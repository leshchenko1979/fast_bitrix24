import asyncio
import collections
import contextlib
import time

RequestRecord = collections.namedtuple("RequestRecord", "when, duration")


class SlidingWindowThrottler:
    """The class emulates a sliding window throttler.

    The consumer may only run requests until he has used up X seconds
    of request running time in total during a period of Y seconds.

    When the consumer has hit the limit, he will have to wait.
    """

    def __init__(self, max_request_running_time: float, measurement_period: float):
        # how much time fits into the bucket before it starts failing
        self._max_request_running_time = max_request_running_time

        # over what period of time should the max_request_running_time be measured
        self._measurement_period = measurement_period

        # request history. left - most recent, right - least recent
        self._request_history = collections.deque()

    @contextlib.asynccontextmanager
    async def acquire(self):
        """A context manager that will wait until it's safe to make the next request"""
        await asyncio.sleep(self._calculate_needed_sleep_time())

        try:
            yield
        finally:
            self._remove_stale_records()

    def _calculate_needed_sleep_time(self) -> float:
        """How much time to sleep before it's safe to make a request"""
        acc = 0
        for record in self._request_history:
            acc += record.duration
            if acc >= self._max_request_running_time:
                return record.when + self._measurement_period - time.monotonic()
        return 0

    def _remove_stale_records(self):
        """Remove all stale records from the record register"""
        cut_off = time.monotonic() - self._measurement_period
        while self._request_history and self._request_history[-1].when < cut_off:
            self._request_history.pop()

    def add_request_record(self, request_duration: float):
        """Register how long the last request has taken"""
        self._request_history.appendleft(
            RequestRecord(time.monotonic(), request_duration)
        )


class LeakyBucketThrottler:
    """The class implements a leaky bucket throttler.

    The consumer may only run requests until he has used up to X requests,
    after which the rate of Y requests per second will be applied.

    When the consumer has hit the limit, he will have to wait.
    """

    def __init__(self, pool_size: int, requests_per_second: float):
        # how many requests can be in the bucket at once
        self._pool_size = pool_size

        # how many requests are removed from the bucket per second
        self._requests_per_second = requests_per_second

        # request history. left - most recent, right - least recent
        self._request_history = collections.deque()

    @contextlib.asynccontextmanager
    async def acquire(self):
        """A context manager that will wait until it's safe to make the next request"""
        await asyncio.sleep(self._calculate_needed_sleep_time())

        try:
            yield
        finally:
            self._remove_stale_records()

    def _calculate_needed_sleep_time(self) -> float:
        """How much time to sleep before it's safe to make a request"""
        while len(self._request_history) >= self._pool_size:
            time_from_last_request = time.monotonic() - self._request_history[0]
            time_to_wait = 1 / self._requests_per_second - time_from_last_request
            if time_to_wait > 0:
                return time_to_wait
            else:
                break
        return 0

    def add_request_record(self):
        """Register when the last request was made"""
        self._request_history.appendleft(time.monotonic())

    def _remove_stale_records(self):
        """Remove all stale records from the record register"""
        cut_off = time.monotonic() - self._pool_size / self._requests_per_second
        while self._request_history and self._request_history[-1] < cut_off:
            self._request_history.pop()
