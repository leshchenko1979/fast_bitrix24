import math
import pytest

from fast_bitrix24.leaky_bucket import LeakyBucketLimiter


@pytest.mark.parametrize(
    "max_request_running_time, measurement_period, requests, measurements",
    [
        [2, 10, [], [[0, 0]]],
        [2, 10, [], [[5, 0]]],
        [2, 10, [], [[15, 0]]],
        [2, 10, [[0, 1], [2, 1]], [[5, 5]]],
        [2, 10, [[0, 1], [2, 1]], [[7, 3]]],
        [2, 10, [[0, 1], [2, 1], [3, 1]], [[5, 7]]],
        [2, 10, [[0, 1], [2, 1], [3, 1], [10, 0.9]], [[0, 0], [1, 0], [2.1, 7.9], [10.1, 1.9]]],
    ],
)
def test_needed_sleep_time(
    max_request_running_time,
    measurement_period,
    requests,
    measurements,
    monkeypatch,
):
    limiter = LeakyBucketLimiter(max_request_running_time, measurement_period)

    while requests or measurements:
        if (requests and measurements and requests[0][0] < measurements[0][0]) or (
            requests and not measurements
        ):
            when, duration = requests.pop(0)
            monkeypatch.setattr("time.monotonic", lambda: when)
            limiter.register(duration)
        else:
            call_point, expected = measurements.pop(0)
            monkeypatch.setattr("time.monotonic", lambda: call_point)
            print("Request record:", limiter.request_register)
            print("Time", call_point)
            assert math.isclose(limiter.get_needed_sleep_time(), expected)
