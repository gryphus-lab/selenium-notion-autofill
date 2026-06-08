from types import SimpleNamespace

from selenium_notion_autofill.utils import selenium_helper


def test_resolve_type_selector_known():
    assert "electronic" in selenium_helper.resolve_type_selector("electronic")
    assert "phone" in selenium_helper.resolve_type_selector("phone")
    assert selenium_helper.resolve_type_selector("unknown") is None


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
    result = selenium_helper.fill_field(None, None, "Type", "selector", "unknown", row={})
    assert result is None


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
