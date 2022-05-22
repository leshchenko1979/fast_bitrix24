import os

import pytest

from fast_bitrix24 import Bitrix, BitrixAsync


@pytest.fixture(scope='function')
def bx_dummy_async():
    return BitrixAsync("https://google.com/path")


@pytest.fixture(scope='function')
def bx_dummy():
    return Bitrix("https://google.com/path")


@pytest.fixture(scope='session')
def get_test():
    test_webhook = os.getenv('FAST_BITRIX24_TEST_WEBHOOK')
    if test_webhook:
        return Bitrix(test_webhook)

    raise RuntimeError(
        'Environment variable FAST_BITRIX24_TEST_WEBHOOK should be set '
        'to the webhook of your test Bitrix24 account.')


@pytest.fixture(scope='session')
def get_test_async():
    test_webhook = os.getenv('FAST_BITRIX24_TEST_WEBHOOK')
    if test_webhook:
        return BitrixAsync(test_webhook)

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
    leads = b.get_all('crm.lead.list', {'select': ['ID']})

    if len(leads) > 500:
        b.get_by_ID('crm.lead.delete', [lead['ID'] for lead in leads])

    lead_nos = b.call('crm.lead.add', [{
        'fields': {
            'NAME': f'Customer #{n}',
        }
    } for n in range(100)])

    try:
        yield b

    finally:
        b.get_by_ID('crm.lead.delete', lead_nos)


@pytest.fixture(scope='function')
def create_a_lead(get_test) -> tuple:
    b = get_test
    lead_no = b.call('crm.lead.add', {
        'fields': {
            'NAME': 'Bob',
        }
    })

    try:
        yield b, lead_no

    finally:
        b.get_by_ID('crm.lead.delete', [lead_no])


@pytest.fixture(scope='session')
def create_100_tasks(get_test) -> Bitrix:
    b: Bitrix = get_test

    # Подчистить тестовый аккаунт от лишних сущностей,
    # созданных при неудачных тестах, чтобы не было блокировки
    # аккаунта при создании более 1000 сущностей.
    # Скорее всего, вызовет проблемы в параллельно
    # запущенных тестах.
    tasks = b.get_all('tasks.task.list', {'select': ['ID']})
    if len(tasks) > 500:
        b.get_by_ID('tasks.task.delete', [x['task']['id'] for x in tasks],
                    ID_field_name='taskId')

    new_tasks = b.call('tasks.task.add', [{
        'fields': {
            'TITLE': f'Task #{n}',
            'RESPONSIBLE_ID': 1
        }
    } for n in range(100)])

    try:
        yield b

    finally:
        b.get_by_ID('tasks.task.delete', [x['task']['id'] for x in new_tasks],
                    ID_field_name='taskId')


@pytest.fixture(scope='function')
@pytest.mark.asyncio
async def create_100_leads_async(get_test_async) -> BitrixAsync:
    b = get_test_async

    # Подчистить тестовый аккаунт от лишних сущностей,
    # созданных при неудачных тестах, чтобы не было блокировки
    # аккаунта при создании более 1000 сущностей.
    # Скорее всего, вызовет проблемы в параллельно
    # запущенных тестах.
    leads = await b.get_all('crm.lead.list', {'select': ['ID']})
    if len(leads) > 500:
        await b.get_by_ID('crm.lead.delete', [lead['ID'] for lead in leads])

    async with b.slow(5):
        lead_nos = await b.call('crm.lead.add', [{
            'fields': {
                'NAME': f'Customer #{n}',
            }
        } for n in range(100)])

    try:
        yield b

    finally:
        await b.get_by_ID('crm.lead.delete', lead_nos)


@pytest.fixture(scope='session')
def create_a_deal(get_test):

    b = get_test
    deal_no = b.call('crm.deal.add', {
        'fields': {
            'NAME': 'Bob',
        }
    })

    try:
        yield b, deal_no

    finally:
        b.get_by_ID('crm.deal.delete', [deal_no])
