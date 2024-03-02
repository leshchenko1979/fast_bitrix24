import asyncio
import sys

import aiohttp.client_exceptions as exc
import pytest

from fast_bitrix24 import Bitrix


@pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8 or higher")
@pytest.mark.parametrize("exception", [exc.ServerConnectionError, asyncio.TimeoutError])
@pytest.mark.asyncio
async def test_retries(exception):
    from unittest.mock import AsyncMock

    bitrix = Bitrix("https://google.com/path")
    srh = bitrix.srh

    srh.request_attempt = AsyncMock(spec=srh.request_attempt, side_effect=exception)

    # должна исчерпать все попытки и выдать RuntimeError
    with pytest.raises(RuntimeError):
        await srh.single_request("abc")
