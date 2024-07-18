import pytest

def test_first_request():
    # нужно проверить, что вызывается функция запроса токена при первом запросе

    raise AssertionError

def test_auth_success():
    # нужно проверить, что серверу передается токен, полученный от token_func

    raise AssertionError

def test_auth_failure():
    # нужно проверить, что вызывается функция запроса токена, если сервер вернул ошибку токена

    raise AssertionError

def test_abort_on_multiple_failures():
    # нужно проверить, что если token_func регулярно возвращает токен, который отвергается сервером,
    # то запрос оборвется после MAX_RETRIES неудачных попыток

    raise AssertionError
