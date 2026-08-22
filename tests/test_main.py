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


def _client_for_response(response):
    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url):
            return response

    return FakeClient()


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

    def create_page(self, database_id, properties, prop_name_map=None):
        self.calls.append((database_id, properties, prop_name_map))
        return "new-page-id"


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


def test_scrape_url_extracts_metadata_with_beautifulsoup(monkeypatch):
    class Response:
        text = (
            "<html><title>Engineer</title>"
            '<meta name="description" content="Build systems">'
            "<h1>Senior Engineer</h1></html>"
        )

    monkeypatch.setattr(
        main_mod.httpx, "Client", lambda **kwargs: _client_for_response(Response())
    )

    result = main_mod._scrape_url("https://93.184.216.34/jobs/1")

    assert result == {
        "url": "https://93.184.216.34/jobs/1",
        "title": "Engineer",
        "description": "Build systems",
        "h1": "Senior Engineer",
        "text": "Engineer\nSenior Engineer",
    }


def test_scrape_url_uses_og_description_and_regex_fallback(monkeypatch):
    class Response:
        text = (
            "<html><title>Engineer</title>"
            '<meta property="og:description" content="Ship products">'
            "<h1>Platform Engineer</h1></html>"
        )

    monkeypatch.setattr(
        main_mod.httpx, "Client", lambda **kwargs: _client_for_response(Response())
    )
    monkeypatch.setattr(
        main_mod,
        "BeautifulSoup",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("parser error")),
    )

    result = main_mod._scrape_url("https://93.184.216.34/jobs/2")

    assert result["title"] == "Engineer"
    assert result["description"] == "Ship products"
    assert result["h1"] == "Platform Engineer"


def test_regex_page_text_excludes_noscript_content():
    result = main_mod._scrape_with_regex(
        "<html><body><noscript>secret</noscript><p>Visible job</p></body></html>",
        {"url": "https://93.184.216.34/jobs/1"},
    )

    assert result["text"] == "Visible job"


def test_scrape_url_allows_captcha_in_valid_description(monkeypatch):
    class Response:
        status_code = 200
        text = (
            "<html><title>Engineer</title><h1>Engineer</h1>"
            "<p>CAPTCHA training.</p></html>"
        )

    monkeypatch.setattr(
        main_mod.httpx,
        "Client",
        lambda **kwargs: _client_for_response(Response()),
    )

    assert "blocked" not in main_mod._scrape_url("https://93.184.216.34/jobs/1")


def test_scrape_url_marks_blocking_body_text(monkeypatch):
    class Response:
        status_code = 200
        text = (
            "<html><title>Engineer</title><h1>Engineer</h1>"
            "<body>Access Denied</body></html>"
        )

    monkeypatch.setattr(
        main_mod.httpx,
        "Client",
        lambda **kwargs: _client_for_response(Response()),
    )

    result = main_mod._scrape_url("https://93.184.216.34/jobs/blocked-body")

    assert result["blocked"] == "The website returned an access-blocked page"


def test_scrape_url_marks_access_blocked_pages(monkeypatch):
    class Response:
        status_code = 403
        text = "<html><title>Blocked - Indeed.com</title><h1>Access Denied</h1></html>"

    monkeypatch.setattr(
        main_mod.httpx, "Client", lambda **kwargs: _client_for_response(Response())
    )

    result = main_mod._scrape_url("https://93.184.216.34/jobs/blocked")

    assert result["blocked"] == "The website returned an access-blocked page"


def test_scrape_url_marks_403_and_429_blocked_regardless_of_content(monkeypatch):
    """403 and 429 status codes should always be marked as blocked, even if
    the response content doesn't contain blocking markers."""

    # Test 403 with normal-looking content
    class Response403:
        status_code = 403
        text = "<html><title>Job Opening</title><h1>Software Engineer</h1></html>"

    monkeypatch.setattr(
        main_mod.httpx, "Client", lambda **kwargs: _client_for_response(Response403())
    )
    result = main_mod._scrape_url("https://93.184.216.34/jobs/1")
    assert result["blocked"] == "The website returned an access-blocked page"

    # Test 429 with normal-looking content
    class Response429:
        status_code = 429
        text = "<html><title>Job Opening</title><h1>Software Engineer</h1></html>"

    monkeypatch.setattr(
        main_mod.httpx, "Client", lambda **kwargs: _client_for_response(Response429())
    )
    result = main_mod._scrape_url("https://93.184.216.34/jobs/2")
    assert result["blocked"] == "The website returned an access-blocked page"


def test_run_create_does_not_create_page_for_blocked_scrape(monkeypatch, capsys):
    monkeypatch.setattr(
        main_mod,
        "_scrape_url",
        lambda url: {"url": url, "title": "Access Denied", "blocked": "blocked"},
    )
    notion = FakeNotion()

    main_mod._run_create(notion, "https://93.184.216.34/jobs/blocked")

    output = capsys.readouterr().out
    assert "Notion entry was not created: blocked" in output
    assert notion.calls == []


def test_scrape_url_returns_url_when_fetch_fails(monkeypatch):
    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url):
            raise RuntimeError("network unavailable")

    def raise_error(**kwargs):
        return FakeClient()

    monkeypatch.setattr(main_mod.httpx, "Client", raise_error)

    assert main_mod._scrape_url("https://93.184.216.34/jobs/3") == {
        "url": "https://93.184.216.34/jobs/3"
    }


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "https://user:password@example.com/",
    ],
)
def test_scrape_url_rejects_ssrf_targets(url, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("network request should not be made")

    monkeypatch.setattr(main_mod.httpx, "Client", fail_if_called)

    with pytest.raises(ValueError):
        main_mod._scrape_url(url)


def test_scrape_url_disables_redirects(monkeypatch):
    calls = []

    class Response:
        text = ""

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url):
            calls.append(url)
            return Response()

    monkeypatch.setattr(main_mod.httpx, "Client", FakeClient)

    main_mod._scrape_url("https://93.184.216.34/jobs/4")

    assert calls[1] == "https://93.184.216.34/jobs/4"
    assert calls[0]["follow_redirects"] is False
    assert calls[0]["trust_env"] is False


def test_scrape_url_uses_validated_dns_address(monkeypatch):
    calls = []

    monkeypatch.setattr(
        main_mod.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs["transport"].address)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url):
            return type("Response", (), {"text": ""})()

    monkeypatch.setattr(main_mod.httpx, "Client", FakeClient)

    main_mod._scrape_url("https://example.com/job")

    assert calls == ["93.184.216.34"]


def test_scrape_url_pins_to_validated_address_preventing_dns_rebinding(monkeypatch):
    """Regression test: ensure the request uses the validated public IP even if
    DNS would later resolve to a private address (DNS rebinding attack)."""
    resolve_calls = []

    def resolve_once_public_then_private(*args, **kwargs):
        hostname = args[0]
        resolve_calls.append(hostname)
        if len(resolve_calls) == 1:
            # First call during validation: return public IP
            return [(2, 1, 6, "", ("93.184.216.34", 443))]
        else:
            # Hypothetical second call (should not happen): return private IP
            return [(2, 1, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(
        main_mod.socket, "getaddrinfo", resolve_once_public_then_private
    )

    connected_address = None

    class FakeClient:
        def __init__(self, **kwargs):
            nonlocal connected_address
            connected_address = kwargs["transport"].address

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url):
            return type("Response", (), {"status_code": 200, "text": ""})()

    monkeypatch.setattr(main_mod.httpx, "Client", FakeClient)

    main_mod._scrape_url("https://example.com/job")

    # Verify DNS was only called once (during validation)
    assert resolve_calls == ["example.com"]
    # Verify the connection used the validated public IP, not any later resolution
    assert connected_address == "93.184.216.34"


def test_log_scraped_values_bounds_page_text(capsys):
    text = "secret " * 100

    main_mod._log_scraped_values("https://example.com/job", {"text": text})

    output = capsys.readouterr().out
    assert f"length={len(text)}" in output
    assert text not in output


def test_scrape_url_accepts_hostname_with_public_dns(monkeypatch):
    monkeypatch.setattr(
        main_mod.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (10, 1, 6, "", ("2001:4860:4860::8888", 443, 0, 0))
        ],
    )
    monkeypatch.setattr(
        main_mod.httpx,
        "Client",
        lambda **kwargs: _client_for_response(
            type("Response", (), {"status_code": 200, "text": ""})()
        ),
    )

    assert main_mod._scrape_url("https://example.com/job")["url"] == (
        "https://example.com/job"
    )


def test_run_create_dry_run_builds_mapped_payload(monkeypatch, capsys):
    monkeypatch.setattr(
        main_mod,
        "_scrape_url",
        lambda url: {
            "url": url,
            "title": "Scraped title",
            "description": "Scraped description",
        },
    )
    notion = FakeNotion()

    main_mod._run_create(
        notion,
        "https://93.184.216.34/jobs/1",
        dry_run=True,
        prop_name_map={"Company": "Firma", "Role": "Stelle"},
        company_override="Acme",
        role_override="Developer",
    )

    output = capsys.readouterr().out
    assert "🔎 Scraped values from https://93.184.216.34/jobs/1:" in output
    assert "   title: [length=13, preview=Scraped title]" in output
    assert "📝 Values prepared for Notion:" in output
    assert "   Company: [length=4, preview=Acme]" in output
    assert "   Role: [length=9, preview=Developer]" in output
    assert "   Stage:" not in output
    assert "   Source:" not in output
    assert "   Notes:" not in output
    assert "   Last Update Date:" not in output
    assert "   Update Details:" not in output
    assert "'Firma': {'rich_text': [{'text': {'content': 'Acme'}}]}" in output
    assert "'Stelle': {'title': [{'text': {'content': 'Developer'}}]}" in output
    assert "'URL': {'url': 'https://93.184.216.34/jobs/1'}" in output
    assert notion.calls == []


def test_run_create_populates_zurich_fields(monkeypatch):
    monkeypatch.setattr(
        main_mod,
        "_scrape_url",
        lambda url: {
            "url": url,
            "title": "Verbose page title",
            "h1": "Head Legal IT and Operations 80-100%",
            "text": "Job description text",
        },
    )
    notion = FakeNotion()

    main_mod._run_create(
        notion,
        "https://www.careers.zurich.com/job/1369843657",
    )

    _, properties, _ = notion.calls[0]
    assert properties["Company"] == "Zurich Insurance"
    assert properties["Role"] == "Head Legal IT and Operations 80-100%"
    assert "Stage" not in properties
    assert "Source" not in properties
    assert "Notes" not in properties
    assert "Last Update Date" not in properties
    assert "Update Details" not in properties


@pytest.mark.parametrize(
    ("url", "expected_source"),
    [
        ("https://www.linkedin.com/jobs/view/123", "LinkedIn"),
        ("https://ch.indeed.com/viewjob?jk=123", "Indeed"),
        ("https://www.careers.zurich.com/job/123", "Company site"),
        ("https://notlinkedin.com/jobs/123", "Company site"),
        ("https://linkedin.com.example/jobs/123", "Company site"),
        ("https://indeed.com.example/jobs/123", "Company site"),
    ],
)
def test_build_create_properties_sets_source_from_url(url, expected_source):
    properties = main_mod._build_create_properties(
        url,
        {"text": "Job description"},
        "Example Company",
        "Engineer",
    )

    assert properties["Source"] == expected_source


def test_load_prop_name_map_rejects_path_outside_working_directory(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    outside_path = tmp_path.parent / "prop_map.json"
    outside_path.write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit):
        main_mod._load_prop_name_map(str(outside_path))


def test_load_prop_name_map_accepts_file_in_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prop_map_path = tmp_path / "prop_map.json"
    prop_map_path.write_text('{"Company": "Firma"}', encoding="utf-8")

    assert main_mod._load_prop_name_map("./prop_map.json") == {"Company": "Firma"}


@pytest.mark.parametrize(
    "content", ["[]", '{"Company": 1}', '{"Company": ["Firma"]}']
)
def test_load_prop_name_map_rejects_non_string_object_maps(
    tmp_path, monkeypatch, content
):
    monkeypatch.chdir(tmp_path)
    prop_map_path = tmp_path / "prop_map.json"
    prop_map_path.write_text(content, encoding="utf-8")

    with pytest.raises(SystemExit):
        main_mod._load_prop_name_map("./prop_map.json")


def test_run_create_calls_notion_with_default_mapping(monkeypatch):
    monkeypatch.setattr(
        main_mod,
        "_scrape_url",
        lambda url: {"url": url, "h1": "Data Engineer"},
    )
    notion = FakeNotion()

    main_mod._run_create(notion, "https://93.184.216.34/jobs/2")

    database_id, properties, prop_name_map = notion.calls[0]
    assert database_id == main_mod.DATABASE_ID
    assert properties["Company"] == "93.184.216.34"
    assert properties["Role"] == "Data Engineer"
    assert properties["URL"] == "https://93.184.216.34/jobs/2"
    assert properties["Type"] == "electronic"
    assert properties["Applied date"]
    assert "Stage" not in properties
    assert "Source" not in properties
    assert "Notes" not in properties
    assert "Last Update Date" not in properties
    assert "Update Details" not in properties
    assert "Tracked" not in properties
    assert prop_name_map is None


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


def test_extract_formatted_field_with_non_dict_parsed_value():
    """When ast.literal_eval succeeds but doesn't produce a dict, the
    original value should be returned unchanged (not None)."""
    assert main_mod.extract_formatted_field("123") == "123"
    assert main_mod.extract_formatted_field("[1, 2, 3]") == "[1, 2, 3]"
    assert main_mod.extract_formatted_field(123) == 123


def test_extract_formatted_field_dict_without_string_key():
    """Test extract_formatted_field with dict missing the 'string' key."""
    result = main_mod.extract_formatted_field("{'other': 'value'}")
    assert result is None


def test_get_month_filter_uses_applied_date_for_both_conditions():
    """Regression test: both date conditions in get_month_filter must use
    the APPLIED_DATE constant (previously the 'before' clause used a
    hardcoded 'Applied date' string, which happened to match but was
    inconsistent with the constant)."""
    month_filter = main_mod.get_month_filter()
    assert month_filter["and"][0]["property"] == main_mod.APPLIED_DATE
    assert month_filter["and"][1]["property"] == main_mod.APPLIED_DATE
    assert "before" in month_filter["and"][1]["date"]


def test_run_update_rejections_handles_screenshot_failure(monkeypatch):
    """Test _run_update_rejections gracefully handles a failing screenshot
    save when an exception occurs during update_rejected_records."""
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

    class ScreenshotFailingDriver(FakeDriver):
        def save_screenshot(self, path):
            raise OSError("disk full")

    driver = ScreenshotFailingDriver()
    wait = FakeWait(driver, 1)

    printed = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(args))
    monkeypatch.setattr(main_mod, "get_rejected_filter", lambda: {"filter": "rejected"})
    monkeypatch.setattr(main_mod, "_create_driver", lambda: (driver, wait))
    monkeypatch.setattr(main_mod, "handle_login", lambda driver: None)

    def raise_exc(driver, wait, df, notion):
        raise RuntimeError("Test error")

    monkeypatch.setattr(main_mod, "update_rejected_records", raise_exc)
    monkeypatch.setattr(builtins, "input", lambda *args, **kwargs: "")

    main_mod._run_update_rejections(notion)

    assert driver.quit_called
    assert any(
        "Could not save screenshot" in item
        for args in printed
        for item in args
        if isinstance(item, str)
    )
