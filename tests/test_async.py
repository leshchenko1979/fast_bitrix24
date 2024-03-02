import os
from asyncio import create_task, ensure_future, gather, sleep, wait
from collections import namedtuple
from contextlib import asynccontextmanager
from time import monotonic

import pytest
from fast_bitrix24 import BitrixAsync
from fast_bitrix24.srh import ServerRequestHandler


@pytest.mark.skipif(
    not os.getenv("FAST_BITRIX24_TEST_WEBHOOK"),
    reason="Нет аккаунта, на котором можно проверить",
)
@pytest.mark.asyncio
class TestAsync:
    async def test_simple_async_calls(self, create_100_leads_async):

        b: BitrixAsync = create_100_leads_async

        leads = await b.get_all("crm.lead.list")
        await b.get_by_ID("crm.lead.get", [lead["ID"] for lead in leads])
        await b.list_and_get("crm.lead")
        await b.call("crm.lead.get", {"ID": leads[0]["ID"]})
        await b.call_batch({"halt": 0, "cmd": {0: "crm.lead.list"}})

    async def test_simultaneous_calls(self, create_100_leads_async):
        b = create_100_leads_async

        result = await gather(
            b.get_all("crm.lead.list"),
            b.get_all("crm.lead.list"),
            b.get_all("crm.lead.list"),
        )

        assert len(result) == 3
        assert result[0] == result[1] == result[2]
        assert all(len(r) >= 100 for r in result)
