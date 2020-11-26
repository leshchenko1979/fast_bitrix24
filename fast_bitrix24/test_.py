import asyncio
import os
from asyncio import gather
from time import monotonic

import pytest

from fast_bitrix24 import Bitrix, BitrixAsync, slow

from .srh import ServerRequestHandler
from .utils import http_build_query


@pytest.fixture(scope='session')
def get_test():
    test_webhook = os.getenv('FAST_BITRIX24_TEST_WEBHOOK')
    if test_webhook:
        return Bitrix(test_webhook)
    else:
        raise RuntimeError(
            'Environment variable FAST_BITRIX24_TEST_WEBHOOK should be set '
            'to the webhook of your test Bitrix24 account.')


@pytest.fixture(scope='session')
def get_test_async():
    test_webhook = os.getenv('FAST_BITRIX24_TEST_WEBHOOK')
    if test_webhook:
        return BitrixAsync(test_webhook)
    else:
        raise RuntimeError(
            'Environment variable FAST_BITRIX24_TEST_WEBHOOK should be set '
            'to the webhook of your test Bitrix24 account.')


@pytest.fixture(scope='session')
def create_100_leads(get_test) -> Bitrix:
    b = get_test

    # Подчистить тестовый аккаунт от лишних сущностей,
    # созданных при неудачных тестах, чтобы не было блокировки
    # аккаунта при создании более 1000 сущностей.
    # Скорее всего, вызовет проблемы в параллельно
    # запущенных тестах.
    total_leads = len(b.get_all('crm.lead.list'))
    if total_leads > 500:
        leads = b.get_all('crm.lead.list', {'select': ['ID']})
        b.get_by_ID('crm.lead.delete', [lead['ID'] for lead in leads])

    with slow(1.2):
        lead_nos = b.call('crm.lead.add', [{
            'fields': {
                'NAME': f'Customer #{n}',
            }
        } for n in range(100)])

    yield b

    b.get_by_ID('crm.lead.delete', lead_nos)


@pytest.fixture(scope='function')
def create_a_lead(get_test) -> tuple:
    b = get_test
    lead_no = b.call('crm.lead.add', {
        'fields': {
            'NAME': 'Bob',
        }
    })

    yield b, lead_no

    b.get_by_ID('crm.lead.delete', [lead_no])


@pytest.fixture(scope='function')
@pytest.mark.asyncio
async def create_100_leads_async(get_test_async) -> BitrixAsync:
    b = get_test_async

    # Подчистить тестовый аккаунт от лишних сущностей,
    # созданных при неудачных тестах, чтобы не было блокировки
    # аккаунта при создании более 1000 сущностей.
    # Скорее всего, вызовет проблемы в параллельно
    # запущенных тестах.
    total_leads = len(await b.get_all('crm.lead.list'))
    if total_leads > 500:
        leads = await b.get_all('crm.lead.list', {'select': ['ID']})
        await b.get_by_ID('crm.lead.delete', [lead['ID'] for lead in leads])

    with slow(1.2):
        lead_nos = await b.call('crm.lead.add', [{
            'fields': {
                'NAME': f'Customer #{n}',
            }
        } for n in range(100)])

    yield b

    await b.get_by_ID('crm.lead.delete', lead_nos)


class TestBasic:

    def test_simple_add_lead(self, get_test):
        b = get_test
        lead_no = b.call('crm.lead.add', {
            'fields': {
                'NAME': 'Bob',
                'COMMENTS': 'x' * 100
            }
        })
        b.get_by_ID('crm.lead.delete', [lead_no])


    def test_simple_get_all(self, create_100_leads):
        b = create_100_leads

        resulting = len(b.get_all('crm.lead.list'))

        assert resulting >= 100


    def test_get_all_params(self, create_100_leads):
        b = create_100_leads

        fields = ['ID', 'NAME']

        leads = b.get_all('crm.lead.list', {
            'select': fields
        })

        assert len(fields) == len(leads[0])


    def test_call_batch(self, create_100_leads):
        b = create_100_leads

        with pytest.raises(ValueError):
            b.call_batch({})

        result = b.call_batch({
            'halt': 0,
            'cmd': {
                1: 'crm.lead.list'
            }
        })

        assert len(result) == 1
        assert len(result['1']) == 50


    @pytest.mark.skip
    def test_batch_issue_85(self, get_test):

        b = get_test

        name = 'Test_user'
        email = '@3.ru'
        count = 2352

        payload = {
            'halt': 0,
        }
        result = []

        try:
            for _ in range(10):
                payload['cmd'] = {}

                for _ in range(50):
                    payload['cmd']['add_user'+str(count)] = \
                        f'crm.lead.add?NAME={name+str(count)}' + \
                        f'&EMAIL={str(count)+email}&UF_DEPARTMENT=11&' + \
                        f'UF_PHONE_INNER={count}'
                    count += 1

                r = b.call_batch(payload)
                result.extend(r.values())
                del payload['cmd']
        finally:
            assert len(result) == 500
            assert len(result) == len(set(result))  # все ID уникальные
            b.call('crm.lead.delete', [{'ID': r} for r in result])


    def test_param_errors(self, get_test):
        b = get_test

        with pytest.raises(TypeError):
            b.get_all('')

        with pytest.raises(TypeError):
            b.get_all(123)

        with pytest.raises(TypeError):
            b.get_all('some_method', {
                'select': None
            })

        with pytest.raises(TypeError):
            b.get_all('some_method', {
                'filter': 3
            })


class TestLongRequests:

    def test_long_task_description(self, get_test):
        b = get_test
        lead_no = b.call('crm.lead.add', {
            'fields': {
                'NAME': 'Bob',
                'COMMENTS': 'x' * 10000
            }
        })
        b.get_by_ID('crm.lead.delete', [lead_no])


class TestParamsEncoding:

    def test_mobile_phone(self, get_test):
        b = get_test
        lead_no = b.call('crm.lead.add', {
            'fields': {
                'NAME': 'Bob',
                'PHONE': [{
                    'VALUE': '+7123456789',
                    'VALUE_TYPE': 'MOBILE'
                }]
            }
        })
        __, lead = b.get_by_ID('crm.lead.get', [lead_no])[0]

        try:
            assert lead['PHONE'][0]['VALUE_TYPE'] == 'MOBILE'
        finally:
            b.get_by_ID('crm.lead.delete', [lead_no])


    def test_filter_not_equal(self, create_100_leads):
        b = create_100_leads

        result = b.get_all('crm.lead.list', {
            'FILTER': {
                '!STATUS_ID': 'NEW'
            }
        })
        assert not result

        result = b.get_all('crm.lead.list', {
            'FILTER': {
                '!STATUS_ID': 'CLOSED'
            }
        })
        assert result

        result = b.get_all('crm.lead.list', {
            'FILTER': {
                '<>STATUS_ID': 'NEW'
            }
        })
        assert result

        result = b.get_all('crm.lead.list', {
            'FILTER': {
                '<>STATUS_ID': 'CLOSED'
            }
        })
        assert result


    def test_product_rows(self, create_a_lead):
        b, lead_no = create_a_lead

        product_rows = [
            {"PRODUCT_NAME": 'ssssdsd', "PRICE": 5555,
             "QUANTITY": 2, "CURRENCY": 'USD'},
            {"PRODUCT_ID": 2809, "PRICE": 100,  "QUANTITY": 2}
        ]

        b.call('crm.lead.productrows.set',
               {'ID': lead_no, 'rows': product_rows})

        result_rows = b.call('crm.lead.productrows.get',
                             {'ID': lead_no})

        assert len(product_rows) == len(result_rows)


class TestHttpBuildQuery:

    def test_original(self):
        assert http_build_query({"alpha": "bravo"}) == "alpha=bravo&"

        test = http_build_query({"charlie": ["delta", "echo", "foxtrot"]})
        assert "charlie[0]=delta" in test
        assert "charlie[1]=echo" in test
        assert "charlie[2]=foxtrot" in test

        test = http_build_query({
            "golf": [
                "hotel",
                {"india": "juliet", "kilo": ["lima", "mike"]},
                "november", "oscar"
            ]
        })
        assert "golf[0]=hotel" in test
        assert "golf[1][india]=juliet" in test
        assert "golf[1][kilo][0]=lima" in test
        assert "golf[1][kilo][1]=mike" in test
        assert "golf[2]=november" in test
        assert "golf[3]=oscar" in test


    def test_new(self):
        d = {
            'FILTER': {
                'STATUS_ID': 'CLOSED'
            }
        }

        test = http_build_query(d)
        assert test == 'FILTER[STATUS_ID]=CLOSED&'

        d = {
            'FILTER': {
                '!STATUS_ID': 'CLOSED'
            }
        }

        test = http_build_query(d)
        assert test == 'FILTER[%21STATUS_ID]=CLOSED&'


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
