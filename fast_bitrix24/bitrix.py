'''Высокоуровневый API для доступа к Битрикс24'''

import urllib.parse
import asyncio
import aiohttp
import time
import itertools
import more_itertools
import pickle
import warnings
from collections.abc import Iterable

from tqdm import tqdm

import fast_bitrix24.correct_asyncio

BITRIX_URI_MAX_LEN = 5820
BITRIX_MAX_BATCH_SIZE = 50
BITRIX_POOL_SIZE = 50
BITRIX_RPS = 2.0

##########################################
#
#   BitrixSemaphoreWrapper class
#
##########################################


class BitrixSemaphoreWrapper():
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


    def __init__(self, pool_size: int, requests_per_second: float):
        self._stopped_time = None
        self._stopped_value = None
        self.requests_per_second = requests_per_second
        self._pool_size = pool_size

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


    async def __aexit__(self, a1, a2, a3):
        self._stopped_time = time.monotonic()
        
        if _SLOW:
            # в slow-режиме обнуляем пул запросов, чтобы после выхода
            # не выдать на сервер пачку запросов и не словить отказ
            self._stopped_value = 0
        else:
            self._stopped_value = self._sem._value


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
    - get_all(self, method: str, details=None)
    - get_by_ID(self, method: str, ID_list, details=None)
    - call(self, method: str, item_list)
    '''

    def __init__(self, webhook: str, verbose: bool = True):
        '''
        Создает объект класса Bitrix.

        '''
        
        self.webhook = _correct_webhook(webhook)
        self._sw = BitrixSemaphoreWrapper(BITRIX_POOL_SIZE, BITRIX_RPS)
        self._autobatch = True
        self._verbose = verbose


    async def _request(self, session, method, params=None, pbar=None):
        await self._sw.acquire()
        url = f'{self.webhook}{method}?{_bitrix_url(params)}'
        async with session.get(url) as response:
            r = await response.json(encoding='utf-8')
        if pbar:
            pbar.update(len(r['result']))
        return r['result'], (r['total'] if 'total' in r.keys() else None)


    async def _request_list(self, method, item_list, real_len=None, real_start=0, preserve_IDs=False):
        if not real_len:
            real_len = len(item_list)

        if (self._autobatch) and (method != 'batch'):

            batch_size = BITRIX_MAX_BATCH_SIZE
            while True:
                batches = [{
                    'halt': 0,
                    'cmd': {
                        item['ID'] if preserve_IDs else f'cmd{i}': 
                        f'{method}?{_bitrix_url(item)}'
                        for i, item in enumerate(next_batch)
                    }}
                    for next_batch in more_itertools.chunked(item_list, batch_size)
                ]
                uri_len = len(self.webhook + 'batch' +
                              urllib.parse.urlencode(batches[0]))
                if uri_len > BITRIX_URI_MAX_LEN:
                    batch_size = int(
                        batch_size // (uri_len / BITRIX_URI_MAX_LEN))
                else:
                    break

            method = 'batch'
            item_list = batches

        async with self._sw, aiohttp.ClientSession(raise_for_status=True) as session:
            global _SLOW
            tasks = [asyncio.create_task(self._request(session, method, i))
                        for i in item_list]
            if not _SLOW:
                tasks.append(asyncio.create_task(self._sw.release_sem()))

            if self._verbose:
                pbar = tqdm(total=real_len, initial=real_start)
            results = []
            tasks_to_process = len(item_list)
            for x in asyncio.as_completed(tasks):
                r, __ = await x
                if r['result_error']:
                    raise RuntimeError(f'The server reply contained an error: {r["result_error"]}')
                if method == 'batch':
                    if preserve_IDs:
                        r = r['result'].items()
                    else:
                        r = list(r['result'].values())
                        if type(r[0]) == list:
                            r = list(itertools.chain(*r))
                results.extend(r)
                if self._verbose:
                    pbar.update(len(r))
                tasks_to_process -= 1
                if tasks_to_process == 0:
                    break
            if self._verbose:
                pbar.close()
            return results

    async def _get_paginated_list(self, method, params=None):
        if params:
            if 'order' not in [x.lower() for x in params.keys()]:
                params.update({'order': {'ID': 'ASC'}})
        else:
            params = {'order': {'ID': 'ASC'}}

        async with self._sw, aiohttp.ClientSession(raise_for_status=True) as session:
            results, total = await self._request(session, method, params)
            if not total or total <= 50:
                return results

            results.extend(await self._request_list(method, [
                _merge_dict({'start': start}, params)
                for start in range(len(results), total, 50)
            ], total, len(results)))

        # дедупликация через сериализацию, превращение в set и десериализацию
        results = [pickle.loads(y) for y in set([pickle.dumps(x) for x in results])] \
            if results else []

        if len(results) != total:
            warnings.warn(f"Number of results returned ({len(results)}) "
                "doesn't equal 'total' from the server reply ({total})",
                RuntimeWarning)

        return results


    def get_all(self, method: str, params=None):
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

        if params:
            _check_params(params)
            for k in params.keys():
                if k.lower() in ['start', 'limit', 'order']:
                    raise ValueError("get_all() doesn't support parameters 'start', 'limit' or 'order'")

        return asyncio.run(self._get_paginated_list(method, params))

    def get_by_ID(self, method: str, ID_list: Iterable, params=None):
        '''
        Получить список сущностей по запросу method и списку ID.

        Используется для случаев, когда нужны не все сущности,
        имеющиеся в базе, а конкретный список поименованных ID.
        Например, все контакты, привязанные к сделкам.

        Параметры:
        - method - метод REST API для запроса к серверу
        - ID_list - список ID
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

        if params: 
            _check_params(params)
            for k in params.keys():
                if k.lower() == 'id':
                    raise ValueError("get_by_ID() doesn't support parameter 'ID' within the 'params' argument")

        if not isinstance(ID_list, Iterable):
            raise TypeError("get_by_ID(): 'ID_list' should be iterable")

        if len(ID_list) == 0:
            return []
        return asyncio.run(self._request_list(
            method,
            [_merge_dict({'ID': ID}, params) for ID in ID_list] if params else
            [{'ID': ID} for ID in set(ID_list)],
            preserve_IDs=True
        ))

    def call(self, method: str, item_list: Iterable):
        '''
        Вызвать метод REST API по списку.

        Параметры:
        - method - метод REST API
        - item_list - список параметров вызываемого метода

        Возвращает список ответов сервера для каждого из элементов item_list.
        '''
        if len(item_list) == 0:
            return []

        try:
            [_check_params(p) for p in item_list]
        except (TypeError, ValueError) as err:
            raise ValueError(
                'item_list contains items with incorrect method params') from err 

        if not isinstance(item_list, Iterable):
            raise TypeError("get_by_ID(): 'item_list' should be iterable")

        return asyncio.run(self._request_list(method, item_list))


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


##########################################
#
#   internal functions
#
##########################################


def _bitrix_url(data):
    parents = list()
    pairs = list()

    def renderKey(parents):
        depth, outStr = 0, ''
        for x in parents:
            s = "[%s]" if (depth > 0 or isinstance(x, int)) and x!='[]' else "%s"
            outStr += s % str(x)
            depth += 1
        return outStr

    def r_urlencode(data):
        if any(isinstance(data, t) for t in [list, tuple, set]):
            data = list(data)
            for i in range(len(data)):
                parents.append('[]')
                r_urlencode(data[i])
                parents.pop()
        elif isinstance(data, dict):
            for key, value in data.items():
                parents.append(key)
                r_urlencode(value)
                parents.pop()
        else:
            pairs.append((renderKey(parents), str(data)))

        return pairs
    return urllib.parse.urlencode(r_urlencode(data))


def _merge_dict(d1, d2):
    d3 = d1.copy()
    if d2:
        d3.update(d2)
    return d3

def _check_params(p):

    # check if p is dict
    if not isinstance(p, dict):
        raise TypeError('params agrument should be a dict')

    # check for allowed keys
    clauses = {
        'select': list,
        'halt': int,
        'cmd': dict,
        'limit': int,
        'order': dict,
        'filter': dict,
        'start': int,
        'fields': dict
    }

#    for pk in p.keys():
#        if pk.lower() not in clauses.keys():
#            raise ValueError(f'Unknown clause "{pk}" in params argument')

    # check for allowed types of key values
    for pi in p.items():
        if pi[0] in clauses.keys():
            t = clauses[pi[0].lower()]
            if t and not (
                (isinstance(pi[1], t)) or
                ((t == list) and (any([isinstance(pi[1], x) for x in [list, tuple, set]])))
            ):
                raise TypeError(f'Clause "{pi[0]}" should be of type {t}, '
                    'but its type is {type(pi[1])}')


def _url_valid(url):
    try:
        result = urllib.parse.urlparse(url)
        return all([result.scheme, result.netloc, result.path])
    except:
        return False


def _correct_webhook(wh):
    if not isinstance(wh, str):
        raise TypeError(f'Webhook should be a {str}')
    if not _url_valid(wh):
        raise ValueError('Webhook is not a valid URL')
    return wh if wh[-1] == '/' else wh + '/'
