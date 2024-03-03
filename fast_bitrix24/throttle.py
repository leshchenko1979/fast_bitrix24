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
        if not self._request_history:
            return

        cut_off = time.monotonic() - self._measurement_period
        while self._request_history[-1].when < cut_off:
            self._request_history.pop()

    def add_request_record(self, request_duration: float):
        """Register how long the last request has taken"""
        self._request_history.appendleft(
            RequestRecord(time.monotonic(), request_duration)
        )
