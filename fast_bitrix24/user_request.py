import pickle
import re
import warnings
from collections import ChainMap
from beartype.typing import Dict, Any, Iterable, Union
from beartype import beartype

import icontract

from .mult_request import (
    MultipleServerRequestHandler,
    MultipleServerRequestHandlerPreserveIDs,
)
from .server_response import ServerResponseParser
from .srh import ServerRequestHandler

BITRIX_PAGE_SIZE = 50


class UserRequestAbstract:
    @beartype
    @icontract.require(lambda method: method, "Method cannot be empty")
    def __init__(
        self,
        bitrix,
        method: str,
        params: Union[Dict[str, Any], None] = None,
        mute=False,
    ):
        self.bitrix = bitrix
        self.srh: ServerRequestHandler = bitrix.srh
        self.method = method
        self.st_method = self.standardized_method(method)
        self.params = params
        self.st_params = self.standardized_params(params)
        self.mute = mute
        self.check_special_limitations()

    @staticmethod
    @icontract.ensure(
        lambda result: result != "batch",
        "Method cannot be 'batch'. Use call_batch() instead.",
    )
    def standardized_method(method: str):
        return method.lower().strip()

    def standardized_params(self, p):
        if p is not None:
            p = {key.upper().strip(): value for key, value in p.items()}
            self.check_expected_clause_types(p)

        return p

    def check_expected_clause_types(self, p):
        EXPECTED_TYPES = {
            "SELECT": list,
            "HELT": int,
            "CMD": dict,
            "LIMIT": int,
            "ORDER": dict,
            "FILTER": dict,
            "START": int,
            "FIELDS": dict,
        }

        # check for allowed types of key values
        for clause_key, clause_value in p.items():
            if clause_key in EXPECTED_TYPES:
                expected_type = EXPECTED_TYPES[clause_key]

                type_ok = isinstance(clause_value, expected_type)
                if expected_type == list:
                    list_error = not any(
                        isinstance(clause_value, x) for x in [list, tuple, set]
                    )
                else:
                    list_error = False

                if not type_ok or list_error:
                    raise TypeError(
                        f'Clause "{clause_key}" should be '
                        f"of type {expected_type}, "
                        f"but its type is {type(clause_value)}"
                    )

    def check_special_limitations(self):
        raise NotImplementedError

    async def run(self):
        response = await self.srh.single_request(self.method, self.params)
        return ServerResponseParser(response).extract_results()


class GetAllUserRequest(UserRequestAbstract):
    def check_special_limitations(self):
        if self.st_params and not set(self.st_params.keys()).isdisjoint(
            {"START", "LIMIT", "ORDER"}
        ):
            raise ValueError(
                "get_all() doesn't support parameters " "'start', 'limit' or 'order'"
            )

    async def run(self):
        self.add_order_parameter()

        await self.make_first_request()

        if self.first_response.more_results_expected():
            await self.make_remaining_requests()
            self.dedup_results()

        return self.results

    def add_order_parameter(self):
        # необходимо установить порядок сортировки, иначе сортировка
        # будет рандомная и сущности будут повторяться на разных страницах

        # ряд методов не признают параметра "order", для таких ничего не делаем
        excluded_methods = {"crm.address.list", "documentgenerator.template.list"}

        if self.method in excluded_methods:
            return

        order_clause = {"order": {"ID": "ASC"}}

        if self.params:
            if "ORDER" not in self.st_params:
                self.params.update(order_clause)
        else:
            self.params = order_clause

    async def make_first_request(self):
        self.first_response = ServerResponseParser(
            await self.srh.single_request(self.method, self.params)
        )
        self.total = self.first_response.total
        self.results = self.first_response.extract_results()

    @icontract.require(lambda self: isinstance(self.results, list))
    async def make_remaining_requests(self):
        item_list = (
            ChainMap({"start": start}, self.params)
            for start in range(len(self.results), self.total, BITRIX_PAGE_SIZE)
        )
        remaining_results = await MultipleServerRequestHandler(
            self.bitrix,
            method=self.method,
            item_list=item_list,
            real_len=self.total,
            real_start=len(self.results),
            mute=self.mute,
        ).run()

        self.results.extend(remaining_results)

    def dedup_results(self):
        # дедупликация через сериализацию, превращение в set и десериализацию
        self.results = (
            [
                pickle.loads(y)  # nosec B301
                for y in {pickle.dumps(x) for x in self.results}  # nosec B301
            ]
            if self.results
            else []
        )

        if len(self.results) != self.total:
            warnings.warn(
                f"Number of results returned ({len(self.results)}) "
                f"doesn't equal 'total' from the server reply ({self.total})",
                RuntimeWarning,
            )


class GetByIDUserRequest(UserRequestAbstract):
    @beartype
    def __init__(
        self,
        bitrix,
        method: str,
        params: Union[Dict[str, Any], None],
        ID_list: Iterable[Union[int, str]],
        ID_field_name: str,
    ):
        self.ID_list = ID_list
        self.ID_field_name = ID_field_name.strip()
        super().__init__(bitrix, method, params)

    def check_special_limitations(self):
        if self.st_params and "ID" in self.st_params.keys():
            raise ValueError(
                "get_by_ID() doesn't support parameter 'ID' "
                "within the 'params' argument"
            )

        if self.bitrix.verbose:
            try:
                len(self.ID_list)
            except TypeError:
                raise TypeError(
                    "get_by_ID(): 'ID_list' should be a Sequence "
                    "if a progress bar is to be displayed"
                )

    async def run(self) -> dict:

        self.prepare_item_list()

        results = await MultipleServerRequestHandlerPreserveIDs(
            self.bitrix, self.method, self.item_list, ID_field=self.ID_field_name
        ).run()

        return results

    def prepare_item_list(self):
        if self.params:
            self.item_list = [
                ChainMap({self.ID_field_name: ID}, self.params) for ID in self.ID_list
            ]
        else:
            self.item_list = [{self.ID_field_name: ID} for ID in self.ID_list]


class CallUserRequest(GetByIDUserRequest):
    @beartype
    def __init__(self, bitrix, method: str, item_list: Union[Dict, Iterable[Dict]]):
        self.item_list = item_list
        super().__init__(bitrix, method, None, None, "__order")

    def check_special_limitations(self):
        if self.bitrix.verbose:
            try:
                len(self.item_list)
            except TypeError:
                raise TypeError(
                    "call(): 'items' should be a Sequence "
                    "if a progress bar is to be displayed"
                )

    async def run(self):

        is_single_item = isinstance(self.item_list, dict)
        if is_single_item:
            self.item_list = [self.item_list]

        results = tuple((await super().run()).values())

        return results[0] if is_single_item else results

    def prepare_item_list(self):
        # добавим порядковый номер
        self.item_list = [
            ChainMap(item, {self.ID_field_name: f"order{str(i)}"})
            for i, item in enumerate(self.item_list)
        ]


class RawCallUserRequest(UserRequestAbstract):
    """Отправляем на сервер один элемент, не обрабатывая его и не заворачивая в батчи.

    Нужно для устревших методов, которые принимают на вход список
    (https://github.com/leshchenko1979/fast_bitrix24/issues/157),
    а также для отправки на сервер значений None, которые преобразуются
    в строку при заворачивании в батч
    (https://github.com/leshchenko1979/fast_bitrix24/issues/156).
    """

    @beartype
    def __init__(self, bitrix, method: str, item: Union[Dict, None]):
        super().__init__(bitrix, method, item)

    def standardized_params(self, p):
        """Пропускаем все проверки и изменения параметров."""
        return p

    def check_special_limitations(self):
        pass


class BatchUserRequest(UserRequestAbstract):
    @beartype
    @icontract.require(lambda params: params, "Params for a batch call can't be empty")
    def __init__(self, bitrix, params: Dict):
        super().__init__(bitrix, "batch", params)

    def standardized_method(self, method):
        return "batch"

    def check_special_limitations(self):
        if {"HALT", "CMD"} != self.st_params.keys():
            raise ValueError(
                "Params for a batch call should contain only 'halt' and 'cmd' "
                "clauses at the highest level"
            )

        if not isinstance(self.st_params["CMD"], dict):
            raise ValueError("'cmd' clause should contain a dict")


class ListAndGetUserRequest(object):
    @beartype
    def __init__(self, bitrix, method_branch: str, ID_field_name: str = "ID"):
        self.bitrix = bitrix
        self.srh: ServerRequestHandler = bitrix.srh
        self.method_branch = method_branch
        self.ID_field_name = ID_field_name

    async def run(self):
        if not isinstance(self.method_branch, str):
            raise TypeError('"method_branch" should be a str')

        if re.search(r"(\.list|\.get)$", self.method_branch.strip().lower()):
            raise ValueError('"method_branch" should not end in ".list" or ".get"')

        IDs = await self.srh.run_async(
            GetAllUserRequest(
                self.bitrix,
                f"{self.method_branch}.list",
                params={"select": [self.ID_field_name]},
                mute=True,
            ).run()
        )

        try:
            ID_list = [x[self.ID_field_name] for x in IDs]
        except (TypeError, KeyError):
            raise ValueError(
                "Seems like list_and_get() cannot be used "
                f'with method branch "{self.method_branch}"'
            )

        return await self.srh.run_async(
            GetByIDUserRequest(
                bitrix=self.bitrix,
                method=f"{self.method_branch}.get",
                params=None,
                ID_field_name=self.ID_field_name,
                ID_list=ID_list,
            ).run()
        )
