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

        super().__init__("https://google.com/path", None, False, 50, 2, 480, None)

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

    # нужен какой-то другой тест для контроля орядока результатов
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


@pytest.mark.skip(
    "Абсолютно дикий формат ответа от Битрикс, нарушающий все шаблоны, "
    "которые присутствуют в других кейсах. А именно: батчевый ответ должен "
    "содержать метки переданных в батче команд и иметь структуру словаря списков. "
    "Тут - список списков."
)
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


def test_crm_category_list(bx_dummy):
    from tests.real_responses.crm_category_list import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_all("crm.category.list", {"entityTypeId": 2})

    assert results is not None
    assert isinstance(results, list)
    assert len(results) > 0
    assert all(isinstance(cat, dict) for cat in results)
    assert results == response["result"]["categories"]


def test_crm_contact_add_batch(bx_dummy):
    from tests.real_responses.crm_contact_add_batch import response

    bx_dummy.srh = MockSRH(response)
    result = bx_dummy.call(
        "crm.contact.add",
        {
            "fields": {
                "NAME": "TESTR",
                "PHONE": [{"VALUE": "78966666647", "VALUE_TYPE": "WORK"}],
                "ASSIGNED_BY_ID": -1,
                "OPENED": "Y",
            },
            "params": {"REGISTER_SONET_EVENT": "Y"},
        },
    )

    # Проверяем что результат - это ID созданного контакта
    assert result == 58943


def test_crm_contact_list(bx_dummy):
    response = {
        "result": [
            {
                "ID": "10",
                "NAME": "Абдуалимова Татьяна Александровна",
                "SECOND_NAME": None,
                "LAST_NAME": None,
            }
        ],
        "total": 1,
        "time": {
            "start": 1731743829.0188,
            "finish": 1731743829.06444,
            "duration": 0.045639991760253906,
            "processing": 0.019975900650024414,
            "date_start": "2024-11-16T10:57:09+03:00",
            "date_finish": "2024-11-16T10:57:09+03:00",
            "operating_reset_at": 1731744429,
            "operating": 0,
        },
    }

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_all(
        "crm.contact.list",
        {
            "params": {
                "select": ["ID", "NAME", "SECOND_NAME", "LAST_NAME"],
                "filter": {"=ID": ["10"]},
            }
        },
    )

    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["ID"] == "10"
    assert results[0]["NAME"] == "Абдуалимова Татьяна Александровна"


def test_crm_company_contact_items_get(bx_dummy):
    from tests.real_responses.crm_company_contact_items_get import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_by_ID("crm.company.contact.items.get", ["205364"])
    assert len(results) == 2


def test_task_elapseditem_getlist_mixed_types(bx_dummy):
    """Тест для проверки обработки смешанных типов в get_by_ID для task.elapseditem.getlist.

    Проверяет, что get_by_ID корректно обрабатывает случаи,
    когда значения могут быть пустым списком, списком словарей или одиночным словарём.
    """
    from tests.real_responses.task_elapseditem_getlist_mixed_types import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.get_by_ID(
        "task.elapseditem.getlist",
        ["145572", "144518", "145620", "145485", "145359", "145523", "145142", "145476", "132990"]
    )

    assert isinstance(results, dict)

    # Пустой список
    assert "145572" in results
    assert isinstance(results["145572"], list)
    assert len(results["145572"]) == 0

    # Список из двух словарей
    assert "144518" in results
    assert isinstance(results["144518"], list)
    assert len(results["144518"]) == 2
    assert all(isinstance(item, dict) for item in results["144518"])
    assert results["144518"][0]["ID"] == "111301"
    assert results["144518"][1]["ID"] == "112004"

    # Список из одного словаря
    assert "145620" in results
    assert isinstance(results["145620"], list)
    assert len(results["145620"]) == 1
    assert results["145620"][0]["ID"] == "112248"

    # Одиночный словарь (в реальном ответе такого нет, но если появится)
    # assert isinstance(results["145485"], dict)  # В реальном ответе теперь это пустой список
    assert "145485" in results
    assert isinstance(results["145485"], list)
    assert len(results["145485"]) == 0

    # Список из одного словаря
    assert "145359" in results
    assert isinstance(results["145359"], list)
    assert len(results["145359"]) == 1
    assert results["145359"][0]["ID"] == "112058"

    # Список из одного словаря
    assert "145523" in results
    assert isinstance(results["145523"], list)
    assert len(results["145523"]) == 1
    assert results["145523"][0]["ID"] == "112249"

    # Список из одного словаря
    assert "145142" in results
    assert isinstance(results["145142"], list)
    assert len(results["145142"]) == 1
    assert results["145142"][0]["ID"] == "112244"

    # Список из нескольких словарей
    assert "145476" in results
    assert isinstance(results["145476"], list)
    assert len(results["145476"]) == 6
    assert results["145476"][0]["ID"] == "112063"
    assert results["145476"][-1]["ID"] == "112226"

    # Список из одного словаря
    assert "132990" in results
    assert isinstance(results["132990"], list)
    assert len(results["132990"]) == 1
    assert results["132990"][0]["ID"] == "112237"


def test_lists_element_add_batch(bx_dummy):
    """Тест для проверки правильного возвращения списка простых значений в batch ответе.

    Проверяет, что при batch-вызове lists.element.add возвращается список всех ID,
    а не только первый ID.
    """
    from tests.real_responses.lists_element_add_batch import response

    bx_dummy.srh = MockSRH(response)
    results = bx_dummy.call(
        "lists.element.add",
        [
            {
                "IBLOCK_TYPE_ID": "lists",
                "IBLOCK_ID": 33,
                "ELEMENT_CODE": "1",
                "FIELDS": {"NAME": "Тест 1", "PROPERTY_117": "1"}
            },
            {
                "IBLOCK_TYPE_ID": "lists",
                "IBLOCK_ID": 33,
                "ELEMENT_CODE": "2",
                "FIELDS": {"NAME": "Тест 2", "PROPERTY_117": "2"}
            }
        ]
    )

    # Ожидаем получить кортеж из двух значений (53, 55)
    assert isinstance(results, tuple)
    assert len(results) == 2
    assert results == (53, 55)
