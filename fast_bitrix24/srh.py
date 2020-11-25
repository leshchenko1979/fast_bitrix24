import asyncio
import time
from collections import deque

import aiohttp
from tqdm import tqdm

from .server_response import ServerResponse
from .utils import _url_valid

BITRIX_POOL_SIZE = 50
BITRIX_RPS = 2.0
BITRIX_MAX_BATCH_SIZE = 50


class ServerRequestHandler():
    '''
    Используется для контроля скорости доступа к серверам Битрикс.

    Основная цель - вести учет количества запросов, которые можно передать
    серверу Битрикс без получения ошибки `503`.

    Используется как контекстный менеджер, оборачивающий несколько
    последовательных запросов к серверу.
    '''


    def __init__(self, webhook, verbose):
        self.webhook = self._standardize_webhook(webhook)
        self._verbose = verbose

        self.requests_per_second = BITRIX_RPS
        self.pool_size = BITRIX_POOL_SIZE

        self.active_requests = set()
        self.session = None

        self.rr = deque() # rr - requests register - список отправленных запросов к серверу


    def _standardize_webhook(self, webhook):

        if not isinstance(webhook, str):
            raise TypeError(f'Webhook should be a {str}')

        webhook = webhook.lower().strip()

        if not _url_valid(webhook):
            raise ValueError('Webhook is not a valid URL')

        if webhook[-1] != '/':
            webhook += '/'

        return webhook


    def run(self, coroutine):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
            loop = asyncio.get_event_loop()

        return loop.run_until_complete(self.run_async(coroutine))


    async def run_async(self, coroutine):
        if not self.active_requests and (not self.session or self.session.closed):
            self.session = aiohttp.ClientSession(raise_for_status=True)

        self.active_requests.add(coroutine)

        result = await coroutine

        self.active_requests -= {coroutine}

        if not self.active_requests and self.session and not self.session.closed:
            await self.session.close()

        return result


    async def single_request(self, method, params=None):
        await self._acquire()
        async with self.session.post(url = self.webhook + method,
                                     json = params) as response:
            r = await response.json(encoding='utf-8')
        return ServerResponse(r)


    async def _acquire(self):
        '''Ожидает, пока не станет безопасно делать запрос к серверу.'''

        global _SLOW, _SLOW_RPS

        # если пул заполнен, ждать

        if _SLOW:
            await asyncio.sleep(1 / _SLOW_RPS)
        else:
            if len(self.rr) >= self.pool_size:
                time_from_last_request = time.monotonic() - self.rr[0]
                time_to_wait = 1 / self.requests_per_second - time_from_last_request
                if time_to_wait > 0:
                    await asyncio.sleep(time_to_wait)

        # зарегистрировать запрос

        cur_time = time.monotonic()
        self.rr.appendleft(cur_time)

        # подчистить пул

        trim_time = cur_time - self.pool_size / self.requests_per_second
        while self.rr and self.rr[len(self.rr) - 1] < trim_time:
            self.rr.pop()

        return


    def get_pbar(self, real_len, real_start):

        class MutePBar():

            def update(self, i):
                pass

            def close(self):
                pass

        if self._verbose:
            return tqdm(total = real_len, initial = real_start)
        else:
            return MutePBar()


_SLOW = False
_SLOW_RPS = 0


class slow:
    def __init__(self, requests_per_second = 0.5):
        global _SLOW_RPS
        _SLOW_RPS = requests_per_second

    def __enter__(self):
        global _SLOW
        _SLOW = True

    def __exit__(self, a1, a2, a3):
        global _SLOW, _SLOW_RPS
        _SLOW = False
        _SLOW_RPS = 0
