import pytest
from fast_bitrix24.utils import convert_boolean_params


class TestBooleanParameterConversion:
    """Test that boolean parameters are correctly converted to Y/N format."""

    def test_simple_boolean_values(self):
        """Test simple boolean values are converted correctly."""
        assert convert_boolean_params(True) == "Y"
        assert convert_boolean_params(False) == "N"

    def test_dict_with_boolean_values(self):
        """Test dictionaries with boolean values are converted correctly."""
        params = {
            "active": True,
            "closed": False,
            "name": "test",
            "count": 123
        }
        expected = {
            "active": "Y",
            "closed": "N",
            "name": "test",
            "count": 123
        }
        assert convert_boolean_params(params) == expected

    def test_nested_dict_with_boolean_values(self):
        """Test nested dictionaries with boolean values are converted correctly."""
        params = {
            "filter": {
                "active": True,
                "closed": False,
                "status": "active"
            },
            "fields": {
                "name": "test",
                "enabled": True
            }
        }
        expected = {
            "filter": {
                "active": "Y",
                "closed": "N",
                "status": "active"
            },
            "fields": {
                "name": "test",
                "enabled": "Y"
            }
        }
        assert convert_boolean_params(params) == expected

    def test_list_with_boolean_values(self):
        """Test lists with boolean values are converted correctly."""
        params = [True, False, "test", 123]
        expected = ["Y", "N", "test", 123]
        assert convert_boolean_params(params) == expected

    def test_nested_list_with_boolean_values(self):
        """Test nested lists with boolean values are converted correctly."""
        params = [
            {"active": True, "name": "item1"},
            {"enabled": False, "name": "item2"},
            "string_item",
            456
        ]
        expected = [
            {"active": "Y", "name": "item1"},
            {"enabled": "N", "name": "item2"},
            "string_item",
            456
        ]
        assert convert_boolean_params(params) == expected

    def test_complex_nested_structure(self):
        """Test complex nested structure with boolean values."""
        params = {
            "filter": {
                "active": True,
                "status": ["active", "pending"],
                "settings": {
                    "enabled": False,
                    "notifications": True
                }
            },
            "fields": ["ID", "NAME", "ACTIVE"],
            "select": {
                "include_archived": False,
                "include_deleted": True
            }
        }
        expected = {
            "filter": {
                "active": "Y",
                "status": ["active", "pending"],
                "settings": {
                    "enabled": "N",
                    "notifications": "Y"
                }
            },
            "fields": ["ID", "NAME", "ACTIVE"],
            "select": {
                "include_archived": "N",
                "include_deleted": "Y"
            }
        }
        assert convert_boolean_params(params) == expected

    def test_non_boolean_values_unchanged(self):
        """Test that non-boolean values remain unchanged."""
        params = {
            "string": "test",
            "integer": 123,
            "float": 45.67,
            "none": None,
            "list": [1, 2, 3],
            "dict": {"key": "value"}
        }
        assert convert_boolean_params(params) == params

    def test_empty_structures(self):
        """Test empty structures are handled correctly."""
        assert convert_boolean_params({}) == {}
        assert convert_boolean_params([]) == []
        assert convert_boolean_params(None) == None

    def test_mixed_boolean_and_non_boolean(self):
        """Test mixed boolean and non-boolean values in complex structure."""
        params = {
            "simple_bool": True,
            "nested": {
                "bool_in_dict": False,
                "string": "test",
                "list_with_bool": [True, "string", False, 123]
            },
            "list_with_dict": [
                {"enabled": True, "name": "item1"},
                {"enabled": False, "name": "item2"}
            ]
        }
        expected = {
            "simple_bool": "Y",
            "nested": {
                "bool_in_dict": "N",
                "string": "test",
                "list_with_bool": ["Y", "string", "N", 123]
            },
            "list_with_dict": [
                {"enabled": "Y", "name": "item1"},
                {"enabled": "N", "name": "item2"}
            ]
        }
        assert convert_boolean_params(params) == expected 