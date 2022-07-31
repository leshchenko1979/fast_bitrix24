from unittest.mock import AsyncMock

import asyncio
from fast_bitrix24 import Bitrix
import pytest

import aiohttp.client_exceptions as exc

@pytest.mark.parametrize("exception", [exc.ServerConnectionError, asyncio.TimeoutError])
@pytest.mark.asyncio
async def test_retries(exception):
    bitrix = Bitrix("https://google.com/path")
    srh = bitrix.srh

    srh.request_attempt = AsyncMock(spec=srh.request_attempt, side_effect=exception)

    # должна исчерпать все попытки и выдать RuntimeError
    with pytest.raises(RuntimeError):
        await srh.single_request(None)
