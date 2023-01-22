import os

import pytest


@pytest.mark.skipif(
    not os.getenv("FAST_BITRIX24_TEST_WEBHOOK"),
    reason="Нет аккаунта, на котором можно проверить",
)
class TestsWithLiveServer:
    class TestBasic:
        def test_simple_add_lead(self, get_test):
            b = get_test
            lead_no = b.call(
                "crm.lead.add", {"fields": {"NAME": "Bob", "COMMENTS": "x" * 100}}
            )
            b.get_by_ID("crm.lead.delete", [lead_no])

        def test_simple_get_all(self, create_100_leads):
            b = create_100_leads

            result = b.get_all("crm.lead.list")
            assert isinstance(result, list)
            assert len(result) >= 100

        def test_get_all_single_page(self, get_test):
            b = get_test

            result = b.get_all("crm.lead.fields")
            assert isinstance(result, dict)

        def test_get_all_params(self, create_100_leads):
            b = create_100_leads

            fields = ["ID", "NAME"]

            leads = b.get_all("crm.lead.list", {"select": fields})

            assert len(fields) == len(leads[0])

        def test_issue_96(self, get_test):
            from datetime import datetime

            b = get_test
            b.call(
                "telephony.externalcall.register",
                {
                    # 'USER_PHONE_INNER': 'OLD_LINE',
                    "USER_ID": 1,
                    "PHONE_NUMBER": "+79163345641",
                    "CALL_START_DATE": f"{datetime.now()}",
                    "CRM_CREATE": 0,
                    "CRM_ENTITY_TYPE": "LEAD",
                    "CRM_ENTITY_ID": 43707,
                    "SHOW": 0,
                    "TYPE": 1,
                },
            )

        def test_call_batch(self, create_100_leads):
            b = create_100_leads

            with pytest.raises(ValueError):
                b.call_batch({})

            result = b.call_batch({"halt": 0, "cmd": {1: "crm.lead.list"}})

            assert len(result) == 1
            assert len(result["1"]) == 50

        def test_get_by_ID_results(self, create_100_leads):
            b = create_100_leads

            leads = b.get_all("crm.lead.list")
            lead_IDs = [lead["ID"] for lead in leads[:10]]

            leads = b.get_by_ID("crm.lead.get", lead_IDs)
            assert isinstance(leads, dict)

        def test_call(self, get_test):
            b = get_test

            delete_IDs = b.call(
                "crm.lead.add",
                [
                    {"fields": {"NAME": "Bob"}},
                    {"fields": {"NAME": "Jake"}},
                ],
            )
            b.call("crm.lead.delete", [{"ID": ID} for ID in delete_IDs])

            b.call("crm.lead.delete", [])

        def test_call_single_param(self, get_test):
            b = get_test
            delete_ID = b.call("crm.lead.add", {"fields": {"NAME": "Bob"}})
            b.call("crm.lead.delete", {"ID": delete_ID})

        def test_issue_129(self, create_a_lead):
            b, lead = create_a_lead

            # итератор и прогресс-бар - ошибка
            with pytest.raises(TypeError):
                b.get_by_ID("crm.lead.get", iter([lead]))

            with pytest.raises(TypeError):
                b.call("crm.lead.get", iter([{"ID": lead}]))

            # итератор и без прогресс бара - нет ошибки
            b.verbose = False
            b.get_by_ID("crm.lead.get", iter([lead]))
            b.call("crm.lead.get", iter([{"ID": lead}]))

            # sequence - нет ошибки
            b.verbose = True
            b.get_by_ID("crm.lead.get", [lead])

            result = b.call("crm.lead.get", [{"ID": lead}])
            assert isinstance(result, tuple)

            result = b.call("crm.lead.get", {"ID": lead})
            assert isinstance(result, dict)

            # пустой итератор и без прогресс бара - нет ошибки
            b.verbose = False
            b.get_by_ID("crm.lead.get", iter([]))
            b.call("crm.lead.get", iter([]))

        def test_issue_132(self, create_100_tasks):
            b = create_100_tasks

            result = b.get_all("tasks.task.list")
            assert result

            with pytest.raises(ValueError):
                result = b.list_and_get("tasks.task", "taskId")

        def test_case(self, get_test):
            b = get_test

            with pytest.raises(
                RuntimeError, match="Could not find value for parameter"
            ):
                b.call("disk.file.get", [{"ID": 1}])

            with pytest.raises(RuntimeError, match="Could not find entity with id"):
                b.call("disk.file.get", [{"id": 1}])

        def test_long_task_description(self, get_test):
            b = get_test
            lead_no = b.call(
                "crm.lead.add", {"fields": {"NAME": "Bob", "COMMENTS": "x" * 10000}}
            )
            b.get_by_ID("crm.lead.delete", [lead_no])

    class TestParamsEncoding:
        def test_mobile_phone(self, get_test):
            b = get_test
            lead_no = b.call(
                "crm.lead.add",
                {
                    "fields": {
                        "NAME": "Bob",
                        "PHONE": [{"VALUE": "+7123456789", "VALUE_TYPE": "MOBILE"}],
                    }
                },
            )
            lead = b.get_by_ID("crm.lead.get", [lead_no])[str(lead_no)]

            try:
                assert lead["PHONE"][0]["VALUE_TYPE"] == "MOBILE"
            finally:
                b.get_by_ID("crm.lead.delete", [lead_no])

        def test_filter_not_equal(self, create_100_leads):
            b = create_100_leads

            result = b.get_all("crm.lead.list", {"FILTER": {"!STATUS_ID": "NEW"}})
            assert not result

            result = b.get_all("crm.lead.list", {"FILTER": {"!STATUS_ID": "CLOSED"}})
            assert result

            result = b.get_all("crm.lead.list", {"FILTER": {"<>STATUS_ID": "NEW"}})
            assert result

            result = b.get_all("crm.lead.list", {"FILTER": {"<>STATUS_ID": "CLOSED"}})
            assert result

        def test_product_rows(self, create_a_lead):
            b, lead_no = create_a_lead

            product_rows = [
                {
                    "PRODUCT_NAME": "ssssdsd",
                    "PRICE": 5555,
                    "QUANTITY": 2,
                    "CURRENCY": "USD",
                },
                {"PRODUCT_ID": 2809, "PRICE": 100, "QUANTITY": 2},
            ]

            b.call("crm.lead.productrows.set", {"ID": lead_no, "rows": product_rows})

            result_rows = b.call("crm.lead.productrows.get", {"ID": lead_no})

            assert len(product_rows) == len(result_rows)


class TestErrors:
    def test_get_all(self, bx_dummy):
        b = bx_dummy

        with pytest.raises(Exception):
            b.get_all("")

        with pytest.raises(Exception):
            b.get_all(123)

        with pytest.raises(Exception):
            b.get_all("some_method", {"select": None})

        with pytest.raises(Exception):
            b.get_all("some_method", {"filter": 3})

        with pytest.raises(Exception):
            b.get_all("task.elapseditem.getlist", {"filter": 3})

    def test_get_by_ID(self, bx_dummy):
        b = bx_dummy

        with pytest.raises(Exception):
            b.get_by_ID("_", 123)

        with pytest.raises(Exception):
            b.get_by_ID("_", [["a"]])

    def test_call(self, bx_dummy, monkeypatch):
        b = bx_dummy

        async def stub(*args, **kwargs):
            return {"result": {"result": {"ok"}}}

        monkeypatch.setattr(b.srh, "request_attempt", stub)
        assert b.srh.request_attempt is stub

        b.call("_", raw=True)

        with pytest.raises(Exception):
            b.call("_", {})

        with pytest.raises(Exception):
            b.call("_", {"select": ["*"]})

        b.call("_", [1, {"a": 2}], raw=True)
