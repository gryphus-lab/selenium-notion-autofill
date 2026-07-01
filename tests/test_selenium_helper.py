from types import SimpleNamespace

from selenium_notion_autofill.utils import selenium_helper


def test_resolve_type_selector_known():
    assert "electronic" in selenium_helper.resolve_type_selector("electronic")
    assert "phone" in selenium_helper.resolve_type_selector("phone")
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

    df = DataFrameLike({"Applied date": ["2026-07-01", "2026-08-15", None, "invalid"]})

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

    fallback_entry = selenium_helper._find_existing_entry(
        Driver([Entry("Acme Consulting Engineer")]), "Acme", "Developer"
    )
    assert fallback_entry is None


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

