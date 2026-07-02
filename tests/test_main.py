import builtins
from datetime import datetime, timezone

import pandas as pd
import pytest

from selenium_notion_autofill import __main__ as main_mod


class FakeDriver:
    def __init__(self):
        self.screenshots = []
        self.quit_called = False
        self.current_url = "https://example.com"

    def get(self, url):
        self.current_url = url

    def save_screenshot(self, path):
        self.screenshots.append(path)

    def quit(self):
        self.quit_called = True


class FakeWait:
    def __init__(self, driver, timeout):
        self.driver = driver
        self.timeout = timeout


class FakeNotion:
    def __init__(self, df=None):
        self.df = df if df is not None else pd.DataFrame()
        self.calls = []

    def get_database_data(self, database_id, filter=None):
        self.calls.append((database_id, filter))
        return self.df.copy()

    def update_row(self, page_id, properties):
        self.calls.append((page_id, properties))
        return True


def test_extract_formatted_field_and_monday_helpers():
    assert main_mod.extract_formatted_field("{'string': 'x'}") == "x"
    assert main_mod.extract_formatted_field("bad") == "bad"

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert main_mod._first_monday_on_or_after(start) == start

    monday = datetime(2024, 1, 8, tzinfo=timezone.utc)
    assert (
        main_mod._first_monday_on_or_after(datetime(2024, 1, 7, tzinfo=timezone.utc))
        == monday
    )

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(main_mod, "datetime", FakeDateTime)
        start_date, end_date = main_mod._get_open_period()
        assert start_date
        assert end_date
    finally:
        monkeypatch.undo()


class FakeDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2024, 2, 1, tzinfo=timezone.utc)


def test_get_month_and_rejected_filters_use_shared_dates(monkeypatch):
    monkeypatch.setattr(
        main_mod, "_get_open_period", lambda: ("2024-01-01", "2024-02-05")
    )

    month_filter = main_mod.get_month_filter()
    rejected_filter = main_mod.get_rejected_filter()

    assert month_filter["and"][0]["property"] == main_mod.APPLIED_DATE
    assert rejected_filter["and"][1]["property"] == main_mod.APPLIED_DATE
    assert month_filter["and"][2]["property"] == "Tracked"
    assert rejected_filter["and"][2]["property"] == "Tracked"
    assert rejected_filter["and"][3]["property"] == "Stage"


def test_prepare_dataframe_transforms_columns():
    df = pd.DataFrame(
        [
            {
                "Date": "{'string': '2024-01-01'}",
                "Type": "{'string': 'electronic'}",
                "PLZ_Ort": "12345 Bern",
            }
        ]
    )

    main_mod.prepare_dataframe(df)

    assert df["Date"].iloc[0] == "2024-01-01"
    assert df["Type"].iloc[0] == "electronic"
    assert df["PLZ_Ort"].iloc[0] == "1234"
    assert df["RAV"].iloc[0] == "false"
    assert df["Arbeitspensum"].iloc[0] == "false"
    assert df["Status"].iloc[0] == "false"


def test_create_driver_builds_driver_and_wait(monkeypatch):
    class DummyManager:
        def install(self):
            return "/tmp/chromedriver"

    monkeypatch.setattr(main_mod, "ChromeDriverManager", DummyManager)
    monkeypatch.setattr(main_mod.shutil, "which", lambda _: "/tmp/chromedriver")
    monkeypatch.setattr(main_mod, "Service", lambda path: path)
    monkeypatch.setattr(main_mod, "WebDriverWait", FakeWait)

    created = []

    def fake_chrome(service=None, options=None):
        created.append((service, options))
        return FakeDriver()

    monkeypatch.setattr(main_mod.webdriver, "Chrome", fake_chrome)

    driver, wait = main_mod._create_driver()

    assert isinstance(driver, FakeDriver)
    assert isinstance(wait, FakeWait)
    assert created


def test_main_dispatches_modes(monkeypatch):
    calls = []
    monkeypatch.setattr(main_mod, "NotionHelper", lambda api_key: api_key)
    monkeypatch.setattr(
        main_mod, "_run_new_entries", lambda notion: calls.append(("new", notion))
    )
    monkeypatch.setattr(
        main_mod,
        "_run_update_rejections",
        lambda notion: calls.append(("update", notion)),
    )
    monkeypatch.setattr(main_mod.sys, "argv", ["prog", "new"])

    main_mod.main()
    assert calls[0][0] == "new"

    monkeypatch.setattr(main_mod.sys, "argv", ["prog", "update-rejections"])
    main_mod.main()
    assert calls[1][0] == "update"

    monkeypatch.setattr(main_mod.sys, "argv", ["prog", "invalid"])
    with pytest.raises(SystemExit):
        main_mod.main()


def test_run_new_entries_handles_empty_and_error(monkeypatch):
    notion = FakeNotion(pd.DataFrame())
    monkeypatch.setattr(main_mod, "get_month_filter", lambda: {"filter": "month"})
    monkeypatch.setattr(main_mod, "prepare_dataframe", lambda df: None)
    monkeypatch.setattr(
        main_mod, "_create_driver", lambda: (FakeDriver(), FakeWait(FakeDriver(), 1))
    )
    monkeypatch.setattr(main_mod, "handle_login", lambda driver: None)
    monkeypatch.setattr(
        main_mod, "process_records", lambda driver, wait, df, notion: None
    )
    monkeypatch.setattr(builtins, "input", lambda *args, **kwargs: "")

    main_mod._run_new_entries(notion)

    notion_with_rows = FakeNotion(pd.DataFrame([{"id": 1, "Role": "Engineer"}]))

    def raise_error(driver, wait, df, notion):
        raise RuntimeError("boom")

    monkeypatch.setattr(main_mod, "process_records", raise_error)
    monkeypatch.setattr(
        main_mod, "_create_driver", lambda: (FakeDriver(), FakeWait(FakeDriver(), 1))
    )

    main_mod._run_new_entries(notion_with_rows)


def test_run_update_rejections_handles_empty_and_success(monkeypatch):
    notion = FakeNotion(pd.DataFrame())
    monkeypatch.setattr(main_mod, "get_rejected_filter", lambda: {"filter": "rejected"})
    monkeypatch.setattr(builtins, "input", lambda *args, **kwargs: "")

    main_mod._run_update_rejections(notion)

    df = pd.DataFrame(
        [
            {
                "id": 1,
                "Company": "Acme",
                "Role": "Dev",
                "Last Update Date": "2024-01-01",
                "Update Details": "",
            }
        ]
    )
    notion = FakeNotion(df)
    main_mod._run_update_rejections(notion)

    df_with_details = pd.DataFrame(
        [
            {
                "id": 1,
                "Company": "Acme",
                "Role": "Dev",
                "Last Update Date": "2024-01-01",
                "Update Details": "reason",
            }
        ]
    )
    notion = FakeNotion(df_with_details)

    driver = FakeDriver()
    monkeypatch.setattr(
        main_mod, "_create_driver", lambda: (driver, FakeWait(driver, 1))
    )
    monkeypatch.setattr(main_mod, "handle_login", lambda driver: None)
    monkeypatch.setattr(
        main_mod, "update_rejected_records", lambda *args, **kwargs: None
    )

    main_mod._run_update_rejections(notion)
    assert driver.quit_called


def test_create_driver_with_chromedriver_manager_none(monkeypatch):
    """Test fallback when ChromeDriverManager is not available."""
    monkeypatch.setattr(main_mod, "ChromeDriverManager", None)
    monkeypatch.setattr(main_mod.shutil, "which", lambda _: "/usr/bin/chromedriver")
    monkeypatch.setattr(main_mod, "Service", lambda path: path)
    monkeypatch.setattr(main_mod, "WebDriverWait", FakeWait)

    created = []

    def fake_chrome(service=None, options=None):
        created.append((service, options))
        return FakeDriver()

    monkeypatch.setattr(main_mod.webdriver, "Chrome", fake_chrome)

    driver, wait = main_mod._create_driver()
    assert isinstance(driver, FakeDriver)
    assert created


def test_create_driver_no_chromedriver_found(monkeypatch):
    """Test error when neither ChromeDriverManager nor chromedriver in PATH."""
    monkeypatch.setattr(main_mod, "ChromeDriverManager", None)
    monkeypatch.setattr(main_mod.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="webdriver_manager not installed"):
        main_mod._create_driver()


def test_prepare_dataframe_with_missing_columns():
    """Test prepare_dataframe when Date and Type columns are missing."""
    df = pd.DataFrame(
        [
            {
                "PLZ_Ort": "12345 Bern",
                "Company": "Test Corp",
            }
        ]
    )

    main_mod.prepare_dataframe(df)

    assert df["PLZ_Ort"].iloc[0] == "1234"
    assert df["RAV"].iloc[0] == "false"
    assert "Date" not in df.columns or pd.isna(df["Date"].iloc[0])


def test_get_open_period_december_to_january(monkeypatch):
    """Test _get_open_period crossing year boundary."""

    class FakeDec(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2024, 12, 15, tzinfo=timezone.utc)

    monkeypatch.setattr(main_mod, "datetime", FakeDec)

    start_date, end_date = main_mod._get_open_period()
    assert "2024-12" in start_date
    assert "2025-01" in end_date


def test_get_open_period_january(monkeypatch):
    """Test _get_open_period in January."""

    class FakeJan(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2024, 1, 5, tzinfo=timezone.utc)

    monkeypatch.setattr(main_mod, "datetime", FakeJan)

    start_date, end_date = main_mod._get_open_period()
    assert "2023-12" in start_date or "2024-01" in start_date


def test_run_new_entries_with_screenshot_exception(monkeypatch):
    """Test _run_new_entries when exception occurs and screenshot can be saved."""
    df = pd.DataFrame([{"id": "page-1", "Role": "Engineer", "Company": "Acme"}])
    notion = FakeNotion(df)

    driver = FakeDriver()
    wait = FakeWait(driver, 1)

    monkeypatch.setattr(main_mod, "get_month_filter", lambda: {"filter": "month"})
    monkeypatch.setattr(main_mod, "prepare_dataframe", lambda df: None)
    monkeypatch.setattr(main_mod, "_create_driver", lambda: (driver, wait))
    monkeypatch.setattr(main_mod, "handle_login", lambda driver: None)

    def raise_exc(driver, wait, df, notion):
        raise ValueError("Test exception")

    monkeypatch.setattr(main_mod, "process_records", raise_exc)
    monkeypatch.setattr(builtins, "input", lambda *args, **kwargs: "")

    main_mod._run_new_entries(notion)
    assert len(driver.screenshots) > 0
    assert driver.quit_called


def test_run_update_rejections_with_exception_handling(monkeypatch):
    """Test _run_update_rejections when screenshot fails."""
    df = pd.DataFrame(
        [
            {
                "id": "page-1",
                "Company": "Acme",
                "Role": "Dev",
                "Last Update Date": "2024-01-01",
                "Update Details": "reason",
            }
        ]
    )
    notion = FakeNotion(df)

    driver = FakeDriver()
    wait = FakeWait(driver, 1)

    monkeypatch.setattr(main_mod, "get_rejected_filter", lambda: {"filter": "rejected"})
    monkeypatch.setattr(main_mod, "_create_driver", lambda: (driver, wait))
    monkeypatch.setattr(main_mod, "handle_login", lambda driver: None)

    def raise_exc(driver, wait, df, notion):
        raise RuntimeError("Test error")

    monkeypatch.setattr(main_mod, "update_rejected_records", raise_exc)
    monkeypatch.setattr(builtins, "input", lambda *args, **kwargs: "")

    main_mod._run_update_rejections(notion)
    assert driver.quit_called


def test_extract_formatted_field_with_none():
    """Test extract_formatted_field with None value."""
    result = main_mod.extract_formatted_field(None)
    assert result is None


def test_extract_formatted_field_with_dict():
    """Test extract_formatted_field with dict that has string key."""
    result = main_mod.extract_formatted_field({"string": "value"})
    assert result == "value"


def test_first_monday_various_days():
    """Test _first_monday_on_or_after for different day offsets."""
    tuesday = datetime(2024, 1, 2, tzinfo=timezone.utc)  # Tuesday
    result = main_mod._first_monday_on_or_after(tuesday)
    assert result.weekday() == 0  # Monday is 0
    assert result > tuesday

    sunday = datetime(2024, 1, 7, tzinfo=timezone.utc)  # Sunday
    result = main_mod._first_monday_on_or_after(sunday)
    assert result.weekday() == 0
    assert result == datetime(2024, 1, 8, tzinfo=timezone.utc)
