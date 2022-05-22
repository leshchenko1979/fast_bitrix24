import logging

import pytest
from beartype.typing import Dict, List, Union
from fast_bitrix24.bitrix import BitrixAsync
from fast_bitrix24.logger import logger
from fast_bitrix24.server_response import ServerResponseParser
from fast_bitrix24.srh import ServerRequestHandler

logger.addHandler(logging.StreamHandler())


@pytest.fixture
def bitrix():
    return BitrixAsync("https://google.com/path")


class MockSRH(ServerRequestHandler):
    def __init__(self, response: Union[Dict, List[Dict]]):
        self.response = response if isinstance(response, list) else [response]
        self.element_no = -1

        super().__init__("https://google.com/path", False, None)

    async def single_request(self, *args, **kwargs):
        self.element_no += 1
        return self.response[self.element_no]


def print_decorator(func):
    """Используется для получения буквального ответа от сервера.

    Пример использования:

    bitrix.srh.single_request = print_decorator(bitrix.srh.single_request)
    response = bitrix.call("crm.lead.fields", raw=True)
    assert False

    После этого в логе pytest будет выведен ответ от сервера.
    """

    async def wrapper(*args, **kwargs):
        result = await func(*args, **kwargs)
        print(result)
        return result

    return wrapper


def test_single_success():
    from tests.real_responses.crm_lead_fields_success import response

    results = ServerResponseParser(response).extract_results()
    assert isinstance(results, dict)

    from tests.real_responses.crm_lead_list_one_page_success import response

    results = ServerResponseParser(response).extract_results()
    assert isinstance(results, list)


async def test_batch_success(bitrix):
    from tests.real_responses.crm_lead_list_several_pages_success import \
        response

    bitrix.srh = MockSRH(response)
    results = await bitrix.get_all("crm.lead.list")
    assert isinstance(results, list)


async def test_batch_single_page_error(bitrix):
    from tests.real_responses.crm_get_batch_mix_success_and_errors import \
        response

    bitrix.srh = MockSRH(response)
    with pytest.raises(RuntimeError):
        await bitrix.get_by_ID("crm.lead.get", [0, 1, 35943])


async def test_call_single_success(bitrix):
    from tests.real_responses.call_single_success import response

    bitrix.srh = MockSRH(response)
    results = await bitrix.call("crm.lead.get", {"ID": 35943})
    assert isinstance(results, dict)


async def test_call_several_success(bitrix):
    from tests.real_responses.call_several_success import response

    bitrix.srh = MockSRH(response)
    results = await bitrix.call(
        "crm.lead.get", [{"ID": 35943}, {"ID": 161}, {"ID": 171}]
    )
    assert isinstance(results, tuple)
    assert len(results) == 3
    assert isinstance(results[0], dict)
