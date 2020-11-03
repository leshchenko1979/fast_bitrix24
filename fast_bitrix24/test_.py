from .utils import http_build_query
import os

import pytest

from fast_bitrix24 import Bitrix, slow


@pytest.fixture(scope='session')
def get_test():
    test_webhook = os.getenv('FAST_BITRIX24_TEST_WEBHOOK')
    if test_webhook:
        return Bitrix(test_webhook)
    else:
        raise RuntimeError('Environment variable FAST_BITRIX24_TEST_WEBHOOK should be set to the webhook of your test Bitrix24 account.')


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
        b.get_by_ID('crm.lead.delete', [l['ID'] for l in leads])

    with slow(1.2):
        lead_nos = b.call('crm.lead.add', [{
            'fields': {
                'NAME': f'Customer #{n}',
            }
        } for n in range(100)])

    yield b

    b.get_by_ID('crm.lead.delete', lead_nos)


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

        assert b.call_batch({
            'halt': 0,
            'cmd': {
                1: 'crm.lead.list'
            }
        })


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


    def test_product_rows(self, create_100_leads):
        b = create_100_leads

        lead = b.get_all('crm.lead.list')[0]
        product_rows = [
            {"PRODUCT_NAME": 'ssssdsd', "PRICE": 5555,
             "QUANTITY": 2, "CURRENCY": 'USD'},
            {"PRODUCT_ID": 2809, "PRICE": 100,  "QUANTITY": 2}
        ]

        b.call('crm.lead.productrows.set',
               {'ID': lead['ID'], 'rows': product_rows})

        result_rows = b.call('crm.lead.productrows.get',
                             {'ID': lead['ID']})

        assert len(product_rows) == len(result_rows)


class TestHttpBuildQuery:

    def test_original(self):
        assert http_build_query ({"alpha": "bravo"}) == "alpha=bravo&"

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
