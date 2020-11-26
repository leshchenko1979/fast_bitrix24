'''Высокоуровневый API для доступа к Битрикс24'''

from collections.abc import Sequence

from .correct_asyncio import *
from .srh import ServerRequestHandler, slow
from .user_request import (BatchUserRequest, CallUserRequest,
                           GetAllUserRequest, GetByIDUserRequest)


class Bitrix:
    '''Клиент для запросов к серверу Битрикс24.'''

    '''
    Параметры:
    - `webhook: str` - URL вебхука, полученного от сервера Битрикс
    - `verbose: bool = True` - показывать ли прогрессбар при выполнении запроса
    '''

    def __init__(self, webhook: str, verbose: bool = True):
        '''
        Создает объект класса Bitrix.

        '''

        self.srh = ServerRequestHandler(webhook, verbose)


    def get_all(self, method: str, params: dict = None) -> list:
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

        return self.srh.run(GetAllUserRequest(self.srh, method, params).run())


    def get_by_ID(self, method: str, ID_list: Sequence,
                  ID_field_name: str = 'ID', params: dict = None) -> list:
        '''
        Получить список сущностей по запросу method и списку ID.

        Используется для случаев, когда нужны не все сущности,
        имеющиеся в базе, а конкретный список поименованных ID.
        Например, все контакты, привязанные к сделкам.

        Параметры:
        - `method` - метод REST API для запроса к серверу
        - `ID_list` - список ID
        - `ID_list_name` - название поля, которе будет подаваться в запрос для
            каждого элемента ID_list
        - `params` - параметры для передачи методу. Используется именно тот
            формат, который указан в документации к REST API Битрикс24

        Возвращает список кортежей вида:
        ```
            [
                (ID, <результат запроса>),
                (ID, <результат запроса>),
                ...
            ]
        ```

        Вторым элементом каждого кортежа будет результат выполнения запроса
        относительно этого ID. Это может быть, например, список связанных
        сущностей или пустой список, если не найдено ни одной привязанной
        сущности.
        '''

        return self.srh.run(GetByIDUserRequest(
            self.srh, method, params, ID_list, ID_field_name).run())


    def call(self, method: str, items):
        '''
        Вызвать метод REST API по списку элементов.

        Параметры:
        - `method` - метод REST API
        - `items` - список параметров вызываемого метода
            либо dict с параметрами для единичного вызова

        Возвращает список ответов сервера для каждого из элементов `items`
        либо просто результат для единичного вызова.
        '''

        if isinstance(items, Sequence):
            func = CallUserRequest(self.srh, method, items).run()
            return self.srh.run(func)
        elif isinstance(items, dict):
            func = CallUserRequest(self.srh, method, [items]).run()
            result = self.srh.run(func)
            return result[0]
        else:
            raise TypeError(
                f'call() accepts either a list of params dicts or '
                f'a single params dict, but got a {type(items)} instead')


    def call_batch(self, params: dict) -> dict:
        '''
        Вызвать метод `batch`.

        Параметры:
        - `params` - список параметров вызываемого метода

        Возвращает ответы сервера в формате словаря, где ключ - название
        команды, а значение - ответ сервера по этой команде.
        '''

        return self.srh.run(BatchUserRequest(self.srh, params).run())


class BitrixAsync:
    '''
    Класс, повторяющий интерфейс класса `Bitrix`, но с асинхронными методами.

    Параметры:
    - `webhook: str` - URL вебхука, полученного от сервера Битрикс
    - `verbose: bool = True` - показывать ли прогрессбар при выполнении запроса
    '''

    def __init__(self, webhook: str, verbose: bool = True):
        '''
        Создает объект класса Bitrix.

        '''

        self.srh = ServerRequestHandler(webhook, verbose)


    async def get_all(self, method: str, params: dict = None) -> list:
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
            GetAllUserRequest(self.srh, method, params).run())


    async def get_by_ID(self, method: str, ID_list: Sequence,
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
        - `ID_list_name` - название поля, которе будет подаваться в запрос для
            каждого элемента ID_list
        - `params` - параметры для передачи методу. Используется именно тот
            формат, который указан в документации к REST API Битрикс24

        Возвращает список кортежей вида:
        ```
            [
                (ID, <результат запроса>),
                (ID, <результат запроса>),
                ...
            ]
        ```
        Вторым элементом каждого кортежа будет результат выполнения запроса
        относительно этого ID. Это может быть, например, список связанных
        сущностей или пустой список, если не найдено ни одной привязанной
        сущности.
        '''

        return await self.srh.run_async(GetByIDUserRequest(
            self.srh, method, params, ID_list, ID_field_name).run())


    async def call(self, method: str, items):
        '''
        Вызвать метод REST API по списку элементов.

        Параметры:
        - `method` - метод REST API
        - `items` - список параметров вызываемого метода
            либо dict с параметрами для единичного вызова

        Возвращает список ответов сервера для каждого из элементов `items`
        либо просто результат для единичного вызова.
        '''

        if isinstance(items, Sequence):
            func = CallUserRequest(self.srh, method, items).run()
            return await self.srh.run_async(func)

        elif isinstance(items, dict):
            func = CallUserRequest(self.srh, method, [items]).run()
            result = await self.srh.run_async(func)
            return result[0]

        else:
            raise TypeError(
                'call() accepts either a list of params dicts or '
                f'a single params dict, but got a {type(items)} instead')


    async def call_batch(self, params: dict) -> dict:
        '''
        Вызвать метод `batch`.

        Параметры:
        - `params` - список параметров вызываемого метода

        Возвращает ответы сервера в формате словаря, где ключ - название
        команды, а значение - ответ сервера по этой команде.
        '''

        return await self.srh.run_async(
            BatchUserRequest(self.srh, params).run())
