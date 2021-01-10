from asyncio import FIRST_COMPLETED, ensure_future, wait
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
        self.task_iterator = self.generate_a_task()
        self.tasks = set()

    def generate_a_task(self):
        '''Объединяем элементы item_list в батчи и по одной создаем и
        возвращаем задачи asyncio с запросами к серверу для каждого батча.'''

        batches = ({
            'halt': 0,
            'cmd': {
                self.batch_command_label(i, item):
                f'{self.method}?{http_build_query(item)}'
                for i, item in enumerate(next_batch)
            }}
            for next_batch in chunked(self.item_list, BITRIX_MAX_BATCH_SIZE))

        for batch in batches:
            yield ensure_future(self.srh.single_request('batch', batch))

    def batch_command_label(self, i, item):
        return f'cmd{i}'

    async def run(self):
        self.top_up_tasks()

        with self.srh.get_pbar(self.real_len, self.real_start) as pbar:
            while self.tasks:
                done, self.tasks = await wait(self.tasks,
                                              return_when=FIRST_COMPLETED)
                extracted_len = self.process_done_tasks(done)
                pbar.update(extracted_len)
                self.top_up_tasks()

    #            self.pbar.set_postfix({
    #                'max. requests': self.srh.mcr_cur_limit,
    #                'requests': self.srh.concurrent_requests,
    #                'tasks': len(self.tasks)})

        return self.results

    def top_up_tasks(self):
        '''Добавляем в self.tasks столько задач, сколько свободных слотов для
        запросов есть сейчас в self.srh.'''

        to_add = max(
            int(self.srh.mcr_cur_limit) - self.srh.concurrent_requests, 0)
        for _ in range(to_add):
            try:
                self.tasks.add(next(self.task_iterator))
            except StopIteration:
                break

    def process_done_tasks(self, done):
        '''Извлечь результаты из списка законченных задач
        и вернуть кол-во извлеченных элементов.'''

        extracted_len = 0
        for done_task in done:
            batch_response = done_task.result()
            unwrapped_result = ServerResponse(batch_response.result).result
            extracted_len += self.extract_result_from_batch_response(
                unwrapped_result)

        return extracted_len

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
