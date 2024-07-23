import pytest
from fast_bitrix24 import Bitrix
from fast_bitrix24.srh import ServerRequestHandler, TokenRejectedError

from typing import Dict, List, Union


class MockSRH(ServerRequestHandler):
    def __init__(self, token_func, response: Union[Dict, List[Dict]]):
        self.response = response if isinstance(response, list) else [response]
        self.element_no = 0

        super().__init__("https://google.com/path", token_func, False, 50, 2, 480, None)

    async def request_attempt(self, *args, **kwargs):
        result = self.response[self.element_no]
        try:
            if isinstance(result, Exception):
                raise result
            else:
                return result
        finally:
            self.element_no += 1


@pytest.mark.skip(reason="TODO")
def test_first_request():
    # нужно проверить, что вызывается функция запроса токена при первом запросе

    raise AssertionError


@pytest.mark.skip(reason="TODO")
def test_auth_success():
    # нужно проверить, что серверу передается токен, полученный от token_func

    raise AssertionError


@pytest.mark.skip(reason="TODO")
def test_auth_failure():
    # нужно проверить, что вызывается функция запроса токена, если сервер вернул ошибку токена

    raise AssertionError


@pytest.mark.skip(reason="TODO")
def test_abort_on_multiple_failures():
    # нужно проверить, что если token_func регулярно возвращает токен, который отвергается сервером,
    # то запрос оборвется после MAX_RETRIES неудачных попыток

    raise AssertionError


def test_expired_token(bx_dummy):
    # нужно проверить, что вызывается функция запроса токена, если токен истек

    called_count = 0

    async def token_func(*args, **kwargs):
        nonlocal called_count
        called_count += 1
        return "abc"

    bx_dummy.srh = MockSRH(token_func, [{}, TokenRejectedError(), {}])

    bx_dummy.call("test", raw=True)
    bx_dummy.call("test", raw=True)

    assert called_count == 2  # начальный запрос + запрос после истечения токена
