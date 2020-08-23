import asyncio
from collections.abc import Sequence
import pickle
import warnings

from .utils import _merge_dict
from .mult_request import MultipleServerRequestHandler, MultipleServerRequestHandlerPreserveIDs
from .server_response import ServerResponse

class UserRequestAbstract():
    def __init__(self, srh, method: str, params: dict):
        self.srh = srh
        self.method = method
        self.params = params
        
    def check_args(self):
        self.check_method()
        if self.params:
            self.check_params(self.params)
        self.check_special_limitations()

    def check_params(self, p):
        # check if p is dict
        if not isinstance(p, dict):
            raise TypeError('params agrument should be a dict')

        clauses = {
            'select': list,
            'halt': int,
            'cmd': dict,
            'limit': int,
            'order': dict,
            'filter': dict,
            'start': int,
            'fields': dict
        }

        # check for allowed types of key values
        for pi in p.items():
            if pi[0] in clauses.keys():
                t = clauses[pi[0].lower()]
                if t and not (
                    (isinstance(pi[1], t)) or
                    ((t == list) and (any([isinstance(pi[1], x) for x in [list, tuple, set]])))
                ):
                    raise TypeError(f'Clause "{pi[0]}" should be of type {t}, '
                        f'but its type is {type(pi[1])}')

    
    def check_special_limitations(self):
        raise NotImplementedError
    
    
    def check_method(self):
        if not isinstance(self.method, str):
            raise TypeError('Method should be a str')
        if self.method.lower().strip() == 'batch':
            raise ValueError("Method cannot be 'batch'")
    
    
class GetAllUserRequest(UserRequestAbstract):
    def run(self):
        self.check_args()
        return self.srh.run(self.get_paginated_list())


    def check_special_limitations(self):
        if self.params:
            for k in self.params.keys():
                if k.lower() in ['start', 'limit', 'order']:
                    raise ValueError("get_all() doesn't support parameters 'start', 'limit' or 'order'")

    
    async def get_paginated_list(self):
        self.add_order_parameter()

        await self.make_first_request()

        if self.first_response.more_results_expected():
            await self.make_remaining_requests()
            self.dedup_results()
                
        return self.results


    def add_order_parameter(self):
        # необходимо установить порядок сортировки, иначе сортировка будет рандомная
        # и сущности будут повторяться на разных страницах
        
        if self.params:
            if 'order' not in [x.lower() for x in self.params.keys()]:
                self.params.update({'order': {'ID': 'ASC'}})
        else:
            self.params = {'order': {'ID': 'ASC'}}

    
    async def make_first_request(self):
        self.srh.add_request_task(self.method, self.params)
        self.first_response = await next(self.srh.get_server_serponses())
        self.results, self.total = self.first_response.result, self.first_response.total 


    async def make_remaining_requests(self):
        self.results.extend(
            await MultipleServerRequestHandler(
                self.srh,
                method = self.method, 
                item_list = [
                    _merge_dict({'start': start}, self.params)
                    for start in range(len(self.results), self.total, 50)
                ], 
                real_len = self.total, 
                real_start = len(self.results)
            ).run()
        )


    def dedup_results(self):
        # дедупликация через сериализацию, превращение в set и десериализацию
        self.results = [pickle.loads(y) for y in set([pickle.dumps(x) for x in self.results])] \
            if self.results else []

        if len(self.results) != self.total:
            warnings.warn(f"Number of results returned ({len(self.results)}) "
                f"doesn't equal 'total' from the server reply ({self.total})",
                RuntimeWarning)


class GetByIDUserRequest(UserRequestAbstract):
    def __init__(self, srh, method: str, params: dict, ID_list, ID_field_name):
        super().__init__(srh, method, params)
        self.ID_list = ID_list
        self.ID_field_name = ID_field_name
        
        
    def check_special_limitations(self):
        if self.params: 
            for k in self.params.keys():
                if k.lower() == 'id':
                    raise ValueError("get_by_ID() doesn't support parameter 'ID' within the 'params' argument")

        if not(isinstance(self.ID_list, Sequence)):
            raise TypeError("get_by_ID(): 'ID_list' should be a sequence")


    def run(self):
        self.check_args()

        if self.list_empty():
            return []
        
        self.prepare_item_list()
        
        results = self.srh.run(
            MultipleServerRequestHandlerPreserveIDs(
                self.srh,
                self.method,
                self.item_list,
                ID_field=self.ID_field_name
            ).run()
        )
        
        return results

        
    def list_empty(self):
        return len(self.ID_list) == 0
    
    
    def prepare_item_list(self):
        if self.params:
            self.item_list = [
                _merge_dict({self.ID_field_name: ID}, self.params) 
                for ID in self.ID_list
            ]
        else:
            self.item_list = [
                {self.ID_field_name: ID} 
                for ID in self.ID_list
            ] 


class CallUserRequest(GetByIDUserRequest):
    def __init__(self, srh, method: str, item_list):
        super().__init__(srh, method, None, None, '__order')
        self.item_list = item_list

        
    def check_special_limitations(self):
        if not isinstance(self.item_list, Sequence):
            raise TypeError("call(): 'item_list' should be a sequence")

        try:
            [self.check_params(p) for p in self.item_list]
        except (TypeError, ValueError) as err:
            raise ValueError(
                'item_list contains items with incorrect method params') from err 


    def run(self):
        results = super().run()
        
        # убираем поле с порядковым номером из результатов
        return [item[1] for item in results]


    def list_empty(self):
        return len(self.item_list) == 0

    
    def prepare_item_list(self):
        # добавим порядковый номер
        self.item_list = [
            _merge_dict(item, {self.ID_field_name: 'order' + str(i)}) 
            for i, item in enumerate(self.item_list)
        ]


class BatchUserRequest(UserRequestAbstract):

    def __init__(self, srh, params):
        super().__init__(srh, 'batch', params)


    def check_method(self):
        if self.method != 'batch':
            raise ValueError("Method should be 'batch'")


    def check_special_limitations(self):
        if {'halt', 'cmd'} != self.params.keys():
            raise ValueError("Params for a batch call should contain only 'halt' and 'cmd' clauses at the highest level")

        if not isinstance(self.params['cmd'], dict):
            raise ValueError("'cmd' clause should contain a dict")
    

    def run(self):
        self.check_args()
        return self.srh.run(self.batch_call())

        
    async def batch_call(self):
        self.srh.add_request_task(self.method, self.params)
        response = await next(self.srh.get_server_serponses())
        return ServerResponse(response.result).result