from asyncio import FIRST_COMPLETED, ensure_future, wait
from beartype.typing import Dict, List, Union

from more_itertools import chunked
from tqdm import tqdm

from .server_response import ServerResponseParser
from .srh import BITRIX_MAX_BATCH_SIZE, ServerRequestHandler
from .utils import http_build_query


class MultipleServerRequestHandler:
    def __init__(
        self,
        bitrix,
        method,
        item_list,
        real_len=None,
        real_start=0,
        mute=False,
        get_by_ID=False,
    ):
        self.bitrix = bitrix
        self.srh: ServerRequestHandler = bitrix.srh
        self.method = method
        self.item_list = item_list
        self.real_len = real_len
        self.real_start = real_start
        self.mute = mute
        self.get_by_ID = get_by_ID

        self.results = None
        self.task_iterator = self.generate_a_task()
        self.tasks = set()

    def generate_a_task(self):
        """Объединяем элементы item_list в батчи и по одной создаем и
        возвращаем задачи asyncio с запросами к серверу для каждого батча."""

        batches = (
            {
                "halt": 0,
                "cmd": {
                    self.batch_command_label(
                        i, item
                    ): f"{self.method}?{http_build_query(item)}"
                    for i, item in enumerate(next_batch)
                },
            }
            for next_batch in chunked(self.item_list, BITRIX_MAX_BATCH_SIZE)
        )

        for batch in batches:
            yield ensure_future(self.srh.single_request("batch", batch))

    def batch_command_label(self, i: int, item) -> str:
        return f"cmd{i:010}"

    async def run(self) -> Union[Dict, List]:
        self.top_up_tasks()

        with self.get_pbar() as pbar:
            while self.tasks:
                done, self.tasks = await wait(self.tasks, return_when=FIRST_COMPLETED)
                extracted_len = self.process_done_tasks(done)
                pbar.update(extracted_len)
                self.top_up_tasks()

        #            self.pbar.set_postfix({
        #                'max. requests': self.srh.mcr_cur_limit,
        #                'requests': self.srh.concurrent_requests,
        #                'tasks': len(self.tasks)})

        return self.results

    def top_up_tasks(self) -> None:
        """Добавляем в self.tasks столько задач, сколько свободных слотов для
        запросов есть сейчас в self.srh."""

        to_add = max(int(self.srh.mcr_cur_limit) - self.srh.concurrent_requests, 0)
        for _ in range(to_add):
            try:
                self.tasks.add(next(self.task_iterator))
            except StopIteration:
                break

    def process_done_tasks(self, done: list) -> int:
        """Извлечь результаты из списка законченных задач
        и вернуть кол-во извлеченных элементов."""

        extracted_len = 0
        for done_task in done:
            extracted = ServerResponseParser(
                done_task.result(), self.get_by_ID
            ).extract_results()

            if self.results is None:
                self.results = extracted
            elif isinstance(extracted, list):
                self.results.extend(extracted)
            elif isinstance(extracted, dict):
                self.results.update(extracted)

            extracted_len += len(extracted)

        return extracted_len

    def get_pbar(self):
        """Возвращает прогресс бар `tqdm()` или пустышку,
        если `self.bitrix.verbose is False`."""

        if self.bitrix.verbose and not self.mute:
            return tqdm(
                total=(self.real_len or len(self.item_list)), initial=self.real_start
            )

        return MutePBar()


class MutePBar:
    def __enter__(self):
        return self

    def __exit__(*args):
        pass

    def update(*args):
        pass


class MultipleServerRequestHandlerPreserveIDs(MultipleServerRequestHandler):
    def __init__(self, bitrix, method, item_list, ID_field, get_by_ID):
        super().__init__(bitrix, method, item_list, get_by_ID=get_by_ID)
        self.ID_field = ID_field

    def batch_command_label(self, i, item):
        return item[self.ID_field]
