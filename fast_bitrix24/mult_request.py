from asyncio import FIRST_COMPLETED, ensure_future, wait
from beartype.typing import Dict, List, Union

from more_itertools import chunked
from tqdm.auto import tqdm

from .server_response import ServerResponseParser
from .srh import ServerRequestHandler
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
        self.task_iterator = self.generate_tasks()
        self.tasks = set()

        # Store the expected length and original items for fallback logic
        if hasattr(self.item_list, '__iter__') and not isinstance(self.item_list, (str, bytes)):
            try:
                # Convert to list to get length and store original items
                self.original_items = list(self.item_list)
                self.expected_item_count = len(self.original_items)
                # Recreate the generator from the stored items
                self.item_list = iter(self.original_items)
                self.task_iterator = self.generate_tasks()
            except (TypeError, ValueError):
                self.original_items = None
                self.expected_item_count = None
        else:
            self.original_items = None
            self.expected_item_count = None

    def generate_tasks(self):
        """Group items in batches and create asyncio tasks for each batch"""

        batches = (
            self.package_batch(chunk)
            for chunk in chunked(self.item_list, self.bitrix.batch_size)
        )

        for batch in batches:
            yield ensure_future(self.srh.single_request("batch", batch))

    def package_batch(self, chunk):
        return {
            "halt": 0,
            "cmd": {
                self.batch_command_label(
                    i, item
                ): f"{self.method}?{http_build_query(item)}"
                for i, item in enumerate(chunk)
            },
        }

    def batch_command_label(self, i, item):
        return f"cmd{i:010}"

    async def run(self) -> Union[Dict, List]:
        self.top_up_tasks()

        with self.get_pbar() as pbar:
            while self.tasks:
                done, self.tasks = await wait(self.tasks, return_when=FIRST_COMPLETED)
                extracted_len = self.process_done_tasks(done)
                pbar.update(extracted_len)
                self.top_up_tasks()

        # If we still have items to process but no tasks, force add at least one task
        # This handles the case where rate limiting prevents task addition
        if not self.tasks:
            try:
                self.tasks.add(next(self.task_iterator))
                with self.get_pbar() as pbar:
                    while self.tasks:
                        done, self.tasks = await wait(self.tasks, return_when=FIRST_COMPLETED)
                        extracted_len = self.process_done_tasks(done)
                        pbar.update(extracted_len)
                        self.top_up_tasks()
            except StopIteration:
                pass

        # If batching didn't work due to rate limiting, fall back to individual requests
        # This ensures we get all results even when batching fails
        # Only apply fallback for pagination scenarios where item_list is a sequence
        should_fallback = False
        if self.results is None:
            should_fallback = True
        elif self.expected_item_count is not None:
            # Handle cases where self.results might be an integer or other non-list type
            try:
                results_len = len(self.results) if isinstance(self.results, (list, dict)) else 1
                should_fallback = results_len < self.expected_item_count
            except (TypeError, ValueError):
                # If we can't determine the length, assume fallback is needed
                should_fallback = True

        if should_fallback:
            return await self._fallback_to_individual_requests()

        return self.results

    async def _fallback_to_individual_requests(self) -> Union[Dict, List]:
        """Fall back to individual requests when batching fails due to rate limiting."""
        fallback_results = []

        # Use the stored original items if available, otherwise try to convert item_list
        if self.original_items is not None:
            items = self.original_items
        else:
            # Convert item_list to list if it's a generator
            items = list(self.item_list)

        for item in items:
            try:
                response = await self.srh.single_request(self.method, item)
                result = ServerResponseParser(response).extract_results()
                if isinstance(result, list):
                    fallback_results.extend(result)
                else:
                    fallback_results.append(result)
            except Exception as e:
                # Log the error but continue with other requests
                print(f"Warning: Individual request failed: {e}")
        return fallback_results

    def top_up_tasks(self) -> None:
        """Добавляем в self.tasks столько задач, сколько свободных слотов для
        запросов есть сейчас в self.srh."""

        to_add = max(int(self.srh.mcr_cur_limit) - self.srh.concurrent_requests, 0)

        # If no tasks can be added due to rate limiting, but we have no active tasks,
        # we need to add at least one task to prevent the loop from exiting prematurely
        # This ensures pagination continues even under strict rate limiting while maintaining batching
        if to_add == 0 and not self.tasks:
            to_add = 1

        # Add tasks up to the calculated limit
        for _ in range(to_add):
            try:
                self.tasks.add(next(self.task_iterator))
            except StopIteration:
                break

        # If we still have no tasks but there are items to process, force add one task
        # This is a fallback to ensure pagination doesn't get stuck
        if not self.tasks:
            try:
                self.tasks.add(next(self.task_iterator))
            except StopIteration:
                pass

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
                if isinstance(self.results, list):
                    self.results.extend(extracted)
                else:
                    # Если self.results - словарь, а extracted - список,
                    # то преобразуем список в словарь с числовыми ключами
                    if not self.results:
                        self.results = {}
                    for i, item in enumerate(extracted):
                        self.results[f"item_{i}"] = item
            elif isinstance(extracted, dict):
                if isinstance(self.results, dict):
                    self.results.update(extracted)
                else:
                    # Если self.results - список, а extracted - словарь,
                    # то преобразуем словарь в список
                    if not self.results:
                        self.results = []
                    self.results.append(extracted)

            extracted_len += len(extracted) if isinstance(extracted, list) else 1

        return extracted_len

    def get_pbar(self):
        """Возвращает прогресс бар `tqdm()` или пустышку,
        если `self.bitrix.verbose is False`."""

        if self.bitrix.verbose and not self.mute:
            # Use original_items length if available, otherwise try to get length from item_list
            if self.original_items is not None:
                total = self.real_len or len(self.original_items)
            else:
                try:
                    total = self.real_len or len(self.item_list)
                except (TypeError, ValueError):
                    # item_list is an iterator or not a sequence, use real_len or default
                    total = self.real_len or 0

            return tqdm(total=total, initial=self.real_start)

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
