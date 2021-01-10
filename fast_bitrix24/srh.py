import asyncio
from asyncio import sleep, Event
import time
from collections import deque
from contextlib import asynccontextmanager

import aiohttp
from aiohttp.client_exceptions import (ClientPayloadError, ClientResponseError,
                                       ServerDisconnectedError)
from tqdm import tqdm

from .server_response import ServerResponse
from .utils import _url_valid


BITRIX_POOL_SIZE = 50
BITRIX_RPS = 2.0
BITRIX_MAX_BATCH_SIZE = 50
BITRIX_MAX_CONCURRENT_REQUESTS = 50

MAX_RETRIES = 10

RESTORE_CONNECTIONS_FACTOR = 1.3  # скорость восстановления количества запросов
DECREASE_CONNECTIONS_FACTOR = 3  # скорость уменьшения количества запросов
INITIAL_TIMEOUT = 0.5  # начальный таймаут в секундах
BACKOFF_FACTOR = 1.5  # основа расчета таймаута
# количество ошибок, до достижения котрого таймауты не делаются
NUM_FAILURES_NO_TIMEOUT = 3


class ServerError(Exception):
    pass


class ServerRequestHandler():
    '''
    Используется для контроля скорости доступа к серверам Битрикс.

    Основная цель - вести учет количества запросов, которые можно передать
    серверу Битрикс без получения ошибки `5XX`.

    Используется как контекстный менеджер, оборачивающий несколько
    последовательных запросов к серверу.
    '''

    def __init__(self, webhook):
        self.webhook = self._standardize_webhook(webhook)

        self.requests_per_second = BITRIX_RPS
        self.pool_size = BITRIX_POOL_SIZE

        self.active_runs = 0
        self.session = None

        # rr - requests register - список отправленных запросов к серверу
        self.rr = deque()

        # лимит количества одновременных запросов,
        # установленный конструктором или пользователем
        self.mcr_max = BITRIX_MAX_CONCURRENT_REQUESTS

        # временный лимит количества одновременных запросов,
        # установленный через autothrottling
        self.mcr_cur_limit = BITRIX_MAX_CONCURRENT_REQUESTS

        self.concurrent_requests = 0
        self.request_complete = Event()

        # если положительное - количество последовательных удачных запросов
        # если отрицательное - количество последовательно полученных ошибок
        self.successive_results = 0

    @staticmethod
    def _standardize_webhook(webhook):
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

        try:
            yield True

        finally:
            self.active_runs -= 1
            if not self.active_runs and self.session and \
                    not self.session.closed:
                await self.session.close()

    async def single_request(self, method, params=None):
        '''Делает единичный запрос к серверу, повторяя при необходимости.'''

        while True:
            try:
                return await self.inner_single_request(method, params)
            except (ClientPayloadError, ServerDisconnectedError, ServerError):
                self.failure()
                if self.successive_results < -MAX_RETRIES:
                    raise

    async def inner_single_request(self, method, params=None):
        '''Делает единичный запрос к серверу, ожидая при необходимости.'''
        try:
            async with self.acquire(), self.session.post(
                    url=self.webhook + method, json=params) as response:
                self.success()
                return ServerResponse(await response.json(encoding='utf-8'))
        except ClientResponseError as error:
            if error.status // 100 == 5:  # ошибки вида 5XX
                raise ServerError('The server returned an error') from error
            else:
                raise

    def success(self):
        self.successive_results = max(self.successive_results + 1, 1)

    def failure(self):
        self.successive_results = min(self.successive_results - 1, -1)

    @asynccontextmanager
    async def acquire(self):
        '''Ожидает, пока не станет безопасно делать запрос к серверу.'''

        await self.autothrottle()

        async with self.limit_concurrent_requests():
            # если пул заполнен, ждать
            if len(self.rr) >= self.pool_size:
                time_from_last_request = time.monotonic() - self.rr[0]
                time_to_wait = 1 / self.requests_per_second - \
                    time_from_last_request
                if time_to_wait > 0:
                    await sleep(time_to_wait)

            # зарегистрировать запрос в очереди
            cur_time = time.monotonic()
            self.rr.appendleft(cur_time)

            # отдать управление
            try:
                yield

            # подчистить пул
            finally:
                trim_time = cur_time - \
                    self.pool_size / self.requests_per_second
                while self.rr and self.rr[len(self.rr) - 1] < trim_time:
                    self.rr.pop()

    async def autothrottle(self):
        '''Если было несколько неудач, делаем таймаут и уменьшаем скорость и количество
        одновременных запросов, и наоборот.'''

        if self.successive_results > 0:

            self.mcr_cur_limit = min(
                self.mcr_cur_limit * RESTORE_CONNECTIONS_FACTOR, self.mcr_max)

        elif self.successive_results < 0:

            self.mcr_cur_limit = max(
                self.mcr_cur_limit / DECREASE_CONNECTIONS_FACTOR, 1)

            if self.successive_results < NUM_FAILURES_NO_TIMEOUT:
                power = -self.successive_results - NUM_FAILURES_NO_TIMEOUT - 1
                await sleep(INITIAL_TIMEOUT * BACKOFF_FACTOR ** power)

    @asynccontextmanager
    async def limit_concurrent_requests(self):
        '''Не позволяет оновременно выполнять
        более `self.mcr_cur_limit` запросов.'''

        while self.concurrent_requests > self.mcr_cur_limit:
            self.request_complete.clear()
            await self.request_complete.wait()

        self.concurrent_requests += 1

        try:
            yield

        finally:
            self.concurrent_requests -= 1
            self.request_complete.set()
