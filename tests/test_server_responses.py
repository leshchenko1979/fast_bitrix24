import logging

import pytest
from beartype.typing import Dict, List, Union
from fast_bitrix24.logger import logger
from fast_bitrix24.server_response import (
    ErrorInServerResponseException,
    ServerResponseParser,
)
from fast_bitrix24.srh import ServerRequestHandler

logger.addHandler(logging.StreamHandler())


class MockSRH(ServerRequestHandler):
    def __init__(self, response: Union[Dict, List[Dict]]):
        self.response = response if isinstance(response, list) else [response]
        self.element_no = -1

        super().__init__("https://google.com/path", False, 50, 2, None)

    async def single_request(self, *args, **kwargs):
        self.element_no += 1
        return self.response[self.element_no]


def test_single_success():
    from tests.real_responses.crm_lead_fields_success import response

    results = ServerResponseParser(response).extract_results()
    assert isinstance(results, dict)

    from tests.real_responses.crm_lead_list_one_page_success import response

    results = ServerResponseParser(response).extract_results()
    assert isinstance(results, list)


def test_batch_success(bx_dummy, recwarn):
    from tests.real_responses.crm_lead_list_several_pages_success import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_all("crm.lead.list")
    assert isinstance(results, list)
    print(w.message for w in recwarn.list)
    with pytest.raises(Exception):
        recwarn.pop(RuntimeWarning)


def test_batch_single_page_error(bx_dummy):
    from tests.real_responses.crm_get_batch_mix_success_and_errors import response

    bx_dummy.srh = MockSRH(response)
    with pytest.raises(ErrorInServerResponseException):
        bx_dummy.get_by_ID("crm.lead.get", [0, 1, 35943])


def test_call_single_success(bx_dummy):
    from tests.real_responses.call_single_success import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.call("crm.lead.get", {"ID": 35943})
    assert isinstance(results, dict)


def test_call_several_success(bx_dummy):
    from tests.real_responses.call_several_success import response

    bx_dummy.srh = MockSRH(response)

    ID_list = [161, 35943, 171]
    results = bx_dummy.call("crm.lead.get", [{"ID": ID} for ID in ID_list])

    assert isinstance(results, tuple)
    assert len(results) == 3
    assert isinstance(results[0], dict)

    # нужен какой-то другой тест для контроля порядока результатов
    # assert [result["ID"] for result in results] == ID_list, "Incorrect order of IDs"


def test_call_list_empty(bx_dummy):
    from tests.real_responses.batch_list_empty import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.call(
        "crm.lead.list", ({"filter": {"PHONE": "+0000877578564"}, "select": ["ID"]},)
    )
    assert isinstance(results, list)
    assert len(results) == 0

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.call(
        "crm.lead.list", {"filter": {"PHONE": "+0000877578564"}, "select": ["ID"]}
    )
    assert isinstance(results, list)
    assert len(results) == 0


def test_get_all_non_list_method(bx_dummy, recwarn):
    from tests.real_responses.user_fields import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_all("user.fields")
    assert isinstance(results, dict)
    print(w.message for w in recwarn.list)
    with pytest.raises(Exception):
        recwarn.pop(RuntimeWarning)


def test_batch_and_call_raw(bx_dummy):
    from tests.real_responses.call_batch import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.call_batch(
        {
            "halt": 0,
            "cmd": {
                "statuses": "crm.status.entity.items?entityId=STATUS",
                "sources": "crm.status.entity.items?entityId=SOURCE",
            },
        }
    )
    assert isinstance(results, dict)
    assert results.keys() == {"statuses", "sources"}

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.call(
        "batch",
        {
            "halt": 0,
            "cmd": {
                "statuses": "crm.status.entity.items?entityId=STATUS",
                "sources": "crm.status.entity.items?entityId=SOURCE",
            },
        },
        raw=True,
    )
    assert isinstance(results, dict)
    assert results.keys() == {"result", "time"}


def test_stagehistory(bx_dummy, recwarn):
    from tests.real_responses.stagehistory import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_all(
        "crm.stagehistory.list",
        {
            "entityTypeId": 2,
            "filter": {"STAGE_ID": "UC_KW9988"},
        },
    )

    assert isinstance(results, list)
    print(w.message for w in recwarn.list)
    with pytest.raises(Exception):
        recwarn.pop(RuntimeWarning)


def test_single_add(bx_dummy):
    from tests.real_responses.single_add import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.call(
        "tasks.task.add",
        {
            "fields": {
                "TITLE": "АГ",
                "DESCRIPTION": "Сложно сказать, почему потускнели светлые лики икон",
                "RESPONSIBLE_ID": 1,
                "TAGS": "скпэ22-4",
                "DEADLINE": "2022/07/30",
            }
        },
    )
    assert isinstance(results, dict)


def test_get_all_tasks(bx_dummy):
    from tests.real_responses.get_all_tasks import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_all(
        "tasks.task.list",
        {"filter": {"status": -1}, "select": ["ID", "STATUS", "STATUS_COMPLETE"]},
    )
    assert isinstance(results, list)
    assert len(results) == 1570


def test_crm_dealcategory_stage_list(bx_dummy):
    from tests.real_responses.crm_dealcategory_stage_list import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_by_ID("crm.dealcategory.stage.list", ["2", "4", "8", 0])
    assert isinstance(results, dict)


def test_crm_dealcategory_stage_list_batch_of_one(bx_dummy):
    from tests.real_responses.crm_dealcategory_stage_list_batch_of_one import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_by_ID("crm.dealcategory.stage.list", [0])

    # should return a list of dicts
    assert isinstance(results, list) and isinstance(results[0], dict)


def test_catalog_document_element_list(bx_dummy):
    from tests.real_responses.catalog_document_element_list import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_all("catalog.document.element.list")

    assert len(results) == 95


def test_crm_item_productrow_list(bx_dummy):
    from tests.real_responses.crm_item_productrow_list import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_all("crm.item.productrow.list")

    assert len(results) == 2


def test_crm_stagehistory_list(bx_dummy):
    from tests.real_responses.crm_stagehistory_list import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_all("crm.stagehistory.list")

    assert len(results) == 9


def test_socialnetwork_api_workgroup_list(bx_dummy):
    from tests.real_responses.socialnetwork_api_workgroup_list import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_all(
        "socialnetwork.api.workgroup.list",
        {
            "select": [
                "ID",
                "NAME",
                "DESCRIPTION",
                "DATE_CREATE",
                "DATE_UPDATE",
                "DATE_ACTIVITY",
                "SUBJECT_ID",
                "KEYWORDS",
                "IMAGE_ID",
                "NUMBER_OF_MEMBERS",
                "INITIATE_PERMS",
                "SPAM_PERMS",
                "SUBJECT_NAME",
            ]
        },
    )

    assert len(results) == 50


def test_crm_add_item(bx_dummy):
    from tests.real_responses.crm_item_add import response

    bx_dummy.srh = MockSRH(response)
    result = bx_dummy.call(
        "crm.item.add", {"entityTypeId": 1, "fields": {"first_name": "first_name"}}
    )
    assert result != "item" and isinstance(result, dict) and "id" in result


def test_crm_item_list(bx_dummy):
    from tests.real_responses.crm_item_list import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_all("crm.item.list")

    assert len(results) == 3
