import more_itertools
import asyncio
import itertools

from .utils import _bitrix_url
from .srh import _SLOW

BITRIX_URI_MAX_LEN = 5820
BITRIX_MAX_BATCH_SIZE = 50

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

