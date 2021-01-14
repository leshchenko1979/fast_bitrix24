import pickle
import re
import warnings
from collections import ChainMap
from typing import Iterable

from .mult_request import (MultipleServerRequestHandler,
                           MultipleServerRequestHandlerPreserveIDs)
from .server_response import ServerResponse
from .srh import ServerRequestHandler

BITRIX_PAGE_SIZE = 50


class UserRequestAbstract(object):

    def __init__(self, bitrix, method: str,
                 params: dict = None, mute=False):
        self.bitrix = bitrix
        self.srh: ServerRequestHandler = bitrix.srh
        self.method = method
        self.st_method = self.standardized_method(method)
        self.params = params
        self.st_params = self.standardized_params(params)
        self.mute = mute
        self.check_special_limitations()

    def standardized_method(self, method):
        if not method:
            raise TypeError('Method cannot be empty')

        if not isinstance(method, str):
            raise TypeError('Method should be a str')

        method = method.lower().strip()

        if method == 'batch':
            raise ValueError(
                "Method cannot be 'batch'. Use call_batch() instead.")

        return method

    def standardized_params(self, p):
        if p is None:
            return None

        if not isinstance(p, dict):
            raise TypeError('Params agrument should be a dict')

        for key, __ in p.items():
            if not isinstance(key, str):
                raise TypeError('Keys in params argument should be strs')

        p = {key.upper().strip(): value for key, value in p.items()}

        self.check_expected_clause_types(p)

        return p

    def check_expected_clause_types(self, p):
        EXPECTED_TYPES = {
            'SELECT': list,
            'HELT': int,
            'CMD': dict,
            'LIMIT': int,
            'ORDER': dict,
            'FILTER': dict,
            'START': int,
            'FIELDS': dict
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
                        f'of type {expected_type}, '
                        f'but its type is {type(clause_value)}')

    def check_special_limitations(self):
        raise NotImplementedError


class GetAllUserRequest(UserRequestAbstract):

    def check_special_limitations(self):
        if self.st_params and not set(self.st_params.keys()).isdisjoint(
            {'START', 'LIMIT', 'ORDER'}
        ):
            raise ValueError("get_all() doesn't support parameters "
                             "'start', 'limit' or 'order'")

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

        order_clause = {'order': {'ID': 'ASC'}}

        if self.params:
            if 'ORDER' not in self.st_params:
                self.params.update(order_clause)
        else:
            self.params = order_clause

    async def make_first_request(self):
        self.first_response = await self.srh.single_request(
            self.method, self.params)
        self.results, self.total = \
            self.first_response.result, self.first_response.total

    async def make_remaining_requests(self):
        item_list = (
            ChainMap({'start': start}, self.params)
            for start in range(len(self.results), self.total, BITRIX_PAGE_SIZE)
        )
        remaining_results = await MultipleServerRequestHandler(
                self.bitrix,
                method=self.method,
                item_list=item_list,
                real_len=self.total,
                real_start=len(self.results),
                mute=self.mute
            ).run()

        self.results.extend(remaining_results)

    def dedup_results(self):
        # дедупликация через сериализацию, превращение в set и десериализацию
        self.results = (
            [pickle.loads(y) for y in {pickle.dumps(x) for x in self.results}]
            if self.results
            else []
        )

        if len(self.results) != self.total:
            warnings.warn(
                f"Number of results returned ({len(self.results)}) "
                f"doesn't equal 'total' from the server reply ({self.total})",
                RuntimeWarning)


class GetByIDUserRequest(UserRequestAbstract):

    def __init__(self, bitrix, method: str, params: dict,
                 ID_list: Iterable, ID_field_name: str):
        self.ID_list = ID_list
        self.ID_field_name = ID_field_name.strip()
        super().__init__(bitrix, method, params)

    def check_special_limitations(self):
        if self.st_params and 'ID' in self.st_params.keys():
            raise ValueError("get_by_ID() doesn't support parameter 'ID' "
                             "within the 'params' argument")

        try:
            iter(self.ID_list)
        except TypeError:
            raise TypeError("get_by_ID(): 'ID_list' should be iterable")

        if self.bitrix.verbose:
            try:
                len(self.ID_list)
            except TypeError:
                raise TypeError("get_by_ID(): 'ID_list' should be a Sequence "
                                "if a progress bar is to be displayed")

        for ID in self.ID_list:
            if not isinstance(ID, (str, int)):
                raise TypeError(
                    "get_by_ID(): 'ID_list' should contain only ints or strs")

    async def run(self) -> dict:

        self.prepare_item_list()

        results = await MultipleServerRequestHandlerPreserveIDs(
            self.bitrix,
            self.method,
            self.item_list,
            ID_field=self.ID_field_name
        ).run()

        return results

    def prepare_item_list(self):
        if self.params:
            self.item_list = [
                ChainMap({self.ID_field_name: ID}, self.params)
                for ID in self.ID_list
            ]
        else:
            self.item_list = [
                {self.ID_field_name: ID}
                for ID in self.ID_list
            ]


class CallUserRequest(GetByIDUserRequest):

    def __init__(self, bitrix, method: str,
                 item_list: Iterable):
        self.item_list = item_list
        super().__init__(bitrix, method, None, None, '__order')

    def check_special_limitations(self):
        try:
            if not (isinstance(self.item_list, dict) or
                    all(isinstance(item, dict) for item in self.item_list)):
                raise TypeError
        except TypeError:
            raise TypeError(
                'call() accepts either an iterable of params dicts or '
                'a single params dict')

        if self.bitrix.verbose:
            try:
                len(self.item_list)
            except TypeError:
                raise TypeError("call(): 'items' should be a Sequence "
                                "if a progress bar is to be displayed")

    async def run(self):

        is_single_item = isinstance(self.item_list, dict)
        if is_single_item:
            self.item_list = [self.item_list]

        results = tuple((await super().run()).values())

        return results[0] if is_single_item else results

    def prepare_item_list(self):
        # добавим порядковый номер
        self.item_list = [
            ChainMap(item, {self.ID_field_name: 'order' + str(i)})
            for i, item in enumerate(self.item_list)
        ]


class BatchUserRequest(UserRequestAbstract):

    def __init__(self, bitrix, params):
        super().__init__(bitrix, 'batch', params)

    def standardized_method(self, method):
        return 'batch'

    def check_special_limitations(self):
        if not self.st_params:
            raise ValueError("Params for a batch call can't be empty")

        if {'HALT', 'CMD'} != self.st_params.keys():
            raise ValueError(
                "Params for a batch call should contain only 'halt' and 'cmd' "
                "clauses at the highest level")

        if not isinstance(self.st_params['CMD'], dict):
            raise ValueError("'cmd' clause should contain a dict")

    async def run(self):
        response = await self.srh.single_request(self.method, self.params)
        return ServerResponse(response.result).result


class ListAndGetUserRequest(object):

    def __init__(self, bitrix, method_branch, ID_field_name='ID'):
        self.bitrix = bitrix
        self.srh: ServerRequestHandler = bitrix.srh
        self.method_branch = method_branch
        self.ID_field_name = ID_field_name

    async def run(self):
        if not isinstance(self.method_branch, str):
            raise TypeError('"method_branch" should be a str')

        if re.search(r'(\.list|\.get)$', self.method_branch.strip().lower()):
            raise ValueError(
                '"method_branch" should not end in ".list" or ".get"')

        IDs = await self.srh.run_async(GetAllUserRequest(
            self.bitrix,
            self.method_branch + '.list',
            params={'select': [self.ID_field_name]},
            mute=True).run())

        try:
            ID_list = [x[self.ID_field_name] for x in IDs]
        except (TypeError, KeyError):
            raise ValueError('Seems like list_and_get() cannot be used '
                             f'with method branch "{self.method_branch}"')

        return await self.srh.run_async(GetByIDUserRequest(
            bitrix=self.bitrix,
            method=self.method_branch + '.get',
            params=None,
            ID_field_name=self.ID_field_name,
            ID_list=ID_list).run())
