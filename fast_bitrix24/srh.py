from asyncio import Event, TimeoutError, sleep
from contextlib import asynccontextmanager

import aiohttp
from aiohttp.client_exceptions import (
    ClientConnectionError,
    ClientPayloadError,
    ClientResponseError,
)

from .throttle import SlidingWindowThrottler, LeakyBucketThrottler
from .logger import logger
from .utils import _url_valid

BITRIX_MAX_BATCH_SIZE = 50
BITRIX_MAX_CONCURRENT_REQUESTS = 50

BITRIX_MAX_REQUEST_RUNNING_TIME = 480
BITRIX_MEASUREMENT_PERIOD = 10 * 60

MAX_RETRIES = 10

RESTORE_CONNECTIONS_FACTOR = 1.3  # скорость восстановления количества запросов
DECREASE_CONNECTIONS_FACTOR = 3  # скорость уменьшения количества запросов
INITIAL_TIMEOUT = 0.5  # начальный таймаут в секундах
BACKOFF_FACTOR = 1.5  # основа расчета таймаута
# количество ошибок, до достижения котрого таймауты не делаются
NUM_FAILURES_NO_TIMEOUT = 3


class ServerError(Exception):
    pass


class TokenRejected(Exception):
    pass


RETRIED_ERRORS = (
    ClientPayloadError,
    ClientConnectionError,
    ServerError,
    TimeoutError,
    TokenRejected,
)


class ServerRequestHandler:
    """
    Используется для контроля скорости доступа к серверам Битрикс.

    Основная цель - вести учет количества запросов, которые можно передать
    серверу Битрикс без получения ошибки `5XX`.

    Используется как контекстный менеджер, оборачивающий несколько
    последовательных запросов к серверу.
    """

    def __init__(
        self,
        webhook: str,
        token_func: callable,
        respect_velocity_policy: bool,
        request_pool_size: int,
        requests_per_second: float,
        client,
        ssl: bool = True,
    ):
        self.webhook = self.standardize_webhook(webhook)

        self.token_func = token_func
        self.token = None

        # token_received - сигнал о том, что процесс получения токена уже запущен
        self.token_request_in_progress = Event()
        self.token_request_in_progress.clear()

        self.respect_velocity_policy = respect_velocity_policy

        self.active_runs = 0

        # если пользователь при инициализации передал клиента со своими настройками,
        # то будем использовать его клиента
        self.client_provided_by_user = bool(client)
        self.session = client
        self.ssl = ssl

        # лимит количества одновременных запросов,
        # установленный конструктором или пользователем
        self.mcr_max = BITRIX_MAX_CONCURRENT_REQUESTS

        # временный лимит количества одновременных запросов,
        # установленный через autothrottling
        self.mcr_cur_limit = BITRIX_MAX_CONCURRENT_REQUESTS

        self.concurrent_requests = 0
        self.request_complete = Event()

        # если положительное - количество последовательных удачных запросов
        # если отрицательное - количество последовательно полученных ошибок
        self.successive_results = 0

        # rate throttlers by method
        self.method_throttlers = {}  # dict[str, LeakyBucketLimiter]

        self.leaky_bucket_throttler = LeakyBucketThrottler(
            request_pool_size, requests_per_second
        )

    @staticmethod
    def standardize_webhook(webhook):
        """Приводит `webhook` к стандартному виду."""

        if not isinstance(webhook, str):
            raise TypeError(f"Webhook should be a {str}")

        webhook = webhook.strip()

        if not _url_valid(webhook):
            raise ValueError("Webhook is not a valid URL")

        if webhook[-1] != "/":
            webhook += "/"

        return webhook

    async def run_async(self, coroutine):
        """Запускает `coroutine`, создавая и прекращая сессию
        при необходимости."""

        async with self.handle_sessions():
            return await coroutine

    @asynccontextmanager
    async def handle_sessions(self):
        """Открывает и закрывает сессию в зависимости от наличия
        активных запросов."""

        # если клиент был задан пользователем, то ожидаем,
        # что пользователь сам откроет и закроет сессию

        if self.client_provided_by_user:
            yield
            return

        if not self.active_runs and (not self.session or self.session.closed):
            self.session = aiohttp.ClientSession(raise_for_status=True)
        self.active_runs += 1

        try:
            yield

        finally:
            self.active_runs -= 1
            if not self.active_runs and self.session and not self.session.closed:
                await self.session.close()

    async def single_request(self, method: str, params=None) -> dict:
        """Делает единичный запрос к серверу,
        с повторными попытками при необходимости."""

        while True:

            try:
                result = await self.request_attempt(method.strip().lower(), params)
                self.success()
                return result

            except RETRIED_ERRORS as err:  # all other exceptions will propagate
                self.failure(err)

    async def request_attempt(self, method, params=None) -> dict:
        """Делает попытку запроса к серверу, ожидая при необходимости."""

        try:
            async with self.acquire(method):
                logger.debug(f"Requesting {{'method': {method}, 'params': {params}}}")

                params_with_auth = params.copy()

                if self.token_func: # если требуется авторизация

                    # если вдруг процесс получения токена уже запущен,
                    # то подождать его окончания
                    await self.token_request_in_progress.wait()

                    if not self.token: # начальное получение токена
                        await self.update_token()

                    params_with_auth["auth"] = self.token

                async with self.session.post(
                    url=self.webhook + method, json=params_with_auth, ssl=self.ssl
                ) as response:
                    json = await response.json(encoding="utf-8")

                    logger.debug("Response: %s", json)

                    self.add_throttler_records(method, params, json)

                    return json

        except ClientResponseError as error:

            if error.status // 100 == 5:  # ошибки вида 5XX
                raise ServerError("The server returned an error") from error

            # нужно получить или освежить токен

            # TODO: нужно как-то отличать проблему протухания токена от других проблем
            elif error.status == 403 and self.token_func:

                # запрашиваем новый токен, только если процесс получения токена еще не запущен
                if not self.token_request_in_progress.is_set():
                    await self.update_token()

                raise TokenRejected("The server rejected the auth token") from error

            raise  # иначе повторяем полученное исключение

    def add_throttler_records(self, method, params: dict, json: dict):
        if "result_time" in json:
            for cmd_name, cmd_url in params["cmd"].items():
                item_method = cmd_url.split("?")[0]
                item_time = json["result_time"][cmd_name]
                self.method_throttlers[item_method].add_request_record(item_time)
        elif "operating" in json["time"]:
            request_run_time = json["time"]["operating"]
            self.method_throttlers[method].add_request_record(request_run_time)

        self.leaky_bucket_throttler.add_request_record()

    def success(self):
        """Увеличить счетчик удачных попыток."""

        self.successive_results = max(self.successive_results + 1, 1)

    def failure(self, err: Exception):
        """Увеличить счетчик неудачных попыток и поднять исключение,
        если попытки исчерпаны."""

        self.successive_results = min(self.successive_results - 1, -1)

        if self.successive_results < -MAX_RETRIES:
            raise RuntimeError(
                "All attempts to get data from server exhausted"
            ) from err

    @asynccontextmanager
    async def acquire(self, method: str):
        """Ожидает, пока не станет безопасно делать запрос к серверу."""

        await self.autothrottle()

        async with self.limit_concurrent_requests(), self.leaky_bucket_throttler.acquire():
            if self.respect_velocity_policy:
                if method not in self.method_throttlers:
                    self.method_throttlers[method] = SlidingWindowThrottler(
                        BITRIX_MAX_REQUEST_RUNNING_TIME, BITRIX_MEASUREMENT_PERIOD
                    )

                async with self.method_throttlers[method].acquire():
                    yield

            else:
                yield

    async def autothrottle(self):
        """Если было несколько неудач, делаем таймаут и уменьшаем скорость
        и количество одновременных запросов, и наоборот."""

        if self.successive_results < 0:
            self.mcr_cur_limit = max(
                self.mcr_cur_limit / DECREASE_CONNECTIONS_FACTOR, 1
            )

            logger.debug(
                f"Concurrent requests decreased: {{'mcr_cur_limit': {self.mcr_cur_limit}}}"
            )

            if self.successive_results < NUM_FAILURES_NO_TIMEOUT:
                power = -self.successive_results - NUM_FAILURES_NO_TIMEOUT - 1
                delay = INITIAL_TIMEOUT * BACKOFF_FACTOR**power

                logger.debug(f"Delaying request: {{'delay': {delay}}}")

                await sleep(delay)

        elif self.successive_results > 0:

            self.mcr_cur_limit = min(
                self.mcr_cur_limit * RESTORE_CONNECTIONS_FACTOR, self.mcr_max
            )

            logger.debug(
                f"Concurrent requests increased: {{'mcr_cur_limit': {self.mcr_cur_limit}}}"
            )

    @asynccontextmanager
    async def limit_concurrent_requests(self):
        """Не позволяет одновременно выполнять
        более `self.mcr_cur_limit` запросов."""

        while self.concurrent_requests > self.mcr_cur_limit:
            self.request_complete.clear()
            await self.request_complete.wait()

        self.concurrent_requests += 1

        try:
            yield

        finally:
            self.concurrent_requests -= 1
            self.request_complete.set()

    async def update_token(self):
        """Запросить новый токен авторизации."""

        self.token_request_in_progress.clear()
        self.token = await self.token_func()
        self.token_request_in_progress.set()
