import json
from types import SimpleNamespace

from selenium_notion_autofill.utils import session_helper


class DummyDriver:
    def __init__(self):
        self.added = []
        self.cookies = [{"name": "a", "value": "1", "sameSite": "Lax"}]
        self.scripts = []

    def get_cookies(self):
        return self.cookies

    def execute_script(self, script, *args):
        # emulate returning storage when asked
        if "localStorage" in script:
            return {"k": "v"}
        self.scripts.append((script, args))
        return None

    def add_cookie(self, cookie):
        # record cookie added
        self.added.append(cookie)

    def get(self, url):
        self.last_get = url

    def refresh(self):
        self.refreshed = True


def test_save_session_writes_files(tmp_path, monkeypatch):
    cookies_file = tmp_path / "jobroom_cookies.json"
    storage_file = tmp_path / "jobroom_storage.json"

    monkeypatch.setattr(session_helper, "COOKIES_FILE", str(cookies_file))
    monkeypatch.setattr(session_helper, "STORAGE_FILE", str(storage_file))

    driver = DummyDriver()

    session_helper.save_session(driver)

    # files created
    assert cookies_file.exists()
    assert storage_file.exists()

    with open(cookies_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)

    with open(storage_file, "r", encoding="utf-8") as f:
        storage = json.load(f)
    assert "localStorage" in storage


def test__apply_cookies_removes_same_site(monkeypatch):
    driver = DummyDriver()
    cookies = [{"name": "x", "value": "y", "sameSite": "None"}]

    session_helper._apply_cookies(driver, cookies)

    assert len(driver.added) == 1
    assert "sameSite" not in driver.added[0]


def test__restore_storage_applies_items(tmp_path, monkeypatch):
    storage_file = tmp_path / "jobroom_storage.json"
    content = {"localStorage": {"a": "1"}, "sessionStorage": {"b": "2"}}
    storage_file.write_text(json.dumps(content))

    monkeypatch.setattr(session_helper, "STORAGE_FILE", str(storage_file))

    recorded = []

    class ExecDriver:
        def execute_script(self, script, *args):
            recorded.append((script, args))

    d = ExecDriver()
    session_helper._restore_storage(d)

    # two calls should be made to set items
    assert any("localStorage.setItem" in r[0] for r in recorded)
    assert any("sessionStorage.setItem" in r[0] for r in recorded)


def test_load_session_no_cookie_file(tmp_path, monkeypatch):
    # point to a non-existent cookies file
    monkeypatch.setattr(session_helper, "COOKIES_FILE", str(tmp_path / "nope.json"))
    d = DummyDriver()
    assert session_helper.load_session(d) is False


def test_load_session_success(tmp_path, monkeypatch):
    cookies_file = tmp_path / "jobroom_cookies.json"
    storage_file = tmp_path / "jobroom_storage.json"

    cookies_file.write_text(json.dumps([{"name": "c", "value": "v"}]))
    storage_file.write_text(json.dumps({"localStorage": {}}))

    monkeypatch.setattr(session_helper, "COOKIES_FILE", str(cookies_file))
    monkeypatch.setattr(session_helper, "STORAGE_FILE", str(storage_file))

    calls = SimpleNamespace(opened=False)

    class RestDriver:
        def __init__(self):
            self.added = []

        def get(self, url):
            calls.opened = True

        def add_cookie(self, c):
            self.added.append(c)

        def refresh(self):
            calls.refreshed = True

        def execute_script(self, script, *args):
            return None

    d = RestDriver()
    assert session_helper.load_session(d) is True
    assert getattr(calls, "opened") is True


def test_load_session_success_without_info_file(tmp_path, monkeypatch):
    cookies_file = tmp_path / "jobroom_cookies.json"
    storage_file = tmp_path / "jobroom_storage.json"

    cookies_file.write_text(json.dumps([{"name": "c", "value": "v"}]))
    storage_file.write_text(json.dumps({"localStorage": {}}))

    monkeypatch.setattr(session_helper, "COOKIES_FILE", str(cookies_file))
    monkeypatch.setattr(session_helper, "STORAGE_FILE", str(storage_file))
    monkeypatch.setattr(session_helper, "SESSION_INFO_FILE", str(tmp_path / "jobroom_session_info.json"))

    calls = SimpleNamespace(opened=False)

    class RestDriver:
        def __init__(self):
            self.added = []

        def get(self, url):
            calls.opened = True

        def add_cookie(self, c):
            self.added.append(c)

        def refresh(self):
            calls.refreshed = True

        def execute_script(self, script, *args):
            return None

    d = RestDriver()
    assert session_helper.load_session(d) is True
    assert getattr(calls, "opened") is True


def test_load_session_fails_with_stale_session_info(tmp_path, monkeypatch):
    cookies_file = tmp_path / "jobroom_cookies.json"
    storage_file = tmp_path / "jobroom_storage.json"
    info_file = tmp_path / "jobroom_session_info.json"

    cookies_file.write_text(json.dumps([{"name": "c", "value": "v"}]))
    storage_file.write_text(json.dumps({"localStorage": {}}))
    info_file.write_text(json.dumps({"date": "2000-01-01T00:00:00"}))

    monkeypatch.setattr(session_helper, "COOKIES_FILE", str(cookies_file))
    monkeypatch.setattr(session_helper, "STORAGE_FILE", str(storage_file))
    monkeypatch.setattr(session_helper, "SESSION_INFO_FILE", str(info_file))

    d = DummyDriver()
    assert session_helper.load_session(d) is False
    assert not cookies_file.exists()
    assert not storage_file.exists()
    assert not info_file.exists()
