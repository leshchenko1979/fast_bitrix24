import more_itertools
import asyncio
import itertools

from .utils import convert_dict_to_bitrix_url
from .srh import _SLOW, BITRIX_MAX_BATCH_SIZE

class MultipleServerRequestHandler:

    def __init__(self, srh, method, item_list, real_len=None, real_start=0):
        self.srh = srh
        self.method = method
        self.item_list = item_list
        self.pbar = srh.get_pbar(real_len if real_len else len(item_list), real_start)
        self.results = []
        self.tasks = []            

                
    async def run(self):
        if self.method != 'batch':
            self.prepare_batches()

        self.prepare_tasks()

        await self.get_results()

        return self.results


    def prepare_batches(self):
        batch_size = BITRIX_MAX_BATCH_SIZE

        while True:
            batches = [{
                'halt': 0,
                'cmd': {
                    self.batch_command_label(i, item): 
                    f'{self.method}?{convert_dict_to_bitrix_url(item)}'
                    for i, item in enumerate(next_batch)
                }}
                for next_batch in more_itertools.chunked(self.item_list, batch_size)
            ]
            
            URI_len_used = self.srh.URI_len_used('batch', batches[0])
            if URI_len_used < 1:
                break
            else:
                batch_size = int(batch_size // URI_len_used)

        self.method = 'batch'
        self.item_list = batches


    def batch_command_label(self, i, item):
        return f'cmd{i}'


    # TODO: переработать - prepare_tasks() не должна смотреть на _SLOW,
    # это должно происходить где-то в недрах ServerRequestHandler
    def prepare_tasks(self):
        global _SLOW
        self.tasks = [asyncio.create_task(self.srh.single_request(self.method, i))
                    for i in self.item_list]
        if not _SLOW:
            self.tasks.append(asyncio.create_task(self.srh.release_sem()))


    async def get_results(self):
        tasks_to_process = len(self.item_list)

        for x in asyncio.as_completed(self.tasks):
            r, __ = await x
            self.results.extend(self.process_response(r))

            self.pbar.update(len(r))
            tasks_to_process -= 1
            if tasks_to_process == 0:
                break

        self.pbar.close()


    def process_response(self, r):
        if r['result_error']:
            raise RuntimeError(f'The server reply contained an error: {r["result_error"]}')
        if self.method == 'batch':
            r = self.extract_result_from_batch(r)
        return r


    def extract_result_from_batch(self, r):
        r = list(r['result'].values())
        if type(r[0]) == list:
            r = list(itertools.chain(*r))
        return r


class MultipleServerRequestHandlerPreserveIDs(MultipleServerRequestHandler):

    def __init__(self, srh, method, item_list, ID_field):
        super().__init__(srh, method, item_list)
        self.ID_field = ID_field
        self.original_item_list = item_list.copy()
        

    async def run(self):
        await super().run()
        self.sort_results()
        return self.results
                        

    def batch_command_label(self, i, item):
        return item[self.ID_field]
    

    def extract_result_from_batch(self, r):
        return r['result'].items()


    def sort_results(self):
        # выделяем ID для облегчения дальнейшего поиска
        IDs_only = [i[self.ID_field] for i in self.original_item_list]
            
        # сортируем results на базе порядка ID в original_item_list
        self.results.sort(key = lambda item: 
            IDs_only.index(item[0]))