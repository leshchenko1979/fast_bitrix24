import pytest
from collections import ChainMap
from fast_bitrix24.mult_request import MultipleServerRequestHandler
from fast_bitrix24.server_response import ServerResponseParser


class MockSRH:
    def __init__(self, responses):
        self.responses = responses if isinstance(responses, list) else [responses]
        self.request_count = 0

    async def single_request(self, method, params):
        self.request_count += 1
        return self.responses[self.request_count - 1]


class MockBitrix:
    def __init__(self, responses):
        self.srh = MockSRH(responses)
        self.verbose = False


def test_chainmap_serialization_in_fallback():
    """Test that ChainMap objects are properly converted to dicts in fallback mode."""

    # Mock responses for individual requests
    mock_responses = [
        {"result": {"id": 1, "name": "Item 1"}},
        {"result": {"id": 2, "name": "Item 2"}},
    ]

    # Create ChainMap objects (similar to what CallUserRequest.prepare_item_list creates)
    chainmap_items = [
        ChainMap({"name": "Item 1"}, {"__order": "order0000000000"}),
        ChainMap({"name": "Item 2"}, {"__order": "order0000000001"}),
    ]

    # Create the handler
    bitrix = MockBitrix(mock_responses)
    handler = MultipleServerRequestHandler(
        bitrix=bitrix,
        method="test.method",
        item_list=chainmap_items,
        get_by_ID=False
    )

    # Store original items to simulate the fallback scenario
    handler.original_items = None  # Force fallback to use item_list

    # Run the fallback method
    import asyncio
    results = asyncio.run(handler._fallback_to_individual_requests())

    # Verify that the requests were made successfully (no JSON serialization errors)
    assert bitrix.srh.request_count == 2

    # Verify that we got the expected results
    assert len(results) == 2
    assert results[0]["id"] == 1
    assert results[1]["id"] == 2


def test_chainmap_detection():
    """Test that ChainMap objects are properly detected and converted."""

    # Test with ChainMap
    chainmap_item = ChainMap({"name": "Test"}, {"__order": "order0000000000"})
    assert hasattr(chainmap_item, 'maps')  # Verify ChainMap detection

    # Test conversion
    converted = dict(chainmap_item)
    assert isinstance(converted, dict)
    assert converted["name"] == "Test"
    assert converted["__order"] == "order0000000000"

    # Test with regular dict (should not be affected)
    regular_dict = {"name": "Test"}
    assert not hasattr(regular_dict, 'maps')
