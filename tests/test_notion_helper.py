"""Tests for Notion helper module."""

import pytest
from unittest.mock import Mock, patch
from selenium_notion_autofill.utils.notion_helper import NotionHelper


@pytest.fixture
def notion_helper():
    """Create a NotionHelper instance for testing."""
    return NotionHelper("test_api_key")


def test_notion_helper_initialization(notion_helper):
    """Test NotionHelper initialization."""
    assert notion_helper.api_key == "test_api_key"
    assert notion_helper.base_url == "https://api.notion.com/v1"
    assert "Authorization" in notion_helper.headers
    assert notion_helper.headers["Authorization"] == "Bearer test_api_key"


def test_get_property_value_title(notion_helper):
    """Test extracting title property value."""
    prop = {
        "type": "title",
        "title": [{"plain_text": "Test Title"}],
    }
    result = notion_helper._get_property_value(prop)
    assert result == "Test Title"


def test_get_property_value_email(notion_helper):
    """Test extracting email property value."""
    prop = {
        "type": "email",
        "email": "test@example.com",
    }
    result = notion_helper._get_property_value(prop)
    assert result == "test@example.com"


def test_get_property_value_checkbox(notion_helper):
    """Test extracting checkbox property value."""
    prop = {
        "type": "checkbox",
        "checkbox": True,
    }
    result = notion_helper._get_property_value(prop)
    assert result is True


def test_get_property_value_date(notion_helper):
    """Test extracting date property value."""
    prop = {
        "type": "date",
        "date": {"start": "2024-01-15"},
    }
    result = notion_helper._get_property_value(prop)
    assert result == "2024-01-15"


def test_get_property_value_none():
    """Test extracting value from None."""
    notion_helper = NotionHelper("test_api_key")
    result = notion_helper._get_property_value(None)
    assert result is None


def test_get_property_value_empty_dict():
    """Test extracting value from empty dict."""
    notion_helper = NotionHelper("test_api_key")
    result = notion_helper._get_property_value({})
    assert result is None
