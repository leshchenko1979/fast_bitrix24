import os

import pytest

from ..bitrix import Bitrix, BitrixAsync


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

    with b.slow(1.2):
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

    async with b.slow(1.2):
        lead_nos = await b.call('crm.lead.add', [{
            'fields': {
                'NAME': f'Customer #{n}',
            }
        } for n in range(100)])

    yield b

    await b.get_by_ID('crm.lead.delete', lead_nos)

@pytest.fixture(scope='session')
def create_a_deal(get_test):

    b = get_test
    deal_no = b.call('crm.deal.add', {
        'fields': {
            'NAME': 'Bob',
        }
    })

    yield b, deal_no

    b.get_by_ID('crm.deal.delete', [deal_no])
