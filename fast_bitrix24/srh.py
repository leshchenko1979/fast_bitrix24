import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager

import aiohttp
from tqdm import tqdm

from .server_response import ServerResponse
from .utils import _url_valid

BITRIX_POOL_SIZE = 50
BITRIX_RPS = 2.0
BITRIX_MAX_BATCH_SIZE = 50
BITRIX_MAX_CONCURRENT_REQUESTS = 20


class ServerRequestHandler():
    '''
    Используется для контроля скорости доступа к серверам Битрикс.

    Основная цель - вести учет количества запросов, которые можно передать
    серверу Битрикс без получения ошибки `5XX`.

    Используется как контекстный менеджер, оборачивающий несколько
    последовательных запросов к серверу.
    '''

    def __init__(self, webhook, verbose):
        self.webhook = self._standardize_webhook(webhook)
        self._verbose = verbose

        self.requests_per_second = BITRIX_RPS
        self.pool_size = BITRIX_POOL_SIZE
        self.slow = False

        self.active_runs = 0
        self.session = None

        # rr - requests register - список отправленных запросов к серверу
        self.rr = deque()

        self.concurrent_requests_sem = asyncio.Semaphore(
            BITRIX_MAX_CONCURRENT_REQUESTS)

    def _standardize_webhook(self, webhook):
        '''Приводит `webhook` к стандартному виду.'''

        if not isinstance(webhook, str):
            raise TypeError(f'Webhook should be a {str}')

        webhook = webhook.lower().strip()

        if not _url_valid(webhook):
            raise ValueError('Webhook is not a valid URL')

        if webhook[-1] != '/':
            webhook += '/'

        return webhook

    def run(self, coroutine):
        '''Запускает `coroutine`, оборачивая его в `run_async()`.'''

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
            loop = asyncio.get_event_loop()

        return loop.run_until_complete(self.run_async(coroutine))

    async def run_async(self, coroutine):
        '''Запускает `coroutine`, создавая и прекращая сессию
        при необходимости.'''

        async with self.handle_sessions():
            return await coroutine

    @asynccontextmanager
    async def handle_sessions(self):
        '''Открывает и закрывает сессию в зависимости от наличия
        активных запросов.'''

        if not self.active_runs and (not self.session or self.session.closed):
            self.session = aiohttp.ClientSession(raise_for_status=True)
        self.active_runs += 1

        yield True

        self.active_runs -= 1
        if not self.active_runs and self.session and not self.session.closed:
            await self.session.close()

    async def single_request(self, method, params=None):
        '''Делает единичный запрос к серверу, ожидая при необходимости.'''

        await self._acquire()

        async with self.concurrent_requests_sem, self.session.post(
                url=self.webhook + method, json=params) as response:
            r = await response.json(encoding='utf-8')

        return ServerResponse(r)

    async def _acquire(self):
        '''Ожидает, пока не станет безопасно делать запрос к серверу.'''

        if self.slow:
            await asyncio.sleep(1 / self.requests_per_second)

        # если пул заполнен, ждать
        elif len(self.rr) >= self.pool_size:
            time_from_last_request = time.monotonic() - self.rr[0]
            time_to_wait = 1 / self.requests_per_second - \
                time_from_last_request
            if time_to_wait > 0:
                await asyncio.sleep(time_to_wait)

        # зарегистрировать запрос в очереди

        cur_time = time.monotonic()
        self.rr.appendleft(cur_time)

        # подчистить пул

        trim_time = cur_time - self.pool_size / self.requests_per_second
        while self.rr and self.rr[len(self.rr) - 1] < trim_time:
            self.rr.pop()

        return

    def get_pbar(self, real_len, real_start):
        '''Возвращает прогресс бар `tqdm()` или пустышку,
        если `self.verbose is False`.'''

        class MutePBar():

            def update(self, i):
                pass

            def close(self):
                pass

        if self._verbose:
            return tqdm(total=real_len, initial=real_start)
        else:
            return MutePBar()
