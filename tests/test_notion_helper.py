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


def test_get_property_value_with_none_values():
    """Test _get_property_value handles None gracefully."""
    notion_helper = NotionHelper("test_api_key")
    assert notion_helper._get_property_value(None) is None
    assert notion_helper._get_property_value({}) is None


def test_get_property_value_select(notion_helper):
    """Test extracting select property value."""
    prop = {
        "type": "select",
        "select": {"name": "In Progress"},
    }
    result = notion_helper._get_property_value(prop)
    assert result == "In Progress"


def test_get_property_value_select_null(notion_helper):
    """Test extracting select when no select is set."""
    prop = {
        "type": "select",
        "select": None,
    }
    result = notion_helper._get_property_value(prop)
    assert result == ""


def test_get_property_value_multi_select(notion_helper):
    """Test extracting multi_select property value."""
    prop = {
        "type": "multi_select",
        "multi_select": [{"name": "tag1"}, {"name": "tag2"}],
    }
    result = notion_helper._get_property_value(prop)
    assert result == ["tag1", "tag2"]


def test_get_property_value_number(notion_helper):
    """Test extracting number property value."""
    prop = {
        "type": "number",
        "number": 42,
    }
    result = notion_helper._get_property_value(prop)
    assert result == 42


def test_get_property_value_url(notion_helper):
    """Test extracting url property value."""
    prop = {
        "type": "url",
        "url": "https://example.com",
    }
    result = notion_helper._get_property_value(prop)
    assert result == "https://example.com"


def test_get_property_value_phone_number(notion_helper):
    """Test extracting phone_number property value."""
    prop = {
        "type": "phone_number",
        "phone_number": "+41123456789",
    }
    result = notion_helper._get_property_value(prop)
    assert result == "+41123456789"


def test_get_property_value_rich_text(notion_helper):
    """Test extracting rich_text property value."""
    prop = {
        "type": "rich_text",
        "rich_text": [
            {"plain_text": "Hello"},
            {"plain_text": " "},
            {"plain_text": "World"},
        ],
    }
    result = notion_helper._get_property_value(prop)
    assert result == "Hello World"


def test_get_property_value_date_with_end(notion_helper):
    """Test extracting date property with end date."""
    prop = {
        "type": "date",
        "date": {"start": "2024-01-15", "end": "2024-01-20"},
    }
    result = notion_helper._get_property_value(prop)
    assert result == "2024-01-15"


def test_get_property_value_title_empty(notion_helper):
    """Test extracting title when empty."""
    prop = {
        "type": "title",
        "title": [],
    }
    result = notion_helper._get_property_value(prop)
    assert result == ""


def test_get_property_value_unknown_type(notion_helper):
    """Test extracting property with unknown type."""
    prop = {
        "type": "custom_type",
        "custom_type": "value",
    }
    result = notion_helper._get_property_value(prop)
    assert result == "value"


def test_get_database_data_with_http_error(monkeypatch, notion_helper):
    """Test get_database_data handles HTTP errors."""

    class BadResponse:
        def __init__(self):
            self.status_code = 401
            self.text = "Unauthorized"
            self.request = Mock()

    def fake_post(*args, **kwargs):
        return BadResponse()

    monkeypatch.setattr("selenium_notion_autofill.utils.notion_helper.httpx.post", fake_post)

    with pytest.raises(httpx.HTTPStatusError):
        notion_helper.get_database_data("db-id")


def test_get_database_data_with_filter(monkeypatch, notion_helper):
    """Test get_database_data applies filter correctly."""

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
        return FakeResponse({"results": [], "has_more": False})

    monkeypatch.setattr("selenium_notion_autofill.utils.notion_helper.httpx.post", fake_post)

    test_filter = {"property": "Status", "select": {"equals": "Done"}}
    notion_helper.get_database_data("db-id", filter=test_filter)

    assert len(calls) == 1
    assert calls[0]["filter"] == test_filter


def test_update_row_with_successful_response(monkeypatch, notion_helper):
    """Test update_row with successful response."""

    class FakeResponse:
        def __init__(self):
            self.status_code = 200
            self.text = "ok"
            self.request = Mock()

    def fake_patch(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr("selenium_notion_autofill.utils.notion_helper.httpx.patch", fake_patch)

    result = notion_helper.update_row("page-1", {"Status": {"select": {"name": "Done"}}})
    assert result is True


def test_get_property_value_with_invalid_type(notion_helper):
    """Test _get_property_value with non-string type."""
    prop = {
        "type": 123,  # Invalid type
        "123": "value",
    }
    result = notion_helper._get_property_value(prop)
    assert result == ""


def test_get_property_value_title_concatenates_without_separator(notion_helper):
    """Regression test: plain_text fragments must be concatenated directly
    (no space inserted between them), since Notion rich text fragments already
    contain their own whitespace where needed."""
    prop = {
        "type": "title",
        "title": [{"plain_text": "Hello"}, {"plain_text": "World"}],
    }
    result = notion_helper._get_property_value(prop)
    assert result == "HelloWorld"


def test_get_property_value_rich_text_concatenates_without_separator(notion_helper):
    """Regression test: rich_text fragments must be concatenated directly."""
    prop = {
        "type": "rich_text",
        "rich_text": [{"plain_text": "foo"}, {"plain_text": "bar"}, {"plain_text": "baz"}],
    }
    result = notion_helper._get_property_value(prop)
    assert result == "foobarbaz"
