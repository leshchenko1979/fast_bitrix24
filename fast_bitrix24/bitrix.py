'''Высокоуровневый API для доступа к Битрикс24'''

import asyncio
import aiohttp
import time
import itertools
import more_itertools
from collections.abc import Sequence
import urllib

from tqdm import tqdm

from .correct_asyncio import *
from .utils import _bitrix_url, _merge_dict
from .user_request import GetAllUserRequest, GetByIDUserRequest, CallUserRequest

BITRIX_URI_MAX_LEN = 5820
BITRIX_MAX_BATCH_SIZE = 50
BITRIX_POOL_SIZE = 50
BITRIX_RPS = 2.0

##########################################
#
#   BitrixSemaphoreWrapper class
#
##########################################


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


    def __init__(self, webhook, pool_size: int, requests_per_second: float, verbose):
        self.webhook = webhook
        self._correct_webhook()
        self._verbose = verbose

        self._stopped_time = None
        self._stopped_value = None
        self.requests_per_second = requests_per_second
        self._pool_size = pool_size
        
        self.session = None


    def _correct_webhook(self):

        def _url_valid(url):
            try:
                result = urllib.parse.urlparse(url)
                return all([result.scheme, result.netloc, result.path])
            except:
                return False

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
            
    # TODO: лишний код, спрямить вызов из UserRequest
    async def _request_list(self, method, item_list, real_len=None, real_start=0, preserve_IDs=False):
        return await ListRequestHandler(self, method, item_list, real_len, real_start, preserve_IDs).run()


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


class ListRequestHandler:
    def __init__(self, srh, method, item_list, real_len=None, real_start=0, preserve_IDs=False):
        self.srh = srh
        self.method = method
        self.item_list = item_list
        self.pbar = srh.get_pbar(real_len if real_len else len(item_list), real_start)
        self.preserve_IDs = preserve_IDs
        self.original_item_list = item_list.copy()
        self.results = []
        self.tasks = []            
                
    async def run(self):
        if self.method != 'batch':
            self.prepare_batches()

        self.prepare_tasks()

        await self.get_results()

        if self.preserve_IDs:
            self.sort_results()
                        
        return self.results

    def prepare_batches(self):
        batch_size = BITRIX_MAX_BATCH_SIZE

        while True:
            batches = [{
                'halt': 0,
                'cmd': {
                    item[self.preserve_IDs] if self.preserve_IDs else f'cmd{i}': 
                    f'{self.method}?{_bitrix_url(item)}'
                    for i, item in enumerate(next_batch)
                }}
                for next_batch in more_itertools.chunked(self.item_list, batch_size)
            ]
            
            # проверяем длину получившегося URI
            uri_len = len(self.srh.webhook + 'batch' +
                            _bitrix_url(batches[0]))
            
            # и если слишком длинный, то уменьшаем размер батча
            # и уходим на перекомпоновку
            if uri_len > BITRIX_URI_MAX_LEN:
                batch_size = int(
                    batch_size // (uri_len / BITRIX_URI_MAX_LEN))
            else:
                break

        self.method = 'batch'
        self.item_list = batches


    def prepare_tasks(self):
        global _SLOW
        self.tasks = [asyncio.create_task(self.srh._request(self.method, i))
                    for i in self.item_list]
        if not _SLOW:
            self.tasks.append(asyncio.create_task(self.srh.release_sem()))


    async def get_results(self):
        tasks_to_process = len(self.item_list)

        for x in asyncio.as_completed(self.tasks):
            r, __ = await x
            self.results.extend(self.process_result(r))

            self.pbar.update(len(r))
            tasks_to_process -= 1
            if tasks_to_process == 0:
                break

        self.pbar.close()

    def process_result(self, r):
        if r['result_error']:
            raise RuntimeError(f'The server reply contained an error: {r["result_error"]}')
        if self.method == 'batch':
            if self.preserve_IDs:
                r = r['result'].items()
            else:
                r = list(r['result'].values())
                if type(r[0]) == list:
                    r = list(itertools.chain(*r))
        return r


    def sort_results(self):
        # выделяем ID для облегчения дальнейшего поиска
        IDs_only = [i[self.preserve_IDs] for i in self.original_item_list]
            
        # сортируем results на базе порядка ID в original_item_list
        self.results.sort(key = lambda item: 
            IDs_only.index(item[0]))


##########################################
#
#   Bitrix class
#
##########################################


class Bitrix:
    '''
    Класс, оборачивающий весь цикл запросов к серверу Битрикс24.

    Параметры:
    - webhook: str - URL вебхука, полученного от сервера Битрикс
    - verbose: bool = True - показывать ли прогрессбар при выполнении запроса

    Методы:
    - get_all(self, method: str, params: dict = None) -> list
    - get_by_ID(self, method: str, ID_list: Sequence, ID_field_name: str = 'ID', params: dict = None) -> list
    - call(self, method: str, item_list: Sequence) -> list
    '''

    def __init__(self, webhook: str, verbose: bool = True):
        '''
        Создает объект класса Bitrix.

        '''
        
        self.srh = ServerRequestHandler(webhook, BITRIX_POOL_SIZE, BITRIX_RPS, verbose)


    def get_all(self, method: str, params: dict = None) -> list:
        '''
        Получить полный список сущностей по запросу method.

        Под капотом использует параллельные запросы и автоматическое построение
        батчей, чтобы ускорить получение данных. Также самостоятельно
        обратывает постраничные ответы сервера, чтобы вернуть полный список.

        Параметры:
        - method - метод REST API для запроса к серверу
        - params - параметры для передачи методу. Используется именно тот формат,
                который указан в документации к REST API Битрикс24. get_all() не
                поддерживает параметры 'start', 'limit' и 'order'.

        Возвращает полный список сущностей, имеющихся на сервере,
        согласно заданным методу и параметрам.
        '''

        return GetAllUserRequest(self.srh, method, params).run()

    def get_by_ID(self, method: str, ID_list: Sequence, ID_field_name: str = 'ID',
        params: dict = None) -> list:
        '''
        Получить список сущностей по запросу method и списку ID.

        Используется для случаев, когда нужны не все сущности,
        имеющиеся в базе, а конкретный список поименованных ID.
        Например, все контакты, привязанные к сделкам.

        Параметры:
        - method - метод REST API для запроса к серверу
        - ID_list - список ID
        - ID_list_name - название поля, которе будет подаваться в запрос для 
            каждого элемента ID_list
        - params - параметры для передачи методу. Используется именно тот
            формат, который указан в документации к REST API Битрикс24

        Возвращает список кортежей вида:

            [
                (ID, <результат запроса>), 
                (ID, <результат запроса>), 
                ...
            ]

        Вторым элементом каждого кортежа будет результат выполнения запроса
        относительно этого ID. Это может быть, например, список связанных
        сущностей или пустой список, если не найдено ни одной привязанной
        сущности.
        '''

        return GetByIDUserRequest(self.srh, method, params, ID_list, ID_field_name).run()

    def call(self, method: str, item_list: Sequence) -> list:
        '''
        Вызвать метод REST API по списку.

        Параметры:
        - method - метод REST API
        - item_list - список параметров вызываемого метода

        Возвращает список ответов сервера для каждого из элементов item_list.
        '''

        return CallUserRequest(self.srh, method, item_list).run()
        
        
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
