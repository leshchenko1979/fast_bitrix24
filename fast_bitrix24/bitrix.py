'''Высокоуровневый API для доступа к Битрикс24'''

from contextlib import asynccontextmanager, contextmanager
from typing import Iterable, Union

from . import correct_asyncio
from .srh import ServerRequestHandler
from .user_request import (BatchUserRequest, CallUserRequest,
                           GetAllUserRequest, GetByIDUserRequest,
                           ListAndGetUserRequest)


class BitrixAbstract(object):

    def __init__(self, webhook: str, verbose: bool = True,
                 respect_velocity_policy: bool = False):
        '''
        Создает объект класса Bitrix.

        Параметры:
        - `webhook: str` - URL вебхука, полученного от сервера Битрикс
        - `verbose: bool = True` - показывать ли прогрессбар при выполнении
        запроса
        - `respect_velocity_policy: bool = False` - соблюдать ли политику
        Битрикса о скорости запросов
        '''

        self.srh = ServerRequestHandler(webhook, respect_velocity_policy)
        self.verbose = verbose


class Bitrix(BitrixAbstract):
    '''Клиент для запросов к серверу Битрикс24.'''

    def get_all(self, method: str, params: dict = None) -> Union[list, dict]:
        '''
        Получить полный список сущностей по запросу `method`.

        Под капотом использует параллельные запросы и автоматическое построение
        батчей, чтобы ускорить получение данных. Также самостоятельно
        обратывает постраничные ответы сервера, чтобы вернуть полный список.

        Параметры:
        - `method` - метод REST API для запроса к серверу
        - `params` - параметры для передачи методу. Используется именно тот
            формат, который указан в документации к REST API Битрикс24.
            `get_all()` не поддерживает параметры `start`, `limit` и `order`.

        Возвращает полный список сущностей, имеющихся на сервере,
        согласно заданным методу и параметрам.
        '''

        return self.srh.run(GetAllUserRequest(self, method, params).run())

    def get_by_ID(self, method: str, ID_list: Iterable,
                  ID_field_name: str = 'ID', params: dict = None) -> dict:
        '''
        Получить список сущностей по запросу method и списку ID.

        Используется для случаев, когда нужны не все сущности,
        имеющиеся в базе, а конкретный список поименованных ID.
        Например, все контакты, привязанные к сделкам.

        Параметры:
        - `method` - метод REST API для запроса к серверу
        - `ID_list` - список ID
        - `ID_field_name` - название поля, которое будет подаваться в запрос
        для каждого элемента ID_list
        - `params` - параметры для передачи методу. Используется именно тот
        формат, который указан в документации к REST API Битрикс24

        Возвращает словарь вида:
        ```
        {
            ID_1: <результат запроса 1>,
            ID_2: <результат запроса 2>,
            ...
        }
        ```

        Значением элемента словаря будет результат выполнения запроса
        относительно этого ID. Это может быть, например, список связанных
        сущностей или пустой список, если не найдено ни одной привязанной
        сущности.
        '''

        return self.srh.run(GetByIDUserRequest(
            self, method, params, ID_list, ID_field_name).run())

    def list_and_get(self, method_branch: str, ID_field_name='ID') -> dict:
        '''
        Скачать список всех ID при помощи метода *.list,
        а затем все элементы при помощи метода *.get.

        Подобный подход показывает на порядок большую скорость
        получения данных, чем `get_all()`
        с параметром `'select': ['*', 'UF_*']`.

        Параметры:
        * `method_branch: str` - группа методов к использованию, например,
        `crm.lead` или `tasks.task`
        * `ID_field_name='ID'` - имя поля, в котором метод *.get принимает
        идентификаторы элементов (например, `'ID'` для метода `crm.lead.get`)

        Возвращает полное содержимое всех элементов в виде, используемом
        функцией `get_by_ID()` - словарь следующего вида:
        ```
        {
            ID_1: <словарь полей сущности с ID_1>,
            ID_2: <словарь полей сущности с ID_2>,
            ...
        }
        ```
        '''

        return self.srh.run(ListAndGetUserRequest(
            self, method_branch, ID_field_name).run())

    def call(self, method: str, items: Union[dict, Iterable]):
        '''
        Вызвать метод REST API по списку элементов.

        Параметры:
        - `method` - метод REST API
        - `items` - список параметров вызываемого метода
            либо dict с параметрами для единичного вызова

        Возвращает список ответов сервера для каждого из элементов `items`
        либо просто результат для единичного вызова.
        '''

        return self.srh.run(CallUserRequest(self, method, items).run())

    def call_batch(self, params: dict) -> dict:
        '''
        Вызвать метод `batch`.

        Параметры:
        - `params` - список параметров вызываемого метода

        Возвращает ответы сервера в формате словаря, где ключ - название
        команды, а значение - ответ сервера по этой команде.
        '''

        return self.srh.run(BatchUserRequest(self, params).run())

    @contextmanager
    def slow(self, max_concurrent_requests: int = 1):
        '''Временно ограничивает количество одновременно выполняемых запросов
        к Битрикс24.'''

        if not isinstance(max_concurrent_requests, int):
            raise 'slow() argument should be only int'
        if max_concurrent_requests < 1:
            raise 'slow() argument should be >= 1'

        mcr_max_backup, self.srh.mcr_max = \
            self.srh.mcr_max, max_concurrent_requests
        self.srh.mcr_cur_limit = min(self.srh.mcr_max, self.srh.mcr_cur_limit)

        yield True

        self.srh.mcr_max = mcr_max_backup
        self.srh.mcr_cur_limit = min(self.srh.mcr_max, self.srh.mcr_cur_limit)


class BitrixAsync(BitrixAbstract):
    '''Класс, повторяющий интерфейс класса `Bitrix`,
    но с асинхронными методами.'''

    async def get_all(self, method: str, params: dict = None) -> \
            Union[list, dict]:
        '''
        Получить полный список сущностей по запросу `method`.

        Под капотом использует параллельные запросы и автоматическое построение
        батчей, чтобы ускорить получение данных. Также самостоятельно
        обратывает постраничные ответы сервера, чтобы вернуть полный список.

        Параметры:
        - `method` - метод REST API для запроса к серверу
        - `params` - параметры для передачи методу. Используется
            именно тот формат, который указан в документации к REST API
            Битрикс24. `get_all()` не поддерживает параметры
            `start`, `limit` и `order`.

        Возвращает полный список сущностей, имеющихся на сервере,
        согласно заданным методу и параметрам.
        '''

        return await self.srh.run_async(
            GetAllUserRequest(self, method, params).run())

    async def get_by_ID(self, method: str, ID_list: Iterable,
                        ID_field_name: str = 'ID',
                        params: dict = None) -> list:
        '''
        Получить список сущностей по запросу `method` и списку ID.

        Используется для случаев, когда нужны не все сущности,
        имеющиеся в базе, а конкретный список поименованных ID.
        Например, все контакты, привязанные к сделкам.

        Параметры:
        - `method` - метод REST API для запроса к серверу
        - `ID_list` - список ID
        - `ID_field_name` - название поля, которое будет подаваться в запрос
        для каждого элемента ID_list
        - `params` - параметры для передачи методу. Используется именно тот
        формат, который указан в документации к REST API Битрикс24

        Возвращает словарь вида:
        ```
        {
            ID_1: <результат запроса 1>,
            ID_2: <результат запроса 2>,
            ...
        }
        ```

        Значением элемента словаря будет результат выполнения запроса
        относительно этого ID. Это может быть, например, список связанных
        сущностей или пустой список, если не найдено ни одной привязанной
        сущности.
        '''

        return await self.srh.run_async(GetByIDUserRequest(
            self, method, params, ID_list, ID_field_name).run())

    async def list_and_get(self, method_branch: str,
                           ID_field_name='ID') -> dict:
        '''
        Скачать список всех ID при помощи метода *.list,
        а затем все элементы при помощи метода *.get.

        Подобный подход показывает на порядок большую скорость
        получения данных, чем `get_all()`
        с параметром `'select': ['*', 'UF_*']`.

        Параметры:
        * `method_branch: str` - группа методов к использованию, например,
        `crm.lead` или `tasks.task`
        * `ID_field_name='ID'` - имя поля, в котором метод *.get принимает
        идентификаторы элементов (например, `'ID'` для метода `crm.lead.get`)

        Возвращает полное содержимое всех элементов в виде, используемом
        функцией `get_by_ID()` - словарь следующего вида:
        ```
        {
            ID_1: <словарь полей сущности с ID_1>,
            ID_2: <словарь полей сущности с ID_2>,
            ...
        }
        ```
        '''

        return await ListAndGetUserRequest(
            self, method_branch, ID_field_name=ID_field_name).run()

    async def call(self, method: str, items: Union[dict, Iterable]):
        '''
        Вызвать метод REST API по списку элементов.

        Параметры:
        - `method` - метод REST API
        - `items` - список параметров вызываемого метода
            либо dict с параметрами для единичного вызова

        Возвращает список ответов сервера для каждого из элементов `items`
        либо просто результат для единичного вызова.
        '''

        return await self.srh.run_async(
            CallUserRequest(self, method, items).run())

    async def call_batch(self, params: dict) -> dict:
        '''
        Вызвать метод `batch`.

        Параметры:
        - `params` - список параметров вызываемого метода

        Возвращает ответы сервера в формате словаря, где ключ - название
        команды, а значение - ответ сервера по этой команде.
        '''

        return await self.srh.run_async(
            BatchUserRequest(self, params).run())

    @asynccontextmanager
    async def slow(self, max_concurrent_requests: int = 1):
        '''Временно ограничивает количество одновременно выполняемых запросов
        к Битрикс24.'''

        if not isinstance(max_concurrent_requests, int):
            raise 'slow() argument should be only int'
        if max_concurrent_requests < 1:
            raise 'slow() argument should be >= 1'

        mcr_max_backup, self.srh.mcr_max = \
            self.srh.mcr_max, max_concurrent_requests
        self.srh.mcr_cur_limit = min(self.srh.mcr_max, self.srh.mcr_cur_limit)

        yield True

        self.srh.mcr_max = mcr_max_backup
        self.srh.mcr_cur_limit = min(self.srh.mcr_max, self.srh.mcr_cur_limit)
