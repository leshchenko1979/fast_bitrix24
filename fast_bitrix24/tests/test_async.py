import asyncio
from asyncio import gather
from time import monotonic

import pytest

from ..bitrix import slow
from ..srh import ServerRequestHandler
from .fixtures import (create_100_leads, create_100_leads_async, create_a_lead,
                       get_test, get_test_async)


class TestAsync:

    @pytest.mark.asyncio
    async def test_simple_async_calls(self, create_100_leads_async):

        b = create_100_leads_async

        leads = await b.get_all('crm.lead.list')
        await b.get_by_ID('crm.lead.list', [lead['ID'] for lead in leads])
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


def get_custom_srh(pool_size, requests_per_second):
    srh = ServerRequestHandler('http://www.bitrix24.ru/path', False)

    srh.pool_size = pool_size
    srh.requests_per_second = requests_per_second

    return srh


async def assert_time_acquire(srh, acquire_amount, time_expected):
    t1 = monotonic()

    for _ in range(acquire_amount):
        await srh._acquire()

    t2 = monotonic()

    assert time_expected - 0.1 < t2 - t1 < time_expected + 0.1


class TestAcquire:

    @pytest.mark.asyncio
    async def test_acquire_sequential(self):

        await assert_time_acquire(get_custom_srh(1, 1), 1, 0)
        await assert_time_acquire(get_custom_srh(10, 1), 10, 0)
        await assert_time_acquire(get_custom_srh(1, 10), 2, 0.1)
        await assert_time_acquire(get_custom_srh(50, 10), 60, 1)


    @pytest.mark.asyncio
    async def test_acquire_intermittent(self):

        srh = get_custom_srh(10, 10)

        await assert_time_acquire(srh, 10, 0)
        await asyncio.sleep(0.3)
        await assert_time_acquire(srh, 10, 0.7)


    @pytest.mark.asyncio
    async def test_acquire_slow(self):

        with slow(10):
            await assert_time_acquire(get_custom_srh(100, 100), 5, 0.5)


    @pytest.mark.asyncio
    async def test_acquire_slow_and_then_fast_and_then_slow_again(self):

        srh = get_custom_srh(10, 10)

        with slow(10):
            await assert_time_acquire(srh, 5, 0.5)

        await assert_time_acquire(srh, 15, 1)

        with slow(10):
            await assert_time_acquire(srh, 5, 0.5)
