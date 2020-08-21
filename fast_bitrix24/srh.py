import asyncio
import aiohttp
import time

from tqdm import tqdm

from .utils import _bitrix_url, _url_valid

BITRIX_POOL_SIZE = 50
BITRIX_RPS = 2.0

class ServerRequestHandler():
    '''
    Используется для контроля скорости доступа к серверам Битрикс.

    Основная цель - вести учет количества запросов, которые можно передать
    серверу Битрикс без получения ошибки `503`.

    Используется как контекстный менеджер, оборачивающий несколько
    последовательных запросов к серверу.

    Чтобы все работало, нужно, чтобы внутри метода класса `Bitrix`, в котором
    используется этот семафор, выполнял параллельно по совими задачами и
    корутину-метод `release_sem()`.
        
    Параметры:
    - pool_size: int - размер пула доступных запросов.
    - requests_per_second: int - скорость подачи запросов.

    Методы:
    - acquire(self)
    - release_sem(self)
    '''


    def __init__(self, webhook, verbose):
        self.webhook = webhook
        self._correct_webhook()
        self._verbose = verbose

        self._stopped_time = None
        self._stopped_value = None
        self.requests_per_second = BITRIX_RPS
        self._pool_size = BITRIX_POOL_SIZE
        
        self.session = None


    def _correct_webhook(self):

        if not isinstance(self.webhook, str):
            raise TypeError(f'Webhook should be a {str}')

        if not _url_valid(self.webhook):
            raise ValueError('Webhook is not a valid URL')

        if self.webhook[-1] != '/':
            self.webhook += '/'


    async def __aenter__(self):
        global _SLOW
        self._sem = asyncio.BoundedSemaphore(self._pool_size)
        if _SLOW:
            self._slow_lock = asyncio.Lock()
        else:
            if self._stopped_time:
                '''
-----v-----------------------------v---------------------
     ^ - _stopped_time             ^ - current time
     |-------- time_passed --------|
     |- step -|- step -|- step |          - add_steps (whole steps to add)
                               |- step -| - additional 1 step added
                                   |-aw-| - additional waiting time
                '''
                time_passed = time.monotonic() - self._stopped_time

                # сколько шагов должно было пройти
                add_steps = time_passed / self.requests_per_second // 1

                # сколько шагов могло пройти с учетом ограничений + еще один
                real_add_steps = min(self._pool_size - self._stopped_value,
                                    add_steps + 1)

                # добавляем пропущенные шаги
                self._sem._value += real_add_steps

                # ждем время, излишне списанное при добавлении дополнительного шага
                await asyncio.sleep((add_steps + 1) / self.requests_per_second - time_passed)

                self._stopped_time = None
                self._stopped_value = None

        self.get_session()


    async def __aexit__(self, a1, a2, a3):
        self._stopped_time = time.monotonic()
        
        if _SLOW:
            # в slow-режиме обнуляем пул запросов, чтобы после выхода
            # не выдать на сервер пачку запросов и не словить отказ
            self._stopped_value = 0
        else:
            self._stopped_value = self._sem._value

        await self.close_session()


    async def release_sem(self):
        '''
        Корутина-метод, которая увеличивает счетчик доступных в пуле запросов.

        Должна запускаться единожды в параллели со всеми другими задачами
        внутри основного цикла `Bitrix._request_list`, кроме случаев
        выполнения в slow-режиме, когда она запускаться на должна.
        '''

        while True:
            if self._sem._value < self._sem._bound_value:
                self._sem.release()
            await asyncio.sleep(1 / self.requests_per_second)


    async def acquire(self):
        '''
        Вызов `await acquire()` должен предшествовать любому обращению
        к серверу Битрикс. Он возвращает `True`, когда к серверу
        можно осуществить запрос.

        Использование:
        ```
        await self.aquire()
        # теперь можно делать запросы
        ...
        ```
        '''
        global _SLOW, _SLOW_RPS
        if _SLOW:
            # ждать, пока отработают другие запросы, запущенные параллельно,
            async with self._slow_lock:
            # потом ждать основное время "остывания"
                await asyncio.sleep(1 / _SLOW_RPS)
            return True 
        else:
            return await self._sem.acquire()


    async def _request(self, method, params=None):
        await self.acquire()
        url = f'{self.webhook}{method}?{_bitrix_url(params)}'
        async with self.session.get(url) as response:
            r = await response.json(encoding='utf-8')
        if 'result_error' in r.keys():
            raise RuntimeError(f'The server reply contained an error: {r["result_error"]}')
        return r['result'], (r['total'] if 'total' in r.keys() else None)


    def get_session(self):
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(raise_for_status=True)


    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
            

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

        
##########################################
#
#   slow() context manager
#
##########################################

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
