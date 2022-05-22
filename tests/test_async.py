import os
from asyncio import create_task, ensure_future, gather, sleep, wait
from collections import namedtuple
from contextlib import asynccontextmanager
from time import monotonic

import pytest
from fast_bitrix24 import BitrixAsync
from fast_bitrix24.srh import BITRIX_POOL_SIZE, BITRIX_RPS, ServerRequestHandler

from .fixtures import (
    create_100_leads,
    create_100_leads_async,
    create_a_lead,
    get_test,
    get_test_async,
)


@pytest.mark.skipif(
    not os.getenv("FAST_BITRIX24_TEST_WEBHOOK"),
    reason="Нет аккаунта, на котором можно проверить",
)
class TestAsync:
    @pytest.mark.asyncio
    async def test_simple_async_calls(self, create_100_leads_async):

        b: BitrixAsync = create_100_leads_async

        leads = await b.get_all("crm.lead.list")
        await b.get_by_ID("crm.lead.get", [lead["ID"] for lead in leads])
        await b.list_and_get("crm.lead")
        await b.call("crm.lead.get", {"ID": leads[0]["ID"]})
        await b.call_batch({"halt": 0, "cmd": {0: "crm.lead.list"}})

    @pytest.mark.asyncio
    async def test_simultaneous_calls(self, create_100_leads_async):
        b = create_100_leads_async

        result = await gather(
            b.get_all("crm.lead.list"),
            b.get_all("crm.lead.list"),
            b.get_all("crm.lead.list"),
        )

        assert len(result) == 3
        assert result[0] == result[1] == result[2]
        assert all(len(r) >= 100 for r in result)


def get_custom_bitrix(pool_size, requests_per_second, respect_velocity_policy=True):
    bitrix = BitrixAsync(
        "http://www.bitrix24.ru/path", respect_velocity_policy=respect_velocity_policy
    )

    bitrix.srh.pool_size = pool_size
    bitrix.srh.requests_per_second = requests_per_second

    return bitrix


async def assert_time_acquire(bitrix, acquire_amount, time_expected):
    t1 = monotonic()

    for _ in range(acquire_amount):
        async with bitrix.srh.acquire():
            pass

    t2 = monotonic()

    assert time_expected <= t2 - t1 < time_expected + 0.2


@pytest.mark.asyncio
class TestAcquire:
    async def test_acquire_sequential(self):

        await assert_time_acquire(get_custom_bitrix(1, 1), 1, 0)
        await assert_time_acquire(get_custom_bitrix(10, 1), 10, 0)
        await assert_time_acquire(get_custom_bitrix(1, 5), 5, 0.8)
        await assert_time_acquire(get_custom_bitrix(50, 10), 60, 1)

        await assert_time_acquire(get_custom_bitrix(1, 1, False), 100, 0)

    async def test_acquire_intermittent(self):

        bitrix = get_custom_bitrix(10, 10)

        await assert_time_acquire(bitrix, 10, 0)
        await sleep(0.3)
        await assert_time_acquire(bitrix, 10, 0.7)

    async def test_acquire_speed(self):
        CYCLES = 100
        POOL_SIZE = 50
        INTERMITTENT_TIME = 0
        RPS = 100

        i = CYCLES
        bitrix = get_custom_bitrix(POOL_SIZE, RPS)

        start = monotonic()

        while i > POOL_SIZE:
            async with bitrix.srh.acquire():
                i -= 1

        elapsed = monotonic() - start
        assert elapsed < 1

        await sleep(INTERMITTENT_TIME)

        while i:
            async with bitrix.srh.acquire():
                i -= 1

        elapsed = monotonic() - start
        expected = INTERMITTENT_TIME + (CYCLES - POOL_SIZE) / RPS
        assert expected - elapsed < 1


class MockStaticResponse(object):
    def __init__(self, stored_json=None):
        self.stored_json = stored_json

    async def json(self, **args):
        return self.stored_json


class MockSession(object):
    def __init__(self, post_callback):
        self.post_callback = post_callback
        self.pool = BITRIX_POOL_SIZE
        self.rps = BITRIX_RPS
        self.num_requests = 0

    @asynccontextmanager
    async def post(self, url, json):
        self.pool -= 1
        self.num_requests += 1

        if self.pool < 0:
            raise RuntimeError(f"Pool exhausted after {self.num_requests} requests")

        yield self.post_callback(self, url, json)


class MockSRH(ServerRequestHandler):
    def __init__(self, post_callback):
        super().__init__(
            "http://www.google.com/", respect_velocity_policy=True, client=None
        )
        self.post_callback = post_callback

    @asynccontextmanager
    async def handle_sessions(self):
        self.session = MockSession(self.post_callback)
        yield

    async def restore_pool(self):
        while True:
            if self.session.pool < BITRIX_POOL_SIZE:
                self.session.pool += 1
            await sleep(1 / self.session.rps)


@pytest.mark.asyncio
class TestMocks:
    async def test_mock(self):

        bitrix = BitrixAsync("http://www.google.com/")
        bitrix.srh = MockSRH(
            lambda *args: MockStaticResponse({"result": ["OK"], "total": 1})
        )

        assert await bitrix.get_all("abc") == ["OK"]

    async def test_mock_get_all(self):

        record_ID = iter(range(1_000_000))

        def post_callback(self: ServerRequestHandler, url: str, json: dict):

            if "batch" not in url:
                page = [{"ID": next(record_ID)} for _ in range(50)]
                response = {"result": page, "total": 5000}

            else:
                cmds = {
                    command: [{"ID": next(record_ID)} for _ in range(50)]
                    for command in json["cmd"]
                }
                response = {"result": {"result": cmds, "total": 5000}}

            return MockStaticResponse(response)

        bitrix = get_custom_bitrix(10_000, 10_000)
        bitrix.srh = MockSRH(post_callback)

        result = await bitrix.get_all("abc")
        assert bitrix.srh.session.num_requests == 3
        assert len(result) == 5000

    async def test_get_by_ID(self):

        ParsedCommand = namedtuple("ParsedCommand", ["metod", "params"])

        def post_callback(self: ServerRequestHandler, url: str, json: dict):
            def parse_command(value: str):
                split = value.split("?")
                method, param_str = split[0], split[1]
                pairs = param_str.split("&")
                split = (pair.split("=") for pair in pairs if pair)
                params = dict(split)
                return ParsedCommand(method, params)

            commands = {key: parse_command(value) for key, value in json["cmd"].items()}

            items = {
                label: {"ID": parsed.params["ID"]} for label, parsed in commands.items()
            }

            response = {"result": {"result": items}}

            return MockStaticResponse(response)

        POOL_SIZE = 50
        RPS = 100
        PAGE_SIZE = 50
        SIZE = POOL_SIZE * PAGE_SIZE + POOL_SIZE * 2
        print(SIZE)

        COMPUTATION_TIME = 2
        timeout = max(SIZE / 50 - POOL_SIZE, 0) / RPS + COMPUTATION_TIME
        print(timeout)
        assert 0 < timeout < 3  # мы не хотим, чтобы тест шел вечно

        bitrix = get_custom_bitrix(POOL_SIZE, RPS)
        bitrix.srh = MockSRH(post_callback)

        bitrix_task = create_task(bitrix.get_by_ID("abc", list(range(SIZE))))
        restore_pool_task = create_task(bitrix.srh.restore_pool())

        await wait({bitrix_task, restore_pool_task}, timeout=timeout)

        result = bitrix_task.result()
        restore_pool_task.cancel()

        assert len(result) == SIZE

    async def test_limit_request_velocity(self):
        async def mock_request(srh: ServerRequestHandler):
            async with srh.limit_request_velocity():
                print(len(srh.rr), min(srh.rr), max(srh.rr), max(srh.rr) - min(srh.rr))

        srh = MockSRH(None)
        tasks = set()

        SIZE = 70
        srh.requests_per_second = 100

        for _ in range(SIZE):
            tasks |= {ensure_future(mock_request(srh))}

        timeout = (SIZE - srh.pool_size) / srh.requests_per_second + 1

        start = monotonic()

        await wait(tasks, timeout=timeout)

        elapsed = monotonic() - start
        print(elapsed)

        assert timeout - 1 <= elapsed < timeout
