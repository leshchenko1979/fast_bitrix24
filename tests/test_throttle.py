import asyncio
import math
import time

import pytest

from fast_bitrix24.throttle import LeakyBucketThrottler, SlidingWindowThrottler


# Test the acquire method of the LeakyBucketThrottler class
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pool_size, requests_per_second, requests_made, sleep_time, test_id",
    [
        (5, 1.0, 3, 0, "acquire_happy_no_wait"),
        (5, 1.0, 8, 1, "acquire_happy_path_wait"),
    ],
)
async def test_leaky_bucket(
    pool_size, requests_per_second, requests_made, sleep_time, test_id, monkeypatch
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
    throttler = LeakyBucketThrottler(pool_size, requests_per_second)
    for _ in range(requests_made):
        throttler.add_request_record()

    # Act
    async with throttler.acquire() as _:
        pass

    # Assert
    assert sum(sleep_log) == sleep_time


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
    throttler = SlidingWindowThrottler(max_request_running_time, measurement_period)

    while requests or measurements:
        if (requests and measurements and requests[0][0] < measurements[0][0]) or (
            requests and not measurements
        ):
            when, duration = requests.pop(0)
            monkeypatch.setattr("time.monotonic", lambda: when)
            throttler.add_request_record(duration)
        else:
            call_point, expected = measurements.pop(0)
            monkeypatch.setattr("time.monotonic", lambda: call_point)
            print("Request record:", throttler._request_history)
            print("Time", call_point)
            assert math.isclose(throttler._calculate_needed_sleep_time(), expected)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "max_request_running_time, measurement_period, request_durations, expected_sleep_time, test_id",
    [
        # Happy path tests
        (10, 20, [1, 2, 3], 0, "happy-1"),
        (10, 20, [5, 5.1, 5], 9.9, "happy-2"),
        # Edge cases
        (10, 20, [10], 10, "edge-1"),
        (10, 20, [10, 0.1], 9.9, "edge-2"),
    ],
)
async def test_sliding_window(
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
    throttler = SlidingWindowThrottler(max_request_running_time, measurement_period)

    # Act
    for duration in request_durations:
        async with throttler.acquire():
            pass
        throttler.add_request_record(duration)
        start_time += duration
        await asyncio.sleep(duration)

    # Assert
    assert math.isclose(
        throttler._calculate_needed_sleep_time(), expected_sleep_time
    ), f"Test failed for {test_id}"
