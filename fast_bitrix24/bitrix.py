'''Высокоуровневый API для доступа к Битрикс24'''

from collections.abc import Sequence

from .correct_asyncio import *
from .utils import _merge_dict
from .user_request import GetAllUserRequest, GetByIDUserRequest, CallUserRequest
from .srh import ServerRequestHandler, slow


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
        
        self.srh = ServerRequestHandler(webhook, verbose)


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