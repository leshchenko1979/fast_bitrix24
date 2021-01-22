from asyncio import gather, sleep
from asyncio.tasks import create_task, wait
from collections import namedtuple
from contextlib import asynccontextmanager
from fast_bitrix24.srh import BITRIX_POOL_SIZE, BITRIX_RPS, ServerRequestHandler
from time import monotonic

import pytest

from fast_bitrix24 import BitrixAsync
from .fixtures import (create_100_leads, create_100_leads_async, create_a_lead,
                       get_test, get_test_async)


class TestAsync:

    @pytest.mark.asyncio
    async def test_simple_async_calls(self, create_100_leads_async):

        b: BitrixAsync = create_100_leads_async

        leads = await b.get_all('crm.lead.list')
        await b.get_by_ID('crm.lead.get', [lead['ID'] for lead in leads])
        await b.list_and_get('crm.lead')
        await b.call('crm.lead.get', {'ID': leads[0]['ID']})
        await b.call_batch({
            'halt': 0,
            'cmd': {
                0: 'crm.lead.list'
            }
        })

    @pytest.mark.asyncio
    async def test_simultaneous_calls(self, create_100_leads_async):
        b = create_100_leads_async

        result = await gather(b.get_all('crm.lead.list'),
                              b.get_all('crm.lead.list'),
                              b.get_all('crm.lead.list'))

        assert len(result) == 3
        assert result[0] == result[1] == result[2]
        assert all(len(r) >= 100 for r in result)


def get_custom_bitrix(pool_size, requests_per_second):
    bitrix = BitrixAsync('http://www.bitrix24.ru/path')

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


class TestAcquire:

    @pytest.mark.asyncio
    async def test_acquire_sequential(self):

        await assert_time_acquire(get_custom_bitrix(1, 1), 1, 0)
        await assert_time_acquire(get_custom_bitrix(10, 1), 10, 0)
        await assert_time_acquire(get_custom_bitrix(1, 5), 5, 1)
        await assert_time_acquire(get_custom_bitrix(50, 10), 60, 1)


    @pytest.mark.asyncio
    async def test_acquire_intermittent(self):

        bitrix = get_custom_bitrix(10, 10)

        await assert_time_acquire(bitrix, 10, 0)
        await sleep(0.3)
        await assert_time_acquire(bitrix, 10, 0.7)

    @pytest.mark.asyncio
    async def test_acquire_speed(self):

        i = 100
        bitrix = get_custom_bitrix(50, 2)

        start = monotonic()

        while i > 50:
            async with bitrix.srh.acquire():
                i -= 1

        elapsed = monotonic() - start
        assert elapsed < 1

        await sleep(10)

        while i:
            async with bitrix.srh.acquire():
                i -= 1

        elapsed = monotonic() - start
        assert 10 + 15 < elapsed < 10 + 15 + 1


class MockResponse(object):
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
            raise RuntimeError(
                f'Pool exhausted after {self.num_requests} requests')

        yield self.post_callback(self, url, json)

class MockSRH(ServerRequestHandler):
    def __init__(self, post_callback):
        super().__init__('http://www.google.com/')
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
async def test_mock():

    bitrix = BitrixAsync('http://www.google.com/')
    bitrix.srh = MockSRH(lambda *args: MockResponse({'result': ('OK',)}))

    assert await bitrix.get_all('abc') == ('OK',)


@pytest.mark.asyncio
async def test_mock_get_all():

    record_ID = iter(range(1_000_000))

    def post_callback(self: ServerRequestHandler, url: str, json: dict):

        if 'batch' not in url:
            response = {
                'result': [{'ID': next(record_ID)} for _ in range(50)],
                'total': 5000
            }

        else:
            response = {
                'result': {'result': {command: [{'ID': next(record_ID)}
                                                for _ in range(50)]
                                      for command in json['cmd']},
                           'total': 5000}
            }

        return MockResponse(response)

    bitrix = BitrixAsync('http://www.google.com/')
    bitrix.srh = MockSRH(post_callback)

    result = await bitrix.get_all('abc')
    assert bitrix.srh.session.num_requests == 3
    assert len(result) == 5000


@pytest.mark.asyncio
async def test_get_by_ID():

    ParsedCommand = namedtuple('ParsedCommand', ['metod', 'params'])

    def post_callback(self: ServerRequestHandler, url: str, json: dict):

        def parse_command(value: str):
            split = value.split('?')
            method, param_str = split[0], split[1]
            pairs = param_str.split('&')
            split = (pair.split('=') for pair in pairs if pair)
            params = {key: value for key, value in split}
            return ParsedCommand(method, params)

        commands = {key: parse_command(value)
                    for key, value in json['cmd'].items()}

        items = {label: {'ID': parsed.params['ID']}
                 for label, parsed in commands.items()}

        response = {'result': {'result': items}}

        return MockResponse(response)


    bitrix = BitrixAsync('http://www.google.com/')
    bitrix.srh = MockSRH(post_callback)

    SIZE = 5000

    bitrix_task = create_task(bitrix.get_by_ID('abc', list(range(SIZE))))
    restore_pool_task = create_task(bitrix.srh.restore_pool())

    await wait({bitrix_task, restore_pool_task}, timeout=10)

    result = bitrix_task.result()

    assert len(result) == SIZE
