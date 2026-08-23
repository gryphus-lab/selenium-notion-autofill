"""Tests for configuration module."""

import pytest

from selenium_notion_autofill.config import (
    FIELD_SELECTORS,
    get_database_id,
    get_notion_api_key,
    validate_property_map,
)


def test_config_keys_exist():
    """Test that all required configuration keys are present."""
    assert get_notion_api_key()
    assert get_database_id()
    assert FIELD_SELECTORS


def test_required_notion_settings_are_validated_when_accessed(monkeypatch):
    monkeypatch.delenv("NOTION_API_KEY")
    monkeypatch.delenv("DATABASE_ID")

    with pytest.raises(RuntimeError, match="NOTION_API_KEY"):
        get_notion_api_key()
    with pytest.raises(RuntimeError, match="DATABASE_ID"):
        get_database_id()


def test_field_selectors_structure():
    """Test that FIELD_SELECTORS has required fields."""
    required_fields = {
        "Date",
        "Type",
        "Company",
        "Street",
        "Email",
        "Phone",
        "Role",
    }
    assert required_fields.issubset(set(FIELD_SELECTORS.keys()))


def test_field_selectors_are_strings():
    """Test that all selectors are strings."""
    for field, selector in FIELD_SELECTORS.items():
        assert isinstance(selector, str), f"Selector for {field} is not a string"


def test_validate_property_map_accepts_string_mapping():
    assert validate_property_map({"Company": "Firma"}) == {"Company": "Firma"}


@pytest.mark.parametrize("value", [[], {"Company": 1}, {1: "Firma"}])
def test_validate_property_map_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        validate_property_map(value)
