"""Tests for configuration module."""

import pytest
from selenium_notion_autofill.config import FIELD_SELECTORS, NOTION_API_KEY, DATABASE_ID


def test_config_keys_exist():
    """Test that all required configuration keys are present."""
    assert NOTION_API_KEY
    assert DATABASE_ID
    assert FIELD_SELECTORS


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
