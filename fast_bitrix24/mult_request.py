import itertools
from asyncio import ensure_future, as_completed

import more_itertools

from .server_response import ServerResponse
from .srh import ServerRequestHandler, BITRIX_MAX_BATCH_SIZE
from .utils import http_build_query


class MultipleServerRequestHandler:

    def __init__(self, srh: ServerRequestHandler, method, item_list, real_len=None, real_start=0):
        self.srh = srh
        self.method = method
        self.item_list = item_list
        self.real_len = real_len or len(item_list)
        self.real_start = real_start
        self.results = []


    async def run(self):
        self.prepare_batches()
        self.prepare_tasks()
        await self.get_results()
        return self.results


    def prepare_batches(self):
        batch_size = BITRIX_MAX_BATCH_SIZE

        batches = [{
            'halt': 0,
            'cmd': {
                self.batch_command_label(i, item):
                f'{self.method}?{http_build_query(item)}'
                for i, item in enumerate(next_batch)
            }}
            for next_batch in more_itertools.chunked(self.item_list, batch_size)
        ]

        self.method = 'batch'
        self.item_list = batches


    def batch_command_label(self, i, item):
        return f'cmd{i}'


    def prepare_tasks(self):
        self.tasks = []
        for item in self.item_list:
            self.tasks.append(ensure_future(self.srh.single_request(self.method, item)))


    async def get_results(self):
        self.pbar = self.srh.get_pbar(self.real_len, self.real_start)

        for task in as_completed(self.tasks):
            batch_response = await task
            unwrapped_result = ServerResponse(batch_response.result).result
            batch_results = self.extract_result_from_batch_response(unwrapped_result)
            self.results.extend(batch_results)
            self.pbar.update(len(batch_results))

        self.pbar.close()


    def extract_result_from_batch_response(self, unwrapped_result):
        result_list = list(unwrapped_result.values())
        if type(result_list[0]) == list:
            result_list = list(itertools.chain(*result_list))
        return result_list


class MultipleServerRequestHandlerPreserveIDs(MultipleServerRequestHandler):

    def __init__(self, srh, method, item_list, ID_field):
        super().__init__(srh, method, item_list)
        self.ID_field = ID_field
        self.original_item_list = item_list.copy()


    async def run(self):
        await super().run()
        self.sort_results()
        return self.results


    def batch_command_label(self, i, item):
        return item[self.ID_field]


    def extract_result_from_batch_response(self, unwrapped_result):
        result_list_of_tuples = unwrapped_result.items()
        return result_list_of_tuples


    def sort_results(self):
        # выделяем ID для облегчения дальнейшего поиска
        IDs_only = [str(i[self.ID_field]) for i in self.original_item_list]

        # сортируем results на базе порядка ID в original_item_list
        self.results.sort(key = lambda item:
            IDs_only.index(item[0]))
