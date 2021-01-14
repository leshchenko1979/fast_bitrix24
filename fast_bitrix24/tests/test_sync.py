import pytest

from ..utils import http_build_query
from .fixtures import (create_100_leads, create_100_leads_async, create_a_lead,
                       get_test, get_test_async, create_a_deal,
                       create_100_tasks)

from ..bitrix import Bitrix


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

    def test_issue_96(self, get_test):
        from datetime import datetime
        b = get_test
        b.call(
            'telephony.externalcall.register',
            {
                # 'USER_PHONE_INNER': 'OLD_LINE',
                'USER_ID': 1,
                'PHONE_NUMBER': '+79163345641',
                'CALL_START_DATE': f'{datetime.now()}',
                'CRM_CREATE': 0,
                'CRM_ENTITY_TYPE': 'LEAD',
                'CRM_ENTITY_ID': 43707,
                'SHOW': 0,
                'TYPE': 1
            }
        )

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

    def test_case(self, get_test):
        b = get_test

        with pytest.raises(RuntimeError,
                           match='Could not find value for parameter'):
            b.call(
                'disk.file.get',
                [{'ID': 1}]
            )

        with pytest.raises(RuntimeError,
                           match='Could not find entity with id'):
            b.call(
                'disk.file.get',
                [{'id': 1}]
            )

    def test_get_by_ID_params(self, get_test):
        b = get_test

        with pytest.raises(TypeError, match='should be iterable'):
            b.get_by_ID('_', 123)

        with pytest.raises(TypeError,
                           match='should contain only ints or strs'):
            b.get_by_ID('_', [['a']])

    def test_get_by_ID_results(self, create_100_leads):
        b = create_100_leads

        leads = b.get_all('crm.lead.list')
        lead_IDs = [lead['ID'] for lead in leads[:10]]

        leads = b.get_by_ID('crm.lead.get', lead_IDs)
        assert isinstance(leads, dict)

    def test_call(self, get_test):
        b = get_test

        delete_ID = b.call('crm.lead.add', {'fields': {'NAME': 'Bob'}})
        b.call('crm.lead.delete', {'ID': delete_ID})

        delete_IDs = b.call('crm.lead.add', [
            {'fields': {'NAME': 'Bob'}},
            {'fields': {'NAME': 'Jake'}},
        ])
        b.call('crm.lead.delete', [{'ID': ID} for ID in delete_IDs])

        b.call('crm.lead.delete', [])

    def test_issue_129(self, create_a_lead):
        b, lead = create_a_lead

        # итератор и прогресс-бар - ошибка
        with pytest.raises(TypeError):
            b.get_by_ID('crm.lead.get', iter([lead]))

        with pytest.raises(TypeError):
            b.call('crm.lead.get', iter([{'ID': lead}]))

        # итератор и без прогресс бара - нет ошибки
        b.verbose = False
        b.get_by_ID('crm.lead.get', iter([lead]))
        b.call('crm.lead.get', iter([{'ID': lead}]))

        # sequence - нет ошибки
        b.verbose = True
        b.get_by_ID('crm.lead.get', [lead])

        result = b.call('crm.lead.get', [{'ID': lead}])
        assert isinstance(result, tuple)

        result = b.call('crm.lead.get', {'ID': lead})
        assert isinstance(result, dict)

        # пустой итератор и без прогресс бара - нет ошибки
        b.verbose = False
        b.get_by_ID('crm.lead.get', iter([]))
        b.call('crm.lead.get', iter([]))

    def test_issue_132(self, create_100_tasks):
        b = create_100_tasks
        result = b.get_all('tasks.task.list')
        assert result
        result = b.list_and_get('tasks.task')


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
        lead = b.get_by_ID('crm.lead.get', [lead_no])[str(lead_no)]

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
