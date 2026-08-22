#!/usr/bin/env python3
"""Notion → Selenium Autofill Script - Main entry point."""

import argparse
import ast
import ipaddress
import json
import re
import shutil
import socket
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

from selenium_notion_autofill.config import (
    APPLIED_DATE,
    DATABASE_ID,
    EXIT_MESSAGE,
    FIELD_SELECTORS,
    NOTION_API_KEY,
    NOTION_PROPERTY_MAP,
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
            return json.load(fh)
    except Exception as exc:
        print(f"Could not load prop-map file {prop_map}: {exc}")
        sys.exit(1)


def _run_create_from_args(notion, args: list[str]) -> None:
    if not args:
        print(f"Usage: {CREATE_USAGE}")
        sys.exit(1)

    parsed_args = _create_arg_parser().parse_args(args)
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

    notion = NotionHelper(NOTION_API_KEY)
    if mode == "update-rejections":
        _run_update_rejections(notion)
    elif mode == "new":
        _run_new_entries(notion)
    elif mode == "create":
        _run_create_from_args(notion, sys.argv[2:])
    else:
        print(f"Unknown mode: {mode}")
        print(
            "Usage: uv run -m selenium_notion_autofill [new|update-rejections|create]"
        )
        sys.exit(1)


def _run_new_entries(notion):
    """Process new untracked entries for the current month."""
    month_filter = get_month_filter()
    df = notion.get_database_data(DATABASE_ID, filter=month_filter)

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


def _scrape_with_regex(text: str, result: dict[str, str]) -> dict[str, str]:
    m = re.search(r"<title>([^<]*+)</title>", text, re.IGNORECASE | re.DOTALL)
    if m:
        result["title"] = m.group(1).strip()

    for attribute, attribute_value in (
        ("name", "description"),
        ("property", "og:description"),
    ):
        tags = re.findall(r"<meta\b[^>]*>", text, re.IGNORECASE)
        attribute_pattern = (
            rf"\b{attribute}\s*=\s*[\"']{re.escape(attribute_value)}[\"']"
        )
        for tag in tags:
            if re.search(attribute_pattern, tag, re.IGNORECASE):
                content = re.search(
                    r"\bcontent\s*=\s*[\"']([^\"']*)[\"']", tag, re.IGNORECASE
                )
                if content:
                    result["description"] = content.group(1).strip()
                    break
        if "description" in result:
            break

    m = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.IGNORECASE | re.DOTALL)
    if m:
        result["h1"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()

    return result


def _scrape_url(url: str) -> dict:
    """Scrape a URL to extract title, description and first h1."""
    _validate_external_url(url)
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=False)
        text = resp.text or ""
    except Exception as exc:
        print(f"   ❌ Could not fetch URL {url}: {exc}")
        return {"url": url}

    result = {"url": url}
    try:
        result = _scrape_with_beautifulsoup(text, result)
    except Exception:
        result = _scrape_with_regex(text, result)

    if any(
        marker in text.lower()
        for marker in ("access denied", "captcha", "unusual traffic", "robot check")
    ):
        result["blocked"] = "The website returned an access-blocked page"
    return result


def _validate_external_url(url: str) -> None:
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

    _validate_public_hostname(
        hostname,
        parsed.port or (443 if parsed.scheme == "https" else 80),
    )


def _validate_public_hostname(hostname: str, port: int) -> None:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        _validate_resolved_addresses(hostname, port)
        return

    if not address.is_global:
        raise ValueError("URL must target a public IP address")


def _validate_resolved_addresses(hostname: str, port: int) -> None:
    try:
        addresses = {
            sockaddr[4][0]
            for sockaddr in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError) as exc:
        raise ValueError("URL hostname could not be resolved") from exc
    if not addresses or any(
        not ipaddress.ip_address(address).is_global for address in addresses
    ):
        raise ValueError("URL must resolve only to public IP addresses")


def _build_create_properties(
    url: str,
    scraped: dict,
    hostname: str,
    title: str,
) -> dict[str, object]:
    today_iso = datetime.now(timezone.utc).date().isoformat()
    values = {
        "Company": hostname,
        "Role": title,
        "URL": url,
        "Date": today_iso,
        "Type": "electronic",
        APPLIED_DATE: today_iso,
        "Tracked": False,
    }
    properties: dict[str, object] = {
        field_name: values[field_name]
        for field_name in FIELD_SELECTORS
        if field_name in values
    }
    properties[APPLIED_DATE] = values[APPLIED_DATE]
    properties["Description"] = scraped.get("description") or ""
    return properties


def _build_dry_run_payload(
    properties: dict[str, object], final_map: dict[str, str] | None
) -> dict:
    return build_notion_properties(properties, final_map)


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
    scraped = _scrape_url(url)

    print(f"🔎 Scraped values from {url}:")
    for key, value in scraped.items():
        print(f"   {key}: {value}")
    if scraped.get("blocked"):
        print(f"❌ Notion entry was not created: {scraped['blocked']}")
        return

    parsed = urlparse(url)
    hostname = parsed.hostname or parsed.netloc or url

    title = role_override or scraped.get("title") or scraped.get("h1") or hostname
    hostname = company_override or hostname
    properties = _build_create_properties(url, scraped, hostname, title)
    if "Description" not in FIELD_SELECTORS and "Description" not in (
        prop_name_map or {}
    ):
        properties.pop("Description")

    print("📝 Values prepared for Notion:")
    for key, value in properties.items():
        print(f"   {key}: {value}")

    # Merge user-provided mapping if present; if not, use env config mapping if any.
    final_map = prop_name_map if prop_name_map else NOTION_PROPERTY_MAP
    final_map = final_map if (final_map and isinstance(final_map, dict)) else None

    if dry_run:
        notion_payload = _build_dry_run_payload(properties, final_map)
        print("--- Dry run: Notion payload to create ---")
        print(notion_payload)
        print("--- End payload ---")
        return

    if final_map:
        page_id = notion.create_page(DATABASE_ID, properties, prop_name_map=final_map)
    else:
        page_id = notion.create_page(DATABASE_ID, properties)

    if page_id:
        print(f"✅ Created Notion entry for {url} -> {page_id}")
    else:
        print(f"❌ Failed to create Notion entry for {url}")


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
    df = notion.get_database_data(DATABASE_ID, filter=rejected_filter)

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
