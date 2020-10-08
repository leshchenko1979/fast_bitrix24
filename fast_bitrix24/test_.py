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
def delete_all_leads(get_test):
    b = get_test
    leads = b.get_all('crm.lead.list', {'select': ['ID']})
    b.get_by_ID('crm.lead.delete', [l['ID'] for l in leads])
    
    
@pytest.fixture(scope='session')
def create_1000_leads(get_test, delete_all_leads):
    b = get_test
    
    delete_all_leads
    with slow(1.2):
        lead_nos = b.call('crm.lead.add', [{
            'fields': {
                'NAME': f'Customer #{n}',
            }
        } for n in range(1000)])
    
    yield True
    
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
        
        
    def test_simple_get_all(self, get_test, delete_all_leads, create_1000_leads):
        b = get_test
        create_1000_leads
        
        leads = b.get_all('crm.lead.list')
        
        assert len(leads) == 1000
        
        
    def test_get_all_params(self, get_test, create_1000_leads):
        b = get_test
        create_1000_leads
        
        fields = ['ID', 'NAME']
        
        leads = b.get_all('crm.lead.list', {
            'select': fields
        })
        
        assert len(fields) == len(leads[0])
        
        
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
        
        
class TestEmbeddedListsInParams:
    
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
