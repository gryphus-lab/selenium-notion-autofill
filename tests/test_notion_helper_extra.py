from selenium_notion_autofill.utils.notion_helper import NotionHelper


def test_get_property_value_various_types():
    nh = NotionHelper(api_key="x")

    assert nh._get_property_value({}) is None

    # rich_text
    prop = {"type": "rich_text", "rich_text": [{"plain_text": "hello"}]}
    assert nh._get_property_value(prop) == "hello"

    # phone_number
    prop = {"type": "phone_number", "phone_number": "+123"}
    assert nh._get_property_value(prop) == "+123"

    # url
    prop = {"type": "url", "url": "https://x"}
    assert nh._get_property_value(prop) == "https://x"

    # select
    prop = {"type": "select", "select": {"name": "Choice"}}
    assert nh._get_property_value(prop) == "Choice"

    # multi_select
    prop = {"type": "multi_select", "multi_select": [{"name": "a"}, {"name": "b"}]}
    assert nh._get_property_value(prop) == ["a", "b"]

    # number
    prop = {"type": "number", "number": 12}
    assert nh._get_property_value(prop) == 12

    # unknown type falls back to string
    prop = {"type": "unknown", "unknown": "val"}
    assert nh._get_property_value(prop) == "val"
