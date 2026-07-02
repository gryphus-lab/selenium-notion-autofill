from types import SimpleNamespace

from selenium.common.exceptions import TimeoutException

from selenium_notion_autofill.utils import selenium_helper


def test_resolve_type_selector_known():
    electronic_selector = selenium_helper.resolve_type_selector("electronic")
    assert electronic_selector is not None
    assert "electronic" in electronic_selector

    phone_selector = selenium_helper.resolve_type_selector("phone")
    assert phone_selector is not None
    assert "phone" in phone_selector

    assert selenium_helper.resolve_type_selector(
        {"type": "string", "string": "Vorstellungsgespräch"}
    ) == "//label[normalize-space()='Vorstellungsgespräch']"
    assert selenium_helper.resolve_type_selector("unknown") is None


def test_get_notion_scalar_value_extracts_wrapped_string():
    value = "{'type': 'string', 'string': 'Vorstellungsgespräch'}"

    assert selenium_helper.get_notion_scalar_value(value) == "Vorstellungsgespräch"
    assert (
        selenium_helper.get_notion_scalar_value({"type": "string", "string": "x"})
        == "x"
    )
    assert selenium_helper.get_notion_scalar_value("plain") == "plain"


def test_fill_text_calls_clear_and_send_keys():
    calls = SimpleNamespace(cleared=False, sent=None)

    class Elem:
        def clear(self):
            calls.cleared = True

        def send_keys(self, v):
            calls.sent = v

    e = Elem()
    selenium_helper.fill_text(e, "Role", "Developer")
    assert calls.cleared is True
    assert calls.sent == "Developer"


def test_fill_checkbox_and_radio_execute_script(monkeypatch):
    executed = []

    class Driver:
        def execute_script(self, script, element):
            executed.append(script)

    class Elem:
        def __init__(self, visible=True):
            self._vis = visible

        def is_displayed(self):
            return self._vis

    d = Driver()
    visible_elem = Elem(True)
    selenium_helper.fill_checkbox(d, visible_elem, "CheckMe")
    assert executed

    executed.clear()
    selenium_helper.fill_radio(d, visible_elem, "Radio", True)
    assert executed


def test_fill_field_type_unknown_returns_none():
    # When Type resolves to None, fill_field should return early
    result = selenium_helper.fill_field(
        None, None, "Type", "selector", "unknown", row={}
    )
    assert result is None


def test_fill_field_interview_skips_non_interview_value():
    result = selenium_helper.fill_field(
        None,
        None,
        "Interview",
        "dummy",
        {"type": "string", "string": "Electronic"},
        row={},
    )
    assert result is None


def test_fill_field_interview_clicks_wrapped_interview_value():
    executed = []
    waited_for = []

    class Elem:
        def is_displayed(self):
            return True

    class Wait:
        def until(self, arg):
            waited_for.append(arg)
            return Elem()

    class Driver:
        def execute_script(self, script, *args):
            executed.append(script)

    selenium_helper.fill_field(
        Driver(),
        Wait(),
        "Interview",
        "dummy",
        "{'type': 'string', 'string': 'Vorstellungsgespräch'}",
        row={},
    )

    assert waited_for
    assert any(script == selenium_helper.EXECUTE_SCRIPT_CLICK for script in executed)


def test_fill_field_text_branch(monkeypatch):
    class Elem:
        def __init__(self):
            self.cleared = False
            self.sent = None

        def clear(self):
            self.cleared = True

        def send_keys(self, v):
            self.sent = v

        def get_attribute(self, k):
            return self.sent or ""

    class Wait:
        def until(self, arg):
            return Elem()

    class Driver:
        def execute_script(self, *args, **kwargs):
            return None

    selenium_helper.fill_field(Driver(), Wait(), "Role", "input.foo", "Engineer")


def test_get_entries_returns_empty_on_exception():
    class Driver:
        def find_elements(self, *args, **kwargs):
            raise selenium_helper.NoSuchElementException("boom")

    assert selenium_helper._get_entries(Driver()) == []


def test_get_month_year_pairs_parses_unique_dates():
    class DataFrameLike:
        def __init__(self, values):
            self.values = values
            self.empty = False

        def get(self, key, default=None):
            return self.values.get(key, default)

    df = DataFrameLike(
        {
            "Applied date": [
                "2026-07-01",
                "2026-07-15",
                "2026-08-15",
                None,
                "invalid",
            ]
        }
    )

    assert selenium_helper._get_month_year_pairs(df) == [("2026", 7), ("2026", 8)]


def test_find_existing_entry_matches_exact_then_fallback():
    class Entry:
        def __init__(self, text):
            self.text = text

    class Driver:
        def __init__(self, entries):
            self.entries = entries

        def find_elements(self, *args, **kwargs):
            return self.entries

    exact_entry = selenium_helper._find_existing_entry(
        Driver([Entry("Acme Consulting Developer")]), "Acme", "Developer"
    )
    assert exact_entry is not None

    prefix_entry = selenium_helper._find_existing_entry(
        Driver([Entry("Acme Labs Developer")]), "Acme Solutions", "Developer"
    )
    assert prefix_entry is not None


def test_find_entry_by_company_prefix():
    class Entry:
        def __init__(self, text):
            self.text = text

    entries = [Entry("Acme GmbH")]
    result = selenium_helper._find_entry_by_company_prefix(entries, "Acme Solutions")
    assert result is not None


def test_format_absagegrund_parses_date_and_falls_back():
    assert (
        selenium_helper._format_absagegrund("2026-07-01", "Reason")
        == "01.07: Reason"
    )
    assert selenium_helper._format_absagegrund("invalid", "Reason") == (
        "invalid: Reason"
    )


def test_is_absagegrund_candidate_filters_non_reason_fields():
    class Elem:
        def __init__(self, el_id, visible=True):
            self._id = el_id
            self._visible = visible

        def get_attribute(self, key):
            return self._id if key == "id" else ""

        def is_displayed(self):
            return self._visible

    assert not selenium_helper._is_absagegrund_candidate(Elem("company-name"))
    assert selenium_helper._is_absagegrund_candidate(Elem("reason-field"))


def test_find_absagegrund_in_entry_prefers_reason_field():
    class Elem:
        def __init__(self, el_id):
            self._id = el_id

        def get_attribute(self, key):
            return self._id if key == "id" else ""

        def is_displayed(self):
            return True

    class Entry:
        def find_elements(self, by, selector):
            return [Elem("company-name"), Elem("reason-text")]

    element = selenium_helper._find_absagegrund_in_entry(Entry())
    assert element is not None
    assert element.get_attribute("id") == "reason-text"


def test_find_absagegrund_fallback_calls_wait():
    class Wait:
        def __init__(self):
            self.called = False

        def until(self, arg):
            self.called = True
            return "fallback"

    wait = Wait()
    assert selenium_helper._find_absagegrund_fallback(wait) == "fallback"
    assert wait.called


def test_fill_absagegrund_uses_fallback_if_no_inline_field(monkeypatch):
    element_state = {}

    class Elem:
        def clear(self):
            element_state["cleared"] = True

        def send_keys(self, value):
            element_state["sent"] = value

    class Entry:
        def find_elements(self, by, selector):
            return []

    class Wait:
        def until(self, arg):
            return Elem()

    class Driver:
        def execute_script(self, *args, **kwargs):
            pass

    monkeypatch.setattr(selenium_helper.time, "sleep", lambda *_: None)
    selenium_helper._fill_absagegrund(Driver(), Wait(), Entry(), "01.07: Reason")
    assert element_state["cleared"] is True
    assert element_state["sent"] == "01.07: Reason"


def test_update_notion_tracked_prints_status(monkeypatch):
    printed = []

    class Notion:
        def __init__(self, result):
            self.result = result

        def update_row(self, page_id, properties):
            assert page_id == "page123"
            assert properties == {"Tracked": {"checkbox": True}}
            return self.result

    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(args))
    selenium_helper._update_notion_tracked(Notion(True), "page123")
    selenium_helper._update_notion_tracked(Notion(False), "page123")
    assert any("Record processed" in item for args in printed for item in args)
    assert any(
        "Failed to update Notion record." in item for args in printed for item in args
    )


def test_fill_typeahead_supports_suggestion_and_enter(monkeypatch):
    monkeypatch.setattr(selenium_helper.time, "sleep", lambda *_: None)

    class Elem:
        def __init__(self):
            self.values = []
            self._displayed = True

        def is_displayed(self):
            return self._displayed

        def send_keys(self, value):
            self.values.append(value)

        def get_attribute(self, key):
            return "" if key != "value" else "Developer"

    class Suggestion:
        def click(self):
            self.clicked = True

    class Wait:
        def __init__(self, mode):
            self.mode = mode

        def until(self, arg):
            if self.mode == "suggestion":
                return Suggestion()
            raise TimeoutException("timeout")

    driver = SimpleNamespace(execute_script=lambda *args, **kwargs: None)
    element = Elem()
    selenium_helper.fill_typeahead(driver, Wait("suggestion"), element, "Role", "Developer")
    assert element.values == ["Developer"]

    fallback_element = Elem()
    selenium_helper.fill_typeahead(
        driver, Wait("timeout"), fallback_element, "Role", "Developer"
    )
    assert fallback_element.values[-1] == selenium_helper.Keys.ENTER


def test_expand_month_section_and_process_rejected_entry(monkeypatch):
    monkeypatch.setattr(selenium_helper.time, "sleep", lambda *_: None)

    class FakeElement:
        def __init__(self, text=""):
            self.text = text

    class Driver:
        def __init__(self):
            self.scripts = []
            self.find_calls = []

        def find_elements(self, by, selector):
            self.find_calls.append(selector)
            if "collapsed" in selector:
                return [FakeElement()]
            return []

        def execute_script(self, *args, **kwargs):
            self.scripts.append(args)

    class FakeRow:
        def __init__(self):
            self._values = {
                "Company": "Acme",
                "Role": "Developer",
                "Last Update Date": "2026-07-01",
                "Update Details": "No fit",
            }

        def get(self, key, default=None):
            return self._values.get(key, default)

    driver = Driver()
    df = SimpleNamespace(empty=False, get=lambda key, default=None: ["2026-07-01"])
    selenium_helper._expand_month_section(driver, df)
    assert driver.scripts

    called = {}
    monkeypatch.setattr(
        selenium_helper,
        "_find_existing_entry",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        selenium_helper,
        "_update_rejected_entry",
        lambda *args, **kwargs: called.setdefault("updated", True),
    )
    monkeypatch.setattr(
        selenium_helper,
        "_report_missing_entry",
        lambda *args, **kwargs: called.setdefault("missing", True),
    )

    selenium_helper._process_rejected_entry(driver, None, None, FakeRow(), 0, 1)
    assert called.get("updated") is True


def test_handle_login_falls_back_to_fresh_login(monkeypatch):
    monkeypatch.setattr(selenium_helper, "load_session", lambda driver: True)
    monkeypatch.setattr(selenium_helper, "save_session", lambda driver: None)
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "")
    monkeypatch.setattr(selenium_helper.time, "sleep", lambda *_: None)

    class Driver:
        def __init__(self):
            self.current_url = "https://example.com/login"
            self.visited = []

        def get(self, url):
            self.visited.append(url)

        def find_element(self, by, selector):
            return SimpleNamespace(click=lambda: None)

    driver = Driver()
    assert selenium_helper.handle_login(driver) is True
    assert driver.visited[0] == selenium_helper.WEBSITE_URL


def test_handle_login_fresh_login_with_buttons(monkeypatch):
    """Test handle_login when session is not restored and buttons are found."""
    monkeypatch.setattr(selenium_helper, "load_session", lambda driver: False)
    monkeypatch.setattr(selenium_helper, "save_session", lambda driver: None)
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "")
    monkeypatch.setattr(selenium_helper.time, "sleep", lambda *_: None)

    class Driver:
        def __init__(self):
            self.current_url = "https://example.com"
            self.visited = []
            self.find_calls = []

        def get(self, url):
            self.visited.append(url)

        def find_element(self, by, selector):
            self.find_calls.append(selector)
            return SimpleNamespace(click=lambda: None)

    driver = Driver()
    result = selenium_helper.handle_login(driver)
    assert result is True
    assert len(driver.find_calls) >= 1


def test_handle_login_missing_buttons(monkeypatch):
    """Test handle_login when buttons are not found."""
    monkeypatch.setattr(selenium_helper, "load_session", lambda driver: False)
    monkeypatch.setattr(selenium_helper, "save_session", lambda driver: None)
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "")
    monkeypatch.setattr(selenium_helper.time, "sleep", lambda *_: None)

    class Driver:
        def __init__(self):
            self.current_url = "https://example.com"

        def get(self, url):
            pass

        def find_element(self, by, selector):
            raise selenium_helper.NoSuchElementException("not found")

    driver = Driver()
    result = selenium_helper.handle_login(driver)
    assert result is True


def test_process_records_flow(monkeypatch):
    """Test process_records iterates and fills fields."""
    monkeypatch.setattr(selenium_helper.time, "sleep", lambda *_: None)
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "")

    fill_calls = []

    def fake_fill(driver, wait, field_name, selector, value, row=None):
        fill_calls.append((field_name, selector, value))

    monkeypatch.setattr(selenium_helper, "fill_field", fake_fill)

    class Driver:
        def __init__(self):
            self.visited = []

        def get(self, url):
            self.visited.append(url)

        def find_element(self, by, selector):
            return SimpleNamespace(click=lambda: None)

    class Notion:
        def update_row(self, page_id, properties):
            return True

    driver = Driver()
    df = SimpleNamespace(
        iterrows=lambda: [
            (
                0,
                {
                    "id": "page1",
                    "Role": "Engineer",
                    "Company": "Acme",
                },
            )
        ]
    )
    selenium_helper.process_records(driver, None, df, Notion())
    assert len(fill_calls) > 0


def test_resolve_type_selector_case_insensitive():
    """Test resolve_type_selector handles case variations."""
    assert selenium_helper.resolve_type_selector("ELECTRONIC") is not None
    assert selenium_helper.resolve_type_selector("Phone") is not None
    assert selenium_helper.resolve_type_selector("VORSTELLUNGSGESPRÄCH") is not None


def test_resolve_type_selector_dict_with_string():
    """Test resolve_type_selector with dict containing string key."""
    result = selenium_helper.resolve_type_selector(
        {"type": "string", "string": "vorstellungsgespräch"}
    )
    assert "Vorstellungsgespräch" in result


def test_get_notion_scalar_value_with_complex_dict():
    """Test get_notion_scalar_value with nested dict."""
    result = selenium_helper.get_notion_scalar_value(
        {"type": "rich_text", "rich_text": [{"plain_text": "text"}]}
    )
    assert result == {"type": "rich_text", "rich_text": [{"plain_text": "text"}]}


def test_fill_field_resolves_interview_type(monkeypatch):
    """Test fill_field correctly handles Interview field type."""
    waited = []
    executed = []

    class Wait:
        def until(self, arg):
            waited.append(arg)
            return SimpleNamespace(is_displayed=lambda: True)

    class Driver:
        def execute_script(self, script, elem):
            executed.append(script)

    monkeypatch.setattr(selenium_helper.time, "sleep", lambda *_: None)

    selenium_helper.fill_field(
        Driver(),
        Wait(),
        "Interview",
        "dummy",
        "vorstellungsgespräch",
        row={},
    )
    assert waited
    assert executed


def test_expand_month_section_for_each_month(monkeypatch):
    """Test _expand_month_section_for handles all month names."""
    monkeypatch.setattr(selenium_helper.time, "sleep", lambda *_: None)

    calls = []

    class Driver:
        def find_elements(self, by, selector):
            calls.append(selector)
            return [SimpleNamespace(scrollIntoView=lambda: None)]

        def execute_script(self, script, elem=None):
            pass

    driver = Driver()
    # Test multiple months
    for month in ["Januar", "Februar", "März", "April", "Mai", "Juni"]:
        calls.clear()
        selenium_helper._expand_month_section_for(driver, month, "2024")
        assert calls


def test_find_entry_with_no_entries_returns_none():
    """Test _find_existing_entry when no entries exist."""
    class Driver:
        def find_elements(self, by, selector):
            return []

    result = selenium_helper._find_existing_entry(Driver(), "Acme", "Developer")
    assert result is None


def test_find_entry_by_company_with_empty_entries():
    """Test _find_entry_by_company with empty list."""
    result = selenium_helper._find_entry_by_company([], "Acme", "Developer")
    assert result is None


def test_find_entry_by_company_prefix_with_empty_company():
    """Test _find_entry_by_company_prefix with empty company name."""
    result = selenium_helper._find_entry_by_company_prefix([], "", "Developer")
    assert result is None


def test_format_absagegrund_with_invalid_date():
    """Test _format_absagegrund gracefully handles invalid dates."""
    result = selenium_helper._format_absagegrund("not-a-date", "Reason")
    assert "Reason" in result


def test_set_status_rejected_uses_fallback_xpath(monkeypatch):
    """Test _set_status_rejected falls back to XPath."""
    monkeypatch.setattr(selenium_helper.time, "sleep", lambda *_: None)

    script_calls = []

    class Driver:
        def execute_script(self, script, elem):
            script_calls.append(script)

    class Entry:
        def find_element(self, by, selector):
            raise selenium_helper.NoSuchElementException("Not found")

    driver = Driver()
    result = selenium_helper._set_status_rejected(driver, Entry())
    assert result is False

