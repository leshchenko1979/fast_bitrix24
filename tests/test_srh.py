import contextlib
import pytest
from unittest.mock import AsyncMock, Mock
from fast_bitrix24.srh import ServerRequestHandler
import aiohttp


@pytest.mark.asyncio
async def test_request_attempt():
    # Create a mock response
    mock_response = Mock(spec=aiohttp.ClientResponse)
    mock_response.status = 200
    mock_response.json.return_value = {"time": {"operating": 1000}}

    @contextlib.asynccontextmanager
    async def mock_post(url, json, ssl):
        yield mock_response

    mock_session = AsyncMock()
    mock_session.post = mock_post

    handler = ServerRequestHandler(
        "https://google.com/webhook", None, True, 50, 2, 480, mock_session
    )

    # Call the method
    result = await handler.request_attempt("method", {"param": "value"})

    # Assert the expected behavior
    assert result == {"time": {"operating": 1000}}
    assert "method" in handler.method_throttlers


@pytest.mark.asyncio
async def test_request_attempt_returns_error_response_without_time():
    # Bitrix24 error responses (e.g. ACCESS_ERROR, INVALID_REQUEST) do not
    # include a "time" key. The throttler must not crash on them — the raw
    # response should propagate so that ServerResponseParser can raise a
    # proper ErrorInServerResponseException downstream.
    error_payload = {
        "error": "ACCESS_ERROR",
        "error_description": "You do not have access to the specified dialog",
    }

    mock_response = Mock(spec=aiohttp.ClientResponse)
    mock_response.status = 200
    mock_response.json.return_value = error_payload

    @contextlib.asynccontextmanager
    async def mock_post(url, json, ssl):
        yield mock_response

    mock_session = AsyncMock()
    mock_session.post = mock_post

    handler = ServerRequestHandler(
        "https://google.com/webhook", None, True, 50, 2, 480, mock_session
    )

    result = await handler.request_attempt("method", {"param": "value"})

    assert result == error_payload
