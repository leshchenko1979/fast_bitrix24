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
    mock_response.json.return_value = {'time': {'operating': 1000}}

    @contextlib.asynccontextmanager
    async def mock_post(url, json):
        yield mock_response

    mock_session = AsyncMock()
    mock_session.post = mock_post

    handler = ServerRequestHandler('https://google.com/webhook', True, mock_session)

    # Call the method
    result = await handler.request_attempt('method', {'param': 'value'})

    # Assert the expected behavior
    assert result == {'time': {'operating': 1000}}
    assert "method" in handler.throttlers
