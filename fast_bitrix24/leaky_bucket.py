import asyncio
import collections
import contextlib
import time


RequestRecord = collections.namedtuple("RequestRecord", "when, duration")


class LeakyBucketLimiter:
    """The class emulates a leaky bucket where the consumer may only run requests
    until he has used up X seconds of request running time in total
    during a period of Y seconds.

    When the consumer has hit the limit, he will have to wait.
    """

    def __init__(self, max_request_running_time: float, measurement_period: float):
        # how much time fits into the bucket before it starts failing
        self.max_request_running_time = max_request_running_time

        # over what period of time should the max_request_running_time be measured
        self.measurement_period = measurement_period

        # request register. left - most recent, right - least recent
        self.request_register = collections.deque()

    @contextlib.asynccontextmanager
    async def acquire(self):
        """A context manager that will wait until it's safe to make the next request"""
        await asyncio.sleep(self.get_needed_sleep_time())

        try:
            yield
        finally:
            self.clean_up()

    def get_needed_sleep_time(self) -> float:
        """How much time to sleep before it's safe to make a request"""
        acc = 0
        for record in self.request_register:
            acc += record.duration
            if acc >= self.max_request_running_time:
                return record.when + self.measurement_period - time.monotonic()
        return 0

    def clean_up(self):
        """Remove all stale records from the record register"""
        if not self.request_register:
            return

        cut_off = time.monotonic() - self.measurement_period
        while self.request_register[-1].when < cut_off:
            self.request_register.pop()

    def register(self, request_duration: float):
        """Register how long the last request has taken"""
        self.request_register.appendleft(
            RequestRecord(time.monotonic(), request_duration)
        )
