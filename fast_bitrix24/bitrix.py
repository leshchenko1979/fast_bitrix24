"""Высокоуровневый API для доступа к Битрикс24"""

import asyncio
import functools as ft
from contextlib import contextmanager
from typing import Iterable, Union

import aiohttp
import icontract
from beartype import beartype

from . import correct_asyncio
from .logger import log, logger
from .server_response import ServerResponseParser
from .srh import ServerRequestHandler
from .user_request import (
    CallUserRequest,
    GetAllUserRequest,
    GetByIDUserRequest,
    ListAndGetUserRequest,
    RawCallUserRequest,
)


class BitrixAsync:
    """Клиент для асинхронных запросов к Битрикс24."""

    def __init__(
        self,
        webhook: str,
        verbose: bool = True,
        respect_velocity_policy: bool = True,
        request_pool_size: int = 50,
        requests_per_second: float = 2.0,
        client: aiohttp.ClientSession = None,
        ssl: bool = True,
    ):
        """
        Создает объект для запросов к Битрикс24.

        Параметры:
        - `webhook: str` - URL вебхука, полученного от сервера Битрикс
        - `verbose: bool = True` - показывать ли прогрессбар при выполнении
        запроса
        - `respect_velocity_policy: bool = True` - соблюдать ли политику
        Битрикса о скорости запросов
        - `request_pool_size: int = 50` - размер пула запросов, который
        можно отправить на сервер без ожидания
        - `requests_per_second: float = 2.0` - максимальная скорость запросов,
        которая будет использоваться после переполнения пула
        - `ssl: bool = True` - использовать ли проверку SSL-сертификата
        при HTTP-соединениях с сервером Битрикс.
        - `client: aiohttp.ClientSession = None` - использовать для HTTP-вызовов
        объект aiohttp.ClientSession, инициализированнный и настроенный
        пользователем. Ожидаеется, что пользователь сам откроет и закроет сессию.
        """

        self.srh = ServerRequestHandler(
            webhook=webhook,
            respect_velocity_policy=respect_velocity_policy,
            request_pool_size=request_pool_size,
            requests_per_second=requests_per_second,
            ssl=ssl,
            client=client,
        )
        self.verbose = verbose

    @log
    async def get_all(self, method: str, params: dict = None) -> Union[list, dict]:
        """
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
        """

        return await self.srh.run_async(GetAllUserRequest(self, method, params).run())

    @log
    async def get_by_ID(
        self,
        method: str,
        ID_list: Iterable,
        ID_field_name: str = "ID",
        params: dict = None,
    ) -> dict:
        """
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
        """

        return await self.srh.run_async(
            GetByIDUserRequest(self, method, params, ID_list, ID_field_name).run()
        )

    @log
    async def list_and_get(self, method_branch: str, ID_field_name="ID") -> dict:
        """
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
        """

        return await ListAndGetUserRequest(
            self, method_branch, ID_field_name=ID_field_name
        ).run()

    @log
    async def call(
        self, method: str, items: Union[dict, Iterable] = None, *, raw=False
    ):
        """
        Вызвать метод REST API по списку элементов.

        Параметры:
        - `method` - метод REST API
        - `items` - список параметров вызываемого метода
            либо dict с параметрами для единичного вызова. Может быть `None`,
            если `raw=True`.
        - `raw` - если True, то items отправляются на сервер в виде json
            в первозданном виде, без обычных преобразований.
            По умолчанию False.

        Возвращает список ответов сервера для каждого из элементов `items`
        либо просто результат для единичного вызова.
        """

        request_cls = RawCallUserRequest if raw else CallUserRequest
        return await self.srh.run_async(request_cls(self, method, items).run())

    @log
    async def call_batch(self, params: dict) -> dict:
        """
        Вызвать метод `batch`.

        Параметры:
        - `params` - список параметров вызываемого метода

        Возвращает ответы сервера в формате словаря, где ключ - название
        команды, а значение - ответ сервера по этой команде.
        """

        response = ServerResponseParser(
            await self.srh.run_async(RawCallUserRequest(self, "batch", params).run())
        )

        response.raise_for_errors()

        return response.result["result"]

    @contextmanager
    @beartype
    @icontract.require(lambda max_concurrent_requests: max_concurrent_requests >= 1)
    def slow(self, max_concurrent_requests: int = 1):
        """Временно ограничивает количество одновременно выполняемых запросов
        к Битрикс24."""

        logger.info(
            "Slow mode enabled: {'max_concurrent_requests': %s}",
            max_concurrent_requests,
        )

        mcr_max_backup, self.srh.mcr_max = self.srh.mcr_max, max_concurrent_requests
        self.srh.mcr_cur_limit = min(self.srh.mcr_max, self.srh.mcr_cur_limit)

        yield True

        logger.info(
            "Slow mode disabled: {'max_concurrent_requests': %s}",
            mcr_max_backup,
        )

        self.srh.mcr_max = mcr_max_backup
        self.srh.mcr_cur_limit = min(self.srh.mcr_max, self.srh.mcr_cur_limit)


class Bitrix(BitrixAsync):
    """Клиент для неасинхронных запросов к серверу Битрикс24.

    Имплементируется путем обертки всех методов родителя в неасинхронные методы.
    """

    def sync_decorator(coroutine):
        ft.wraps(coroutine)

        def sync_wrapper(*args, **kwargs):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                return asyncio.run(coroutine(*args, **kwargs))

            if loop.is_running():
                return loop.create_task(coroutine(*args, **kwargs))

            return loop.run_until_complete(coroutine(*args, **kwargs))

        return sync_wrapper

    for method in dir(BitrixAsync):
        if not method.startswith("__") and method != "slow":
            locals()[method] = sync_decorator(getattr(BitrixAsync, method))
