from asyncio import ensure_future, wait
from itertools import chain

from more_itertools import chunked

from .server_response import ServerResponse
from .srh import BITRIX_MAX_BATCH_SIZE, ServerRequestHandler
from .utils import http_build_query


class MultipleServerRequestHandler:

    def __init__(self, srh: ServerRequestHandler, method, item_list,
                 real_len=None, real_start=0):
        self.srh = srh
        self.method = method
        self.item_list = item_list
        self.real_len = real_len or len(item_list)
        self.real_start = real_start
        self.results = []

    async def run(self):
        self.pbar = self.srh.get_pbar(self.real_len, self.real_start)

        self.task_iterator = self.generate_a_task()
        self.tasks = set()
        self.top_up_tasks()

        while self.tasks:
            done, _ = await wait(self.tasks)

            for done_task in done:
                batch_response = done_task.result()
                unwrapped_result = ServerResponse(batch_response.result).result
                extracted_len = self.extract_result_from_batch_response(
                    unwrapped_result)
                self.pbar.update(extracted_len)

            self.tasks -= done
            self.top_up_tasks()

        self.pbar.close()
        return self.results

    def top_up_tasks(self):
        '''Добавляем в self.tasks столько задач, сколько свободных слотов для
        запросов есть сейчас в self.srh.'''

        while len(self.tasks) < self.srh.concurrent_requests_sem._value:
            try:
                self.tasks.add(next(self.task_iterator))
            except StopIteration:
                break

    def generate_a_task(self):
        '''Объединяем элементы item_list в батчи и по одной создаем и
        возвращаем задачи asyncio с запросами к серверу для каждого батча.'''

        batches = [{
            'halt': 0,
            'cmd': {
                self.batch_command_label(i, item):
                f'{self.method}?{http_build_query(item)}'
                for i, item in enumerate(next_batch)
            }}
            for next_batch in chunked(self.item_list, BITRIX_MAX_BATCH_SIZE)]

        for batch in batches:
            yield ensure_future(self.srh.single_request('batch', batch))

    def batch_command_label(self, i, item):
        return f'cmd{i}'

    def extract_result_from_batch_response(self, unwrapped_result):
        '''Добавляет `unwrapped_result` в `self.results` и возвращает
        длину добавленного списка результатов'''
        result_list = list(unwrapped_result.values())
        if type(result_list[0]) == list:
            result_list = list(chain(*result_list))
        self.results.extend(result_list)
        return len(result_list)


class MultipleServerRequestHandlerPreserveIDs(MultipleServerRequestHandler):

    def __init__(self, srh, method, item_list, ID_field):
        super().__init__(srh, method, item_list)
        self.ID_field = ID_field
        self.results = {}

    def batch_command_label(self, i, item):
        return item[self.ID_field]

    def extract_result_from_batch_response(self, unwrapped_result):
        self.results.update(unwrapped_result)
        return len(unwrapped_result)
