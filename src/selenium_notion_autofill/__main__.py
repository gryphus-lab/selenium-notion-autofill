#!/usr/bin/env python3
"""Notion → Selenium Autofill Script - Main entry point."""

import argparse
import ast
import ipaddress
import json
import re
import shutil
import socket
import ssl
import sys
import traceback
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpcore
import httpx
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

from selenium_notion_autofill.config import (
    APPLIED_DATE,
    EXIT_MESSAGE,
    FIELD_SELECTORS,
    NOTION_PROPERTY_MAP,
    get_database_id,
    get_notion_api_key,
    validate_property_map,
)

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:  # pragma: no cover - optional dependency
    ChromeDriverManager = None
    import shutil

from selenium_notion_autofill.utils import NotionHelper
from selenium_notion_autofill.utils.notion_helper import build_notion_properties
from selenium_notion_autofill.utils.selenium_helper import (
    handle_login,
    process_records,
    update_rejected_records,
)

LAST_UPDATE_DATE = "Last Update Date"
UPDATE_DETAILS = "Update Details"
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
NOTION_RICH_TEXT_LIMIT = 2000
BLOCKED_PAGE_MESSAGE = "The website returned an access-blocked page"
OPTIONAL_CREATE_FIELDS = (
    "Description",
    "Stage",
    "Source",
    "Notes",
    LAST_UPDATE_DATE,
    UPDATE_DETAILS,
)
HOSTNAME_COMPANY_MAP = {
    r"(?:^|\.)careers\.zurich\.com$": "Zurich Insurance",
}
# og:site_name values that are the job board itself, not the employer.
_JOB_BOARD_SITE_NAMES = {"linkedin", "indeed", "jobs", "xing", "glassdoor"}


class _DocumentTooLargeError(RuntimeError):
    """Raised when a scraped response exceeds the document size limit."""


def extract_formatted_field(val):
    """Extract formatted field value from string representation.

    Args:
        val: Value to extract from

    Returns:
        The extracted string value or original value if extraction fails
    """
    if val is None:
        return val
    try:
        parsed = ast.literal_eval(str(val))
    except (ValueError, SyntaxError, TypeError):
        return val
    else:
        if isinstance(parsed, dict):
            return parsed.get("string")
        return val


def _first_monday_on_or_after(date_value):
    """Return the first Monday on or after the given datetime."""
    days_until_monday = (7 - date_value.weekday()) % 7
    if days_until_monday == 0:
        return date_value
    return date_value + timedelta(days=days_until_monday)


def _get_open_period():
    """Calculate the start and end of the current open NpA period.

    The open period runs from the first day of the reference month until
    the first Monday of the following month.
    """
    now = datetime.now(timezone.utc)
    first_of_current = datetime(now.year, now.month, 1)
    first_of_next = (
        datetime(now.year + 1, 1, 1)
        if now.month == 12
        else datetime(now.year, now.month + 1, 1)
    )

    first_monday_current = _first_monday_on_or_after(first_of_current)
    first_monday_next = _first_monday_on_or_after(first_of_next)

    if now.date() < first_monday_current.date():
        start_of_period = (
            datetime(now.year - 1, 12, 1)
            if now.month == 1
            else datetime(now.year, now.month - 1, 1)
        )
        end_of_period = first_monday_current
    else:
        start_of_period = first_of_current
        end_of_period = first_monday_next

    return start_of_period.strftime("%Y-%m-%d"), end_of_period.strftime("%Y-%m-%d")


def get_month_filter():
    """Get filter for untracked records in the current open NpA period.

    Returns:
        Dictionary with Notion filter criteria
    """
    start_date, end_date = _get_open_period()

    return {
        "and": [
            {"property": APPLIED_DATE, "date": {"on_or_after": start_date}},
            {"property": APPLIED_DATE, "date": {"before": end_date}},
            {"property": "Tracked", "checkbox": {"equals": False}},
        ]
    }


def get_rejected_filter():
    """Get filter for tracked records that are now rejected in the open period.

    These are entries already submitted to Job-Room (Tracked=True) with
    Stage='Rejected' that need their status updated from 'Noch offen' to 'Absage'.
    """
    start_date, end_date = _get_open_period()

    return {
        "and": [
            {"property": APPLIED_DATE, "date": {"on_or_after": start_date}},
            {"property": APPLIED_DATE, "date": {"before": end_date}},
            {"property": "Tracked", "checkbox": {"equals": False}},
            {"property": "Stage", "status": {"equals": "Rejected"}},
        ]
    }


def prepare_dataframe(df):
    """Prepare and transform dataframe for processing.

    Args:
        df: Dataframe to prepare
    """
    if "Date" in df.columns:
        df["Date"] = df["Date"].apply(extract_formatted_field)
    if "Type" in df.columns:
        df["Type"] = df["Type"].apply(extract_formatted_field)

    df["PLZ_Ort"] = df["PLZ_Ort"].astype(str).str[:4]
    df["RAV"] = "false"
    df["Arbeitspensum"] = "false"
    df["Status"] = "false"

    for column in df.columns:
        print(f"{column}: {df[column].iloc[0]}")


def _create_driver():
    """Create and return a Selenium Chrome WebDriver instance.

    Returns:
        Tuple of (driver, wait)
    """
    options = Options()
    options.add_argument("--start-maximized")

    if ChromeDriverManager:
        service = Service(ChromeDriverManager().install())
    else:
        chromedriver_path = shutil.which("chromedriver")
        if not chromedriver_path:
            raise RuntimeError(
                "webdriver_manager not installed and chromedriver not found in PATH. "
                "Install webdriver-manager or ensure chromedriver is available."
            )
        service = Service(chromedriver_path)

    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 20)
    return driver, wait


CREATE_USAGE = (
    "uv run -m selenium_notion_autofill create <url> [--dry-run] "
    "[--prop-map=path] [--company=NAME] [--role=TITLE]"
)


def _create_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uv run -m selenium_notion_autofill create")
    parser.add_argument("url")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prop-map")
    parser.add_argument("--company", dest="company_override")
    parser.add_argument("--role", dest="role_override")
    return parser


def _load_prop_name_map(prop_map: str | None) -> dict[str, str] | None:
    if not prop_map:
        return None

    try:
        base_dir = Path.cwd().resolve()
        prop_map_path = Path(prop_map).resolve()
        if not prop_map_path.is_relative_to(base_dir):
            raise ValueError("path must be inside the current working directory")

        with prop_map_path.open("r", encoding="utf-8") as fh:
            parsed_map = json.load(fh)
        return validate_property_map(parsed_map)
    except Exception as exc:
        print(f"Could not load prop-map file {prop_map}: {exc}")
        sys.exit(1)


def _run_create_from_args(notion, args: list[str]) -> None:
    if not args:
        print(f"Usage: {CREATE_USAGE}")
        sys.exit(1)

    parsed_args = _create_arg_parser().parse_args(args)
    if not parsed_args.dry_run:
        notion = NotionHelper(get_notion_api_key())
    _run_create(
        notion,
        parsed_args.url,
        dry_run=parsed_args.dry_run,
        prop_name_map=_load_prop_name_map(parsed_args.prop_map),
        company_override=parsed_args.company_override,
        role_override=parsed_args.role_override,
    )


def main():
    """Main entry point for the autofill script."""
    mode = sys.argv[1] if len(sys.argv) > 1 else "new"

    if mode == "update-rejections":
        _run_update_rejections(NotionHelper(get_notion_api_key()))
    elif mode == "new":
        _run_new_entries(NotionHelper(get_notion_api_key()))
    elif mode == "create":
        _run_create_from_args(None, sys.argv[2:])
    else:
        print(f"Unknown mode: {mode}")
        print(
            "Usage: uv run -m selenium_notion_autofill [new|update-rejections|create]"
        )
        sys.exit(1)


def _run_new_entries(notion):
    """Process new untracked entries for the current month."""
    month_filter = get_month_filter()
    df = notion.get_database_data(get_database_id(), filter=month_filter)

    if df.empty:
        print("\n     ⚠️ No new records to process for this month. ")
        print("     Please check your Notion database.")
        print("     Exiting...\n")
        return

    prepare_dataframe(df)
    print(f"✅ Loaded {len(df)} new records from Notion")

    driver, wait = _create_driver()

    try:
        print("🌐 Opening Job-Room...")
        handle_login(driver)
        print("\n🚀 Starting automation...")
        process_records(driver, wait, df, notion)
    except Exception as exc:
        print(f"❌ Error: {exc}")
        try:
            driver.save_screenshot("results/jobroom_main_error.png")
        except Exception as screenshot_exc:
            print(f"   ⚠️ Could not save screenshot: {screenshot_exc}")
        traceback.print_exc()
    finally:
        input("\nPress Enter to close browser...")
        driver.quit()


def _meta_content(soup, attrs: dict[str, str]) -> str | None:
    meta = soup.find("meta", attrs=attrs)
    value = meta.get("content") if meta else None
    return value.strip() if isinstance(value, str) else None


def _scrape_with_beautifulsoup(text: str, result: dict[str, str]) -> dict[str, str]:
    soup = BeautifulSoup(text, "html.parser")
    company = _extract_company_from_soup(soup)
    if company:
        result["company"] = company

    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    content = soup.find("main") or soup.find("article") or soup.body or soup
    page_text = content.get_text("\n", strip=True)
    if page_text:
        result["text"] = re.sub(r"\n{2,}", "\n", page_text)

    if soup.title and isinstance(soup.title.string, str):
        result["title"] = soup.title.string.strip()

    description = _meta_content(soup, {"name": "description"}) or _meta_content(
        soup, {"property": "og:description"}
    )
    if description:
        result["description"] = description

    h1 = soup.find("h1")
    if h1:
        result["h1"] = h1.get_text(strip=True)
    return result


def _extract_company_from_soup(soup) -> str | None:
    """Best-effort employer/company name from a job-posting page.

    Priority: JSON-LD JobPosting hiringOrganization → LinkedIn/Indeed company
    anchors → og:site_name (unless it's the job board itself). Returns None if
    nothing reliable is found, so callers can fall back to the hostname map.
    """
    company = _extract_company_from_json_ld(soup)
    if company:
        return company

    company = _extract_company_from_selectors(soup)
    if company:
        return company

    return _extract_company_from_site_name(soup)


def _extract_company_from_json_ld(soup) -> str | None:
    """Extract an employer from JobPosting JSON-LD, including @graph nodes."""
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        company = _extract_company_from_json_ld_data(data)
        if company:
            return company
    return None


def _extract_company_from_json_ld_data(data) -> str | None:
    if isinstance(data, list):
        for node in data:
            company = _extract_company_from_json_ld_data(node)
            if company:
                return company
        return None

    if not isinstance(data, dict):
        return None

    company = _extract_company_from_json_ld_node(data)
    if company:
        return company

    graph = data.get("@graph")
    if isinstance(graph, (dict, list)):
        return _extract_company_from_json_ld_data(graph)
    return None


def _extract_company_from_json_ld_node(node) -> str | None:
    if not isinstance(node, dict):
        return None
    organization = node.get("hiringOrganization")
    if isinstance(organization, dict) and organization.get("name"):
        return str(organization["name"]).strip()
    if isinstance(organization, str) and organization.strip():
        return organization.strip()
    return None


def _extract_company_from_selectors(soup) -> str | None:
    """Extract an employer from common LinkedIn and Indeed page elements."""
    selectors = [
        ("a", {"class": re.compile(r"topcard__org-name-link|company")}),
        (None, {"class": re.compile(r"topcard__flavor")}),
        (None, {"data-testid": re.compile(r"company-name|inlineHeader-companyName")}),
        (None, {"class": re.compile(r"jobsearch-CompanyInfoContainer")}),
    ]
    for tag_name, attrs in selectors:
        element = soup.find(tag_name, attrs) if tag_name else soup.find(attrs=attrs)
        if element:
            name = element.get_text(strip=True)
            if name:
                return name
    return None


def _extract_company_from_site_name(soup) -> str | None:
    site_name = _meta_content(soup, {"property": "og:site_name"})
    if site_name and site_name.strip().lower() not in _JOB_BOARD_SITE_NAMES:
        return site_name.strip()
    return None


class _HTMLFallbackExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.description: str | None = None
        self.skip_depth = 0
        self.title_depth = 0
        self.h1_depth = 0
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if tag_name in {"script", "style", "noscript"}:
            self.skip_depth += 1
            return

        if self.skip_depth:
            return

        if tag_name == "title":
            self.title_depth += 1
        elif tag_name == "h1":
            self.h1_depth += 1
        elif tag_name == "meta":
            self._capture_meta_description(attrs)

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        elif tag_name == "title" and self.title_depth:
            self.title_depth -= 1
        elif tag_name == "h1" and self.h1_depth:
            self.h1_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return

        value = data.strip()
        if not value:
            return

        self.text_parts.append(value)
        if self.title_depth:
            self.title_parts.append(value)
        if self.h1_depth:
            self.h1_parts.append(value)

    def _capture_meta_description(self, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {
            name.lower(): value
            for name, value in attrs
            if isinstance(name, str) and isinstance(value, str)
        }
        meta_name = attr_map.get("name", "").lower()
        meta_property = attr_map.get("property", "").lower()
        if meta_name == "description" or meta_property == "og:description":
            content = attr_map.get("content", "").strip()
            if content:
                self.description = content

    def apply_to(self, result: dict[str, str]) -> dict[str, str]:
        page_text = " ".join(self.text_parts).strip()
        if page_text:
            result["text"] = page_text

        title = " ".join(self.title_parts).strip()
        if title:
            result["title"] = title

        if self.description:
            result["description"] = self.description

        h1 = " ".join(self.h1_parts).strip()
        if h1:
            result["h1"] = h1

        return result


def _scrape_with_regex(text: str, result: dict[str, str]) -> dict[str, str]:
    parser = _HTMLFallbackExtractor()
    parser.feed(text)
    parser.close()
    return parser.apply_to(result)


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    def __init__(self, address: str):
        self.address = address
        self.backend = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host,
        port,
        timeout=None,
        local_address=None,
        socket_options=None,
    ):
        return self.backend.connect_tcp(
            self.address, port, timeout, local_address, socket_options
        )

    def connect_unix_socket(self, path, timeout=None, socket_options=None):
        return self.backend.connect_unix_socket(path, timeout, socket_options)

    def sleep(self, seconds):
        return self.backend.sleep(seconds)


class _LimitedResponseStream(httpx.SyncByteStream):
    def __init__(self, core_response: httpcore.Response):
        self.core_response = core_response
        self.bytes_read = 0

    def __iter__(self):
        try:
            for chunk in self.core_response.iter_stream():
                self.bytes_read += len(chunk)
                if self.bytes_read > MAX_DOCUMENT_BYTES:
                    raise _DocumentTooLargeError("response exceeds document size limit")
                yield chunk
        finally:
            self.core_response.close()

    def close(self) -> None:
        self.core_response.close()


class _PinnedTransport(httpx.BaseTransport):
    def __init__(self, address: str, hostname: str):
        self.address = address
        self.hostname = hostname
        self.ssl_context = ssl.create_default_context(  # NOSONAR - secure TLS defaults
            purpose=ssl.Purpose.SERVER_AUTH
        )
        self.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.ssl_context.check_hostname = True
        self.ssl_context.verify_mode = ssl.CERT_REQUIRED
        self.pool = httpcore.ConnectionPool(
            ssl_context=self.ssl_context, network_backend=_PinnedNetworkBackend(address)
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        core_request = httpcore.Request(
            request.method,
            str(request.url),
            headers=request.headers.raw,
            content=request.content,
            extensions={
                **request.extensions,
                "sni_hostname": self.hostname,
            },
        )
        core_response = self.pool.handle_request(core_request)
        content_length = next(
            (
                value
                for name, value in core_response.headers
                if name.lower() == b"content-length"
            ),
            None,
        )
        if content_length is not None:
            try:
                declared_length = int(content_length)
                if declared_length < 0 or declared_length > MAX_DOCUMENT_BYTES:
                    core_response.close()
                    raise _DocumentTooLargeError("response exceeds document size limit")
            except (TypeError, ValueError):
                pass
        response_stream = _LimitedResponseStream(core_response)
        try:
            return httpx.Response(
                core_response.status,
                headers=core_response.headers,
                stream=response_stream,
                extensions=core_response.extensions,
                request=request,
            )
        except Exception:
            response_stream.close()
            raise

    def close(self) -> None:
        self.pool.close()


def _fetch_url(url: str, address: str) -> tuple[httpx.Response, str]:
    hostname = urlparse(url).hostname
    if hostname is None:
        raise ValueError("URL must include a hostname")
    with httpx.Client(
        transport=_PinnedTransport(address, hostname),
        timeout=15,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = client.get(url)
    return response, response.text or ""


def _redirect_location(response: httpx.Response) -> str | None:
    if 300 <= response.status_code < 400:
        return getattr(response, "headers", {}).get("location")
    return None


def _scrape_url(url: str) -> dict:
    """Scrape a URL to extract title, description and first h1."""
    current_url = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        address = _validate_external_url(current_url)
        try:
            resp, text = _fetch_url(current_url, address)
            location = _redirect_location(resp)
            if location and redirect_count < MAX_REDIRECTS:
                current_url = urljoin(current_url, location)
                continue
            break
        except _DocumentTooLargeError:
            print(f"   ❌ Could not fetch URL {url}: document exceeds size limit")
            return {"url": url}
        except Exception as exc:
            print(f"   ❌ Could not fetch URL {url}: {exc}")
            return {"url": url, "blocked": f"The URL could not be fetched: {exc}"}

    result = {"url": url}
    try:
        result = _scrape_with_beautifulsoup(text, result)
    except Exception:
        result = _scrape_with_regex(text, result)

    status_code = resp.status_code
    if 200 <= status_code < 300:
        heading_fields = " ".join(
            str(result.get(field, "")) for field in ("title", "h1")
        ).lower()
        text_fields = str(result.get("text", ""))[:500].lower()
        if any(
            marker in heading_fields
            for marker in ("access denied", "captcha", "unusual traffic", "robot check")
        ) or any(
            marker in text_fields
            for marker in ("access denied", "unusual traffic", "robot check")
        ):
            result["blocked"] = BLOCKED_PAGE_MESSAGE
    elif status_code in {403, 429}:
        result["blocked"] = BLOCKED_PAGE_MESSAGE
    else:
        result["blocked"] = f"The website returned HTTP {status_code}"
    return result


def _validate_external_url(url: str) -> str:
    """Reject URL targets that could be used to access local network services."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string")

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use HTTP(S) and include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("URL must not contain credentials")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("URL must not target localhost")

    return _validate_public_hostname(
        hostname,
        parsed.port or (443 if parsed.scheme == "https" else 80),
    )


def _validate_public_hostname(hostname: str, port: int) -> str:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return _validate_resolved_addresses(hostname, port)

    if not address.is_global:
        raise ValueError("URL must target a public IP address")
    return str(address)


def _validate_resolved_addresses(hostname: str, port: int) -> str:
    try:
        addresses: set[str] = {
            str(sockaddr[4][0])
            for sockaddr in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError) as exc:
        raise ValueError("URL hostname could not be resolved") from exc
    if not addresses or any(
        not ipaddress.ip_address(address).is_global for address in addresses
    ):
        raise ValueError("URL must resolve only to public IP addresses")
    return min(addresses)


def _source_from_url(url: str) -> str:
    hostname = (urlparse(url).hostname or "").rstrip(".").lower()
    if hostname == "linkedin.com" or hostname.endswith(".linkedin.com"):
        return "LinkedIn"
    if hostname == "indeed.com" or hostname.endswith(".indeed.com"):
        return "Indeed"
    return "Company site"


def _resolve_company_name(
    hostname: str,
    company_override: str | None,
    scraped_company: str | None = None,
) -> str:
    # 1) explicit override always wins
    if company_override:
        return company_override
    # 2) known hostname → company mapping (e.g. career portals)
    normalized_company = hostname.rstrip(".").lower()
    for hostname_pattern, company_name in HOSTNAME_COMPANY_MAP.items():
        if re.search(hostname_pattern, normalized_company):
            return company_name
    # 3) company scraped from the page (JobPosting/og:site_name/company element)
    if scraped_company and scraped_company.strip():
        return scraped_company.strip()
    # 4) last resort: the hostname (previous behaviour)
    return hostname


# Fields that must always be present on a newly created entry, regardless of
# whether they appear in FIELD_SELECTORS or the property map.
_ALWAYS_KEEP_CREATE_FIELDS = ("Stage",)


def _remove_unmapped_optional_properties(
    properties: dict[str, object], final_map: dict[str, str] | None
) -> None:
    for field_name in OPTIONAL_CREATE_FIELDS:
        if field_name in _ALWAYS_KEEP_CREATE_FIELDS:
            continue
        if field_name not in FIELD_SELECTORS and field_name not in (final_map or {}):
            properties.pop(field_name, None)


def _build_create_properties(
    url: str,
    scraped: dict,
    company: str,
    title: str,
) -> dict[str, object]:
    today_iso = datetime.now(timezone.utc).date().isoformat()
    values = {
        "Company": company,
        "Role": title,
        "URL": url,
        "Date": today_iso,
        "Type": "electronic",
        APPLIED_DATE: today_iso,
        "Tracked": False,
        "Stage": "Applied",
        "Source": _source_from_url(url),
        "Notes": _truncate_optional_text(scraped.get("text")),
        LAST_UPDATE_DATE: today_iso,
        UPDATE_DETAILS: "New entry",
        "Description": _truncate_optional_text(scraped.get("description")),
    }
    properties: dict[str, object] = {
        field_name: values[field_name]
        for field_name in (
            *FIELD_SELECTORS,
            APPLIED_DATE,
            *OPTIONAL_CREATE_FIELDS,
        )
        if field_name in values
    }
    # New applications always start at Stage "Applied".
    properties["Stage"] = "Applied"
    return properties


ADDRESS_FIELD = "Address"


def _existing_company_address(
    notion, company: str, final_map: dict | None
) -> str | None:
    """Return the Address of a prior entry for the same Company, if any.

    Queries the database for rows whose Company matches (case-insensitive) and
    returns the first non-empty Address found. Returns None on no match, no
    address, or any lookup failure (so creation proceeds with a blank address).
    """
    if notion is None or not company or not company.strip():
        return None
    company_prop = _actual_prop("Company", final_map)
    address_prop = _actual_prop(ADDRESS_FIELD, final_map)
    try:
        df = notion.get_database_data(
            get_database_id(),
            filter={"property": company_prop, "rich_text": {"equals": company}},
        )
    except Exception as exc:  # noqa: BLE001 - lookup is best-effort
        print(f"   ⚠️  Could not look up existing address for {company}: {exc}")
        return None
    if df is None or df.empty or address_prop not in df.columns:
        return None
    for value in df[address_prop]:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _apply_existing_company_address(
    notion, properties: dict[str, object], company: str, final_map: dict | None
) -> None:
    """Copy a known Company address onto the new entry, else leave it blank."""
    address = _existing_company_address(notion, company, final_map)
    if address:
        properties[ADDRESS_FIELD] = address
        print(f"   📍 Reused address for {company}: {address}")


def _actual_prop(canonical: str, final_map: dict | None) -> str:
    if isinstance(final_map, dict):
        return final_map.get(canonical, canonical)
    return canonical


def _truncate_optional_text(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value[:NOTION_RICH_TEXT_LIMIT]
    return None


def _build_dry_run_payload(
    properties: dict[str, object], final_map: dict[str, str] | None
) -> dict:
    return build_notion_properties(properties, final_map)


def _log_scraped_values(url: str, scraped: dict) -> None:
    print(f"🔎 Scraped values from {_escape_terminal_controls(url)}:")
    for key, value in scraped.items():
        if isinstance(value, str):
            value = f"[length={len(value)}, preview={_scraped_text_preview(value)}]"
        print(f"   {key}: {value}")


def _scraped_text_preview(value: str, limit: int = 200) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    preview = _escape_terminal_controls(normalized[:limit])
    return f"{preview}..." if len(normalized) > limit else preview


def _escape_terminal_controls(value: str) -> str:
    return re.sub(
        r"[\x00-\x1f\x7f-\x9f]",
        lambda match: f"\\x{ord(match.group()):02x}",
        value,
    )


def _log_prepared_properties(properties: dict[str, object]) -> None:
    print("📝 Values prepared for Notion:")
    for key, value in properties.items():
        if isinstance(value, str):
            value = f"[length={len(value)}, preview={_scraped_text_preview(value)}]"
        print(f"   {key}: {value}")


def _resolve_property_map(prop_name_map: dict | None) -> dict | None:
    selected_map = prop_name_map if prop_name_map else NOTION_PROPERTY_MAP
    return validate_property_map(selected_map) if selected_map else None


def _create_notion_page(notion, properties: dict[str, object], final_map: dict | None):
    if final_map:
        return notion.create_page(
            get_database_id(), properties, prop_name_map=final_map
        )
    return notion.create_page(get_database_id(), properties)


def _run_create(
    notion,
    url: str,
    dry_run: bool = False,
    prop_name_map: dict | None = None,
    company_override: str | None = None,
    role_override: str | None = None,
):
    """Create a Notion page using the same property names the Selenium script expects.

    The database field names must align with `FIELD_SELECTORS` keys, which are the
    same names used by the rest of the automation. This keeps the new URL entry
    feature consistent with the Job-Room autofill flow.
    """
    try:
        scraped = _scrape_url(url)
    except ValueError as exc:
        print(f"❌ Could not scrape URL {url}: {exc}")
        sys.exit(1)

    _log_scraped_values(url, scraped)
    if scraped.get("blocked"):
        print(f"❌ Notion entry was not created: {scraped['blocked']}")
        sys.exit(1)

    final_map = _resolve_property_map(prop_name_map)

    parsed = urlparse(url)
    hostname = parsed.hostname or parsed.netloc or url

    title = role_override or scraped.get("h1") or scraped.get("title") or hostname
    company = _resolve_company_name(hostname, company_override, scraped.get("company"))
    properties = _build_create_properties(url, scraped, company, title)
    _remove_unmapped_optional_properties(properties, final_map)
    # Dry-run must not touch the Notion API; only look up a reusable address for
    # a real create.
    if not dry_run:
        _apply_existing_company_address(notion, properties, company, final_map)

    _log_prepared_properties(properties)

    if dry_run:
        notion_payload = _build_dry_run_payload(properties, final_map)
        print("--- Dry run: Notion payload to create ---")
        print(notion_payload)
        print("--- End payload ---")
        return

    page_id = _create_notion_page(notion, properties, final_map)

    if page_id:
        print(f"✅ Created Notion entry for {url} -> {page_id}")
    else:
        print(f"❌ Failed to create Notion entry for {url}")
        sys.exit(1)


def _filter_rejected_records(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        df["Update Details"].apply(
            lambda value: pd.notna(value) and str(value).strip() != ""
        )
    ].reset_index(drop=True)


def _print_rejected_records(df: pd.DataFrame) -> None:
    print(f"✅ Found {len(df)} rejected records to update on Job-Room")
    print("\nRecords to update:")
    for _, row in df.iterrows():
        company = row.get("Company", "N/A")
        role = row.get("Role", "N/A")
        update_date = row.get("Last Update Date", "N/A")
        print(f"   • {company} - {role} (rejected: {update_date})")


def _process_rejected_records(driver, wait, df, notion) -> None:
    try:
        print("\n🌐 Opening Job-Room...")
        handle_login(driver)
        print("\n🔄 Updating rejected entries...")
        update_rejected_records(driver, wait, df, notion)
    except Exception as exc:
        print(f"❌ Error: {exc}")
        try:
            driver.save_screenshot("results/jobroom_update_main_error.png")
        except Exception as screenshot_exc:
            print(f"   ⚠️ Could not save screenshot: {screenshot_exc}")
        traceback.print_exc()
    finally:
        input("\nPress Enter to close browser...")
        driver.quit()


def _run_update_rejections(notion):
    """Update existing entries that have been rejected since submission."""
    rejected_filter = get_rejected_filter()
    df = notion.get_database_data(get_database_id(), filter=rejected_filter)

    if df.empty:
        print("\n     ⚠️ No rejected records to update for this month.")
        print("     All entries are either still open or already updated.")
        print(EXIT_MESSAGE)
        return

    df = _filter_rejected_records(df)

    if df.empty:
        print("\n     ⚠️ Rejected records found but none have Update Details.")
        print("     Please add rejection reasons in Notion first.")
        print(EXIT_MESSAGE)
        return

    _print_rejected_records(df)

    driver, wait = _create_driver()
    _process_rejected_records(driver, wait, df, notion)


if __name__ == "__main__":
    main()
