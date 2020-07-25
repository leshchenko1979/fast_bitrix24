import urllib.parse

import asyncio
import aiohttp
import time
import itertools

from tqdm import tqdm

import fast_bitrix24.correct_asyncio

##########################################
#
#   SemaphoreWrapper class
#
##########################################


class SemaphoreWrapper():

    def __init__(self, custom_pool_size, cautious):
        if cautious:
            self._stopped_time = time.monotonic()
            self._stopped_value = 0
        else:
            self._stopped_time = None
            self._stopped_value = None
        self._REQUESTS_PER_SECOND = 2
        self._pool_size = custom_pool_size


    async def __aenter__(self):
        self._sem = asyncio.BoundedSemaphore(self._pool_size)
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
            add_steps = time_passed / self._REQUESTS_PER_SECOND // 1
            
            # сколько шагов могло пройти с учетом ограничений + еще один
            real_add_steps = min(self._pool_size - self._stopped_value, 
                 add_steps + 1)

            # добавляем пропущенные шаги
            self._sem._value += real_add_steps
                      
            # ждем время, излишне списанное при добавлении дополнительного шага
            await asyncio.sleep((add_steps + 1) / self._REQUESTS_PER_SECOND - time_passed)

            self._stopped_time = None
            self._stopped_value = None

        self.release_task = asyncio.create_task(self._release_sem())


    async def __aexit__(self, a1, a2, a3):
        self._stopped_time = time.monotonic()
        self._stopped_value = self._sem._value
        self.release_task.cancel()


    async def _release_sem(self):
        while True:
            if self._sem._value < self._sem._bound_value:
                self._sem.release()
            await asyncio.sleep(1 / self._REQUESTS_PER_SECOND)


    async def acquire(self):
        return await self._sem.acquire()


##########################################
#
#   Bitrix class
#
##########################################


class Bitrix:
    def __init__(self, webhook, custom_pool_size = 50, cautious=False, auto_batch=True):
        self.webhook = webhook
        self._sw = SemaphoreWrapper(custom_pool_size, cautious)
        self._autobatch = auto_batch

    
    async def _request(self, session, method, details = None, pbar = None):
        await self._sw.acquire()
        url = f'{self.webhook}{method}?{http_build_query(details)}'
        async with session.get(url) as response:
            r = await response.json(encoding='utf-8')
        if pbar:
            pbar.update(len(r['result']))
        return r['result'], (r['total'] if 'total' in r.keys() else None)


    async def _request_list (self, method, item_list, real_len = None, real_start = 0):
        async with self._sw, aiohttp.ClientSession(raise_for_status=True) as session:
            if len(item_list) == 1:
                r, __ = await self._request(session, method, item_list[0])
                return [r]
            if not real_len:
                real_len = len(item_list)
            with tqdm(total=real_len, initial=real_start) as pbar:
                tasks = [asyncio.create_task(self._request(
                    session, method, i, pbar)) for i in item_list]
                results = []
                for x in asyncio.as_completed((*tasks, self._sw.release_task)):
                    r, __ = await x
                    results.append(r)
                    if len(results) == len(item_list):
                        return results


    async def _get_paginated_list(self, method, details=None):
        async with self._sw, aiohttp.ClientSession(raise_for_status=True) as session:
            results, total = await self._request(session, method, details)
            if not total or total <= 50:
                return results
            remaining_results = await self._request_list(method, [
                details.update({'start': start}) if details else {'start': start} \
                for start in range(len(results), total, 50)
            ], total, len(results))
            results = [dict(t) for t in {
                tuple(d.items()) for d in itertools.chain(results, *remaining_results)
            }] 
            return results
        

    def get_list(self, method, details=None):
        return asyncio.run(self._get_paginated_list(method, details))


    def get_items_by_ID_list(self, method, ID_list, details = None):
        return asyncio.run(self._request_list(method, 
            [details.copy().update({'ID': ID}) for ID in ID_list] if details else \
            [{'ID': ID} for ID in ID_list]
        ))


    def post_list(self, method, item_list):
        return asyncio.run(self._request_list(method, item_list))


##########################################
#
#   internal functions
#
##########################################


def http_build_query(data):
    parents = list()
    pairs = dict()

    def renderKey(parents):
        depth, outStr = 0, ''
        for x in parents:
            s = "[%s]" if depth > 0 or isinstance(x, int) else "%s"
            outStr += s % str(x)
            depth += 1
        return outStr

    def r_urlencode(data):
        if isinstance(data, list) or isinstance(data, tuple):
            for i in range(len(data)):
                parents.append(i)
                r_urlencode(data[i])
                parents.pop()
        elif isinstance(data, dict):
            for key, value in data.items():
                parents.append(key)
                r_urlencode(value)
                parents.pop()
        else:
            pairs[renderKey(parents)] = str(data)

        return pairs
    return urllib.parse.urlencode(r_urlencode(data))
