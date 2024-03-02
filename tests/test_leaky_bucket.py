import asyncio
import math
import time

import pytest

from fast_bitrix24.leaky_bucket import LeakyBucketLimiter, RequestRecord


@pytest.mark.parametrize(
    "max_request_running_time, measurement_period, requests, measurements",
    [
        [2, 10, [], [[0, 0]]],
        [2, 10, [], [[5, 0]]],
        [2, 10, [], [[15, 0]]],
        [2, 10, [[0, 1], [2, 1]], [[5, 5]]],
        [2, 10, [[0, 1], [2, 1]], [[7, 3]]],
        [2, 10, [[0, 1], [2, 1], [3, 1]], [[5, 7]]],
        [
            2,
            10,
            [[0, 1], [2, 1], [3, 1], [10, 0.9]],
            [[0, 0], [1, 0], [2.1, 7.9], [10.1, 1.9]],
        ],
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "max_request_running_time, measurement_period, request_durations, expected_sleep_time, test_id",
    [
        # Happy path tests
        (10, 20, [1, 2, 3], 0, "happy-1"),
        (10, 20, [5, 5.1, 5], 9.9, "happy-2"),
        # Edge cases
        (10, 20, [10], 10, "edge-1"),
        (10, 20, [10, 0.1],  9.9, "edge-2"),
    ],
)
async def test_leaky_bucket_limiter(
    max_request_running_time,
    measurement_period,
    request_durations,
    expected_sleep_time,
    test_id,
    monkeypatch,
):
    # Set up mocks
    start_time = time.monotonic()

    def fake_time():
        return start_time

    monkeypatch.setattr(time, "monotonic", fake_time)

    sleep_log = []

    async def fake_sleep(duration):
        sleep_log.append(duration)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    # Arrange
    limiter = LeakyBucketLimiter(max_request_running_time, measurement_period)

    # Act
    for duration in request_durations:
        async with limiter.acquire():
            pass
        limiter.register(duration)
        start_time += duration
        await asyncio.sleep(duration)

    # Assert
    assert math.isclose(
        limiter.get_needed_sleep_time(), expected_sleep_time
    ), f"Test failed for {test_id}"
