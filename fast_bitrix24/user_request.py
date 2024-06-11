import pickle
import re
import warnings
from collections import ChainMap

import icontract
from beartype import beartype
from beartype.typing import Any, Dict, Iterable, Union

from .mult_request import (
    MultipleServerRequestHandler,
    MultipleServerRequestHandlerPreserveIDs,
)
from .server_response import ServerResponseParser
from .srh import ServerRequestHandler
from .utils import get_warning_stack_level


BITRIX_PAGE_SIZE = 50

TOP_MOST_LIBRARY_MODULES = [
    "fast_bitrix24\\bitrix",
    "fast_bitrix24\\logger",
    "fast_bitrix24/bitrix",
    "fast_bitrix24/logger",
]

# методы, возвращающие только списки
GET_ALL_ENDINGS = (".list", ".getlist", ".fields", ".getavaliableforpayment", ".types")

# методы, возвращающие как списки, так и отдельные сущности
AMBIGUOUS_ENDINGS = (".get",)

ALL_ENDINGS = (*GET_ALL_ENDINGS, *AMBIGUOUS_ENDINGS)


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

        # st_params будет использоваться для проверки параметров,
        # но на сервер должны уходить параметры без изменения регистра
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
        if p is None:
            return

        p = {key.upper().strip(): value for key, value in p.items()}
        self.check_expected_clause_types(p)

        if "FILTER" in p and None in p["FILTER"].values():
            warnings.warn(
                "Using None as filter value confuses Bitrix. "
                "Try using an empty string, 'null' or 'false'.",
                UserWarning,
                stacklevel=get_warning_stack_level(TOP_MOST_LIBRARY_MODULES),
            )

        return p

    def check_expected_clause_types(self, p):
        EXPECTED_TYPES = {
            "SELECT": list,
            "HALT": int,
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
    @icontract.require(
        lambda self: not self.st_params
        or set(self.st_params.keys()).isdisjoint({"START", "ORDER"}),
        "get_all() doesn't support parameters 'start' or 'order'",
    )
    @icontract.require(
        lambda self: not self.st_method.startswith("tasks.elapseditem."),
        "get_all() shouldn't be used with 'tasks.elapseditem.*' method group. "
        "Use call(raw=True) instead. Read more: "
        "https://github.com/leshchenko1979/fast_bitrix24/issues/199",
    )
    def check_special_limitations(self):
        if not self.st_method.endswith(ALL_ENDINGS):
            warnings.warn(
                "get_all() should be used only with methods that end with "
                f"the following: {ALL_ENDINGS}. You are using '{self.st_method}'. "
                "Use get_by_ID() or call() instead.",
                UserWarning,
                stacklevel=get_warning_stack_level(TOP_MOST_LIBRARY_MODULES),
            )

        if self.st_params and "LIMIT" in self.st_params:
            warnings.warn(
                "Bitrix servers don't seem to support the 'LIMIT' parameter.",
                UserWarning,
                stacklevel=get_warning_stack_level(TOP_MOST_LIBRARY_MODULES),
            )

        if (
            self.st_params
            and "SELECT" in self.st_params
            and "*" in self.st_params["SELECT"]
            and "filter" not in self.st_params
        ):
            warnings.warn(
                "You are selecting all fields and no filter. Beware that this is time-consuming and "
                "may lead to penalties from the Bitrix server.",
                UserWarning,
                stacklevel=get_warning_stack_level(TOP_MOST_LIBRARY_MODULES),
            )

        return True

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
        EXCLUDED_METHODS = {
            "crm.address.list",
            "documentgenerator.template.list",
            "userfieldconfig.list",
        }

        if self.st_method in EXCLUDED_METHODS:
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
                stacklevel=get_warning_stack_level(TOP_MOST_LIBRARY_MODULES),
            )


class GetByIDUserRequest(UserRequestAbstract):
    @beartype
    def __init__(
        self,
        bitrix,
        method: str,
        params: Union[Dict[str, Any], None],
        ID_list: Union[Iterable[Union[int, str]], None],
        ID_field_name: str,
    ):
        self.ID_list = ID_list
        self.ID_field_name = ID_field_name.strip()
        super().__init__(bitrix, method, params)

    @icontract.require(lambda self: self.ID_list, "get_by_ID(): ID_list can't be empty")
    @icontract.require(
        lambda self: not (self.st_params and "ID" in self.st_params.keys()),
        "get_by_ID() doesn't support parameter 'ID' within the 'params' argument",
    )
    @icontract.require(
        lambda self: not self.bitrix.verbose
        or not self.ID_list
        or "__len__" in dir(self.ID_list),
        "get_by_ID(): 'ID_list' should be a Sequence "
        "if a progress bar is to be displayed",
    )
    def check_special_limitations(self):
        return True

    async def run(self) -> dict:
        self.prepare_item_list()

        return await MultipleServerRequestHandlerPreserveIDs(
            self.bitrix,
            self.method,
            self.item_list,
            ID_field=self.ID_field_name,
            get_by_ID=True,
        ).run()

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

    @icontract.require(lambda self: self.item_list, "call(): item_list can't be empty")
    @icontract.require(
        lambda self: not self.bitrix.verbose
        or not self.ID_list
        or "__len__" in dir(self.ID_list),
        "call(): 'ID_list' should be a Sequence "
        "if a progress bar is to be displayed",
    )
    def check_special_limitations(self):
        if self.st_method.endswith(GET_ALL_ENDINGS):
            warnings.warn(
                "It's better to use get_all() with methods that end with "
                f"the following: {GET_ALL_ENDINGS}. You are using '{self.st_method}'.",
                UserWarning,
                stacklevel=get_warning_stack_level(TOP_MOST_LIBRARY_MODULES),
            )

    async def run(self):

        is_single_item = isinstance(self.item_list, dict)
        if is_single_item:
            self.item_list = [self.item_list]

        self.prepare_item_list()

        raw_results = await MultipleServerRequestHandlerPreserveIDs(
            self.bitrix,
            self.method,
            self.item_list,
            ID_field=self.ID_field_name,
            get_by_ID=False,
        ).run()

        if isinstance(raw_results, dict) and not is_single_item:
            return tuple(raw_results.values())
        elif raw_results and isinstance(raw_results, list) and is_single_item:
            return raw_results[0]
        else:
            return raw_results

    def prepare_item_list(self):
        # При отправке батчей на сервер результаты приходят не в том порядке,
        # в котором они отправлялись. Для того, чтобы пользователь мог понять,
        # какой результат пришел по каждому конкретному элементу списка,
        # переданному в call(), нужно возвращать не результаты запроса общим списком,
        # где может быть нарушен порядок, а словарь, содержащий на результаты запроса
        # по каждому элементу списка.

        # Для этого добавляем к каждому элементу списка ключ "__order",
        # который при извелечении результатов запросов будет возвращен пользователю
        # как ключ словаря с результатами.

        self.item_list = [
            ChainMap(item, {self.ID_field_name: f"order{i:010}"})
            for i, item in enumerate(self.item_list)
        ]


class RawCallUserRequest:
    """Отправляем на сервер один элемент, не обрабатывая его и не заворачивая в батчи.

    Нужно для устревших методов, которые принимают на вход список
    (https://github.com/leshchenko1979/fast_bitrix24/issues/157),
    а также для отправки на сервер значений None, которые преобразуются
    в строку при заворачивании в батч
    (https://github.com/leshchenko1979/fast_bitrix24/issues/156).
    """

    @beartype
    def __init__(self, bitrix, method: str, item):
        self.srh = bitrix.srh
        self.method = method
        self.item = item

    async def run(self):
        return await self.srh.single_request(self.method, self.item)


class ListAndGetUserRequest:
    @beartype
    def __init__(self, bitrix, method_branch: str, ID_field_name: str = "id"):
        self.bitrix = bitrix
        self.srh: ServerRequestHandler = bitrix.srh
        self.method_branch = method_branch
        self.ID_field_name = ID_field_name

        warnings.warn(
            "list_and_get() is deprecated. It's not efficient to use it "
            "now that exceeding Bitrix request rate limitations gets users "
            "heavily penalised. Use 'get_all()' instead.",
            DeprecationWarning,
            stacklevel=get_warning_stack_level(TOP_MOST_LIBRARY_MODULES),
        )

    @icontract.require(
        lambda self: not re.search(
            r"(\.list|\.get)$", self.method_branch.strip().lower()
        ),
        'list_and_get(): "method_branch" should not end in ".list" or ".get"',
    )
    async def run(self):
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
                "list_and_get(): seems like list_and_get() cannot be used "
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
