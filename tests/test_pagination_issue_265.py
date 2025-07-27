"""Test for GitHub issue #265: get_all() stops after first 50 results due to batch failures"""
import warnings
import pytest
from fast_bitrix24.bitrix import BitrixAsync
from fast_bitrix24.srh import ServerRequestHandler


class MockSRHBatchFailure(ServerRequestHandler):
    """Mock SRH that simulates the issue from GitHub #265"""

    def __init__(self):
        # Initialize with required attributes
        self.call_count = 0
        self.mcr_cur_limit = 50
        self.concurrent_requests = 0

    async def single_request(self, method, params):
        self.call_count += 1

        if method == "batch":
            # Simulate batch request returning empty results (the core issue)
            return {
                "result": {
                    "result": {}  # Empty batch results
                }
            }

        elif method == "crm.deal.list":
            # First request succeeds - matches the exact scenario from the log
            return {
                'result': [
                    {'ID': '14152', 'UF_CRM_1626273510024': '22531'},
                    {'ID': '14194', 'UF_CRM_1626273510024': '1960'},
                    # ... simulate 48 more results to total 50
                ] + [
                    {'ID': f'{14200 + i}', 'UF_CRM_1626273510024': f'data_{i}'}
                    for i in range(48)
                ],
                'next': 50,
                'total': 2490,  # Large dataset (2440 remaining > 100 threshold)
                'time': {}
            }

        return {'result': [], 'total': 0}

    async def run_async(self, coro):
        return await coro


class MockSRHSmallDataset(ServerRequestHandler):
    """Mock SRH for small dataset where empty batches might be legitimate"""

    def __init__(self):
        self.call_count = 0
        self.mcr_cur_limit = 50
        self.concurrent_requests = 0

    async def single_request(self, method, params):
        self.call_count += 1

        if method == "batch":
            # Return empty results for small dataset
            return {
                "result": {
                    "result": {}
                }
            }

        elif method == "crm.deal.list":
            # Small dataset with 75 total results (25 remaining < 100 threshold)
            return {
                'result': [{'ID': f'{i}', 'data': f'item_{i}'} for i in range(50)],
                'next': 50,
                'total': 75,  # Small dataset
                'time': {}
            }

        return {'result': [], 'total': 0}

    async def run_async(self, coro):
        return await coro


@pytest.mark.asyncio
async def test_github_issue_265_large_dataset_batch_failure():
    """Test that batch failures are detected for large datasets (>100 remaining)"""

    bitrix = BitrixAsync("https://mock.webhook.url/")
    bitrix.srh = MockSRHBatchFailure()

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")

        results = await bitrix.get_all(
            'crm.deal.list',
            params={
                'filter': {'UF_CRM_1626273510024': True, 'UF_CRM_1753419667': False },
                'select': ['ID', 'UF_CRM_1626273510024']
            }
        )

        # Should get only first page results (50 items)
        assert len(results) == 50, f"Expected 50 results, got {len(results)}"

        # Should have made 2 API calls (first request + batch request)
        assert bitrix.srh.call_count == 2, f"Expected 2 API calls, got {bitrix.srh.call_count}"

        # Should generate warnings about batch failure for large datasets
        warnings_messages = [str(w.message) for w in warning_list]

        # Check for batch failure warning (should be present for large datasets)
        batch_failure_warnings = [w for w in warnings_messages if "Batch requests returned no results" in w]
        assert len(batch_failure_warnings) > 0, "Should warn about batch request failure for large datasets"

        # Check for result count mismatch warning
        mismatch_warnings = [w for w in warnings_messages if "Number of results returned" in w and "doesn't equal 'total'" in w]
        assert len(mismatch_warnings) > 0, "Should warn about result count mismatch"

        # Verify warning mentions possible legitimate causes
        batch_warning = batch_failure_warnings[0]
        assert "Expected 2440 more items but got 0" in batch_warning
        assert "data changes during pagination" in batch_warning


@pytest.mark.asyncio
async def test_small_dataset_no_false_positive():
    """Test that small datasets don't generate false positive warnings"""

    bitrix = BitrixAsync("https://mock.webhook.url/")
    bitrix.srh = MockSRHSmallDataset()

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")

        results = await bitrix.get_all('crm.deal.list')

        # Should get only first page results (50 items)
        assert len(results) == 50, f"Expected 50 results, got {len(results)}"

        # Should have made 2 API calls
        assert bitrix.srh.call_count == 2, f"Expected 2 API calls, got {bitrix.srh.call_count}"

        warnings_messages = [str(w.message) for w in warning_list]

        # Should NOT generate batch failure warnings for small datasets (25 remaining < 100 threshold)
        batch_warnings = [w for w in warnings_messages if "Batch requests returned no results" in w]
        assert len(batch_warnings) == 0, "Should not warn about batch failures for small datasets"

        # Should still generate result count mismatch warning (this is separate logic)
        mismatch_warnings = [w for w in warnings_messages if "Number of results returned" in w and "doesn't equal 'total'" in w]
        assert len(mismatch_warnings) > 0, "Should still warn about result count mismatch"


@pytest.mark.asyncio
async def test_normal_pagination_still_works():
    """Test that normal pagination continues to work after the fix"""

    class MockSRHWorkingPagination(ServerRequestHandler):
        def __init__(self):
            self.call_count = 0
            self.mcr_cur_limit = 50
            self.concurrent_requests = 0

        async def single_request(self, method, params):
            self.call_count += 1

            if method == "batch":
                # Simulate successful batch with results
                return {
                    "result": {
                        "result": {
                            f"cmd{i}": {'ID': f'{100 + i}', 'data': f'batch_item_{i}'}
                            for i in range(50)  # Return 50 more items
                        }
                    }
                }

            elif method == "crm.deal.list":
                return {
                    'result': [{'ID': f'{i}', 'data': f'item_{i}'} for i in range(50)],
                    'next': 50,
                    'total': 100,  # Smaller total for faster test
                    'time': {}
                }

            return {'result': [], 'total': 0}

        async def run_async(self, coro):
            return await coro

    bitrix = BitrixAsync("https://mock.webhook.url/")
    bitrix.srh = MockSRHWorkingPagination()

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")

        results = await bitrix.get_all('crm.deal.list')

        # Should get all results
        assert len(results) == 100, f"Expected 100 results, got {len(results)}"

        # Should not generate any batch failure warnings
        batch_warnings = [w for w in warning_list if "Batch requests returned" in str(w.message)]
        assert len(batch_warnings) == 0, "Should not warn about batch failures when pagination works"
