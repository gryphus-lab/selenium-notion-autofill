"""Tests for Notion helper module."""

import pytest
import httpx
from unittest.mock import Mock
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


def test_get_database_data_paginates_and_flattens_properties(monkeypatch, notion_helper):
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200
            self.text = "ok"
            self.request = Mock()

        def json(self):
            return self._payload

    calls = []

    def fake_post(url, headers=None, json=None, timeout=30):
        calls.append(json)
        if len(calls) == 1:
            return FakeResponse(
                {
                    "results": [
                        {
                            "id": "page-1",
                            "properties": {
                                "Title": {
                                    "type": "title",
                                    "title": [{"plain_text": "Test Title"}],
                                },
                                "Email": {"type": "email", "email": "a@example.com"},
                                "Status": {
                                    "type": "select",
                                    "select": {"name": "Open"},
                                },
                                "Tags": {
                                    "type": "multi_select",
                                    "multi_select": [{"name": "one"}, {"name": "two"}],
                                },
                                "Tracked": {"type": "checkbox", "checkbox": True},
                                "Count": {"type": "number", "number": 3},
                                "Start": {"type": "date", "date": {"start": "2024-01-01"}},
                                "Url": {"type": "url", "url": "https://example.com"},
                                "Phone": {
                                    "type": "phone_number",
                                    "phone_number": "123456",
                                },
                                "Rich": {
                                    "type": "rich_text",
                                    "rich_text": [{"plain_text": "rich"}],
                                },
                            },
                        }
                    ],
                    "has_more": True,
                    "next_cursor": "cursor-2",
                }
            )
        return FakeResponse({"results": [], "has_more": False, "next_cursor": None})

    monkeypatch.setattr("selenium_notion_autofill.utils.notion_helper.httpx.post", fake_post)

    df = notion_helper.get_database_data("db-id")

    assert len(df) == 1
    assert df.loc[0, "id"] == "page-1"
    assert df.loc[0, "Title"] == "Test Title"
    assert df.loc[0, "Email"] == "a@example.com"
    assert df.loc[0, "Status"] == "Open"
    assert df.loc[0, "Tags"] == ["one", "two"]
    assert bool(df.loc[0, "Tracked"]) is True
    assert df.loc[0, "Count"] == 3
    assert df.loc[0, "Start"] == "2024-01-01"
    assert df.loc[0, "Url"] == "https://example.com"
    assert df.loc[0, "Phone"] == "123456"
    assert df.loc[0, "Rich"] == "rich"
    assert len(calls) == 2
    assert calls[1].get("start_cursor") == "cursor-2"


def test_update_row_returns_false_on_request_error(monkeypatch, notion_helper):
    def fake_patch(*args, **kwargs):
        raise httpx.RequestError("boom")

    monkeypatch.setattr("selenium_notion_autofill.utils.notion_helper.httpx.patch", fake_patch)

    assert notion_helper.update_row("page-1", {"Tracked": {"checkbox": True}}) is False
