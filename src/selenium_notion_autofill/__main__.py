#!/usr/bin/env python3
"""Notion → Selenium Autofill Script - Main entry point."""

import ast
import shutil
import sys
import traceback
from datetime import datetime, timedelta, timezone

import pandas as pd
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
import httpx
import re
import json
from urllib.parse import urlparse
from bs4 import BeautifulSoup
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


def main():
    """Main entry point for the autofill script."""
    mode = sys.argv[1] if len(sys.argv) > 1 else "new"

    notion = NotionHelper(NOTION_API_KEY)
    # Ensure the NotionHelper sends the actual API key in Authorization
    try:
        notion.headers["Authorization"] = f"Bearer {NOTION_API_KEY}"
    except Exception:
        pass

    if mode == "update-rejections":
        _run_update_rejections(notion)
    elif mode == "new":
        _run_new_entries(notion)
    elif mode == "create":
        # Parse simple flags: --dry-run, --prop-map=path, --company=..., --role=...
        args = sys.argv[2:]
        if not args:
            print("Usage: uv run -m selenium_notion_autofill create <url> [--dry-run] [--prop-map=path] [--company=NAME] [--role=TITLE]")
            sys.exit(1)

        url = None
        dry_run = False
        prop_map = None
        company_override = None
        role_override = None

        for a in args:
            if a == "--dry-run":
                dry_run = True
                continue
            if a.startswith("--prop-map="):
                prop_map = a.split("=", 1)[1]
                continue
            if a.startswith("--company="):
                company_override = a.split("=", 1)[1]
                continue
            if a.startswith("--role="):
                role_override = a.split("=", 1)[1]
                continue
            if url is None:
                url = a

        if url is None:
            print("No URL provided")
            sys.exit(1)

        # If prop_map is a path to a JSON file, try to load it
        prop_name_map = None
        if prop_map:
            try:
                with open(prop_map, "r", encoding="utf-8") as fh:
                    prop_name_map = json.load(fh)
            except Exception as exc:
                print(f"Could not load prop-map file {prop_map}: {exc}")
                sys.exit(1)

        _run_create(notion, url, dry_run=dry_run, prop_name_map=prop_name_map, company_override=company_override, role_override=role_override)
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: uv run -m selenium_notion_autofill [new|update-rejections|create]")
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


def _scrape_url(url: str) -> dict:
    """Scrape a URL to extract title, description and first h1.

    Prefer using BeautifulSoup for robust parsing; fall back to regex if the
    parser is not available or parsing fails. Returns a dict with keys:
    title, description, h1, and url.
    """
    try:
        resp = httpx.get(url, timeout=15)
        text = resp.text or ""
    except Exception as exc:
        print(f"   ❌ Could not fetch URL {url}: {exc}")
        return {"url": url}

    result = {"url": url}

    # Try BeautifulSoup parsing first
    try:
        soup = BeautifulSoup(text, "html.parser")
        if soup.title and soup.title.string:
            result["title"] = soup.title.string.strip()

        # meta description
        desc = None
        md = soup.find("meta", attrs={"name": "description"})
        if md and md.get("content"):
            desc = md.get("content").strip()
        else:
            og = soup.find("meta", attrs={"property": "og:description"})
            if og and og.get("content"):
                desc = og.get("content").strip()
        if desc:
            result["description"] = desc

        h1 = soup.find("h1")
        if h1:
            result["h1"] = h1.get_text(strip=True)

        return result
    except Exception:
        # Fallback to regex if BeautifulSoup parsing fails
        pass

    # Regex fallback
    m = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    if m:
        result["title"] = m.group(1).strip()

    m = re.search(r"<meta[^>]+name=[\"']description[\"'][^>]*content=[\"'](.*?)[\"']", text, re.IGNORECASE | re.DOTALL)
    if m:
        result["description"] = m.group(1).strip()
    else:
        m = re.search(r"<meta[^>]+property=[\"']og:description[\"'][^>]*content=[\"'](.*?)[\"']", text, re.IGNORECASE | re.DOTALL)
        if m:
            result["description"] = m.group(1).strip()

    m = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.IGNORECASE | re.DOTALL)
    if m:
        result["h1"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()

    return result


def _run_create(notion, url: str, dry_run: bool = False, prop_name_map: dict | None = None, company_override: str | None = None, role_override: str | None = None):
    """Create a Notion page using the same property names the Selenium script expects.

    The database field names must align with `FIELD_SELECTORS` keys, which are the
    same names used by the rest of the automation. This keeps the new URL entry
    feature consistent with the Job-Room autofill flow.
    """
    scraped = _scrape_url(url)

    parsed = urlparse(url)
    hostname = parsed.hostname or parsed.netloc or url

    title = scraped.get("title") or scraped.get("h1") or hostname
    if role_override:
        title = role_override
    if company_override:
        hostname = company_override

    today_iso = datetime.now(timezone.utc).date().isoformat()

    # Build properties using the same names the Selenium form expects from Notion.
    properties: dict[str, object] = {}
    for field_name in FIELD_SELECTORS:
        if field_name == "Company":
            properties[field_name] = hostname
        elif field_name == "Role":
            properties[field_name] = title
        elif field_name == "URL":
            properties[field_name] = url
        elif field_name == "Date":
            properties[field_name] = today_iso
        elif field_name == "Type":
            properties[field_name] = "electronic"
        elif field_name == APPLIED_DATE:
            properties[field_name] = today_iso
        elif field_name == "Tracked":
            properties[field_name] = False

    # Add a couple useful extras only if the DB actually contains them.
    if "Description" in FIELD_SELECTORS or "Description" in (prop_name_map or {}):
        properties["Description"] = scraped.get("description") or ""

    # Merge user-provided mapping if present; if not, use env config mapping if any.
    final_map = prop_name_map if prop_name_map else NOTION_PROPERTY_MAP
    final_map = final_map if (final_map and isinstance(final_map, dict)) else None

    if dry_run:
        notion_payload = {}
        for key, val in properties.items():
            if val is None:
                continue
            actual_name = final_map.get(key, key) if final_map else key
            canonical = key.lower()
            if canonical == "company":
                notion_payload[actual_name] = {"title": [{"text": {"content": str(val)}}]}
            elif canonical == "role":
                notion_payload[actual_name] = {"rich_text": [{"text": {"content": str(val)}}]}
            elif canonical in ("url", "website", "link"):
                notion_payload[actual_name] = {"url": str(val)}
            elif canonical in ("email",):
                notion_payload[actual_name] = {"email": str(val)}
            elif canonical in ("phone", "phone_number"):
                notion_payload[actual_name] = {"phone_number": str(val)}
            elif isinstance(val, bool):
                notion_payload[actual_name] = {"checkbox": bool(val)}
            elif isinstance(val, (int, float)):
                notion_payload[actual_name] = {"number": val}
            else:
                notion_payload[actual_name] = {"rich_text": [{"text": {"content": str(val)}}]}

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


def _run_update_rejections(notion):
    """Update existing entries that have been rejected since submission."""
    rejected_filter = get_rejected_filter()
    df = notion.get_database_data(DATABASE_ID, filter=rejected_filter)

    if df.empty:
        print("\n     ⚠️ No rejected records to update for this month.")
        print("     All entries are either still open or already updated.")
        print(EXIT_MESSAGE)
        return

    # Filter to only those with Update Details (rejection reason)
    df = df[
        df["Update Details"].apply(lambda x: pd.notna(x) and str(x).strip() != "")
    ].reset_index(drop=True)

    if df.empty:
        print("\n     ⚠️ Rejected records found but none have Update Details.")
        print("     Please add rejection reasons in Notion first.")
        print(EXIT_MESSAGE)
        return

    print(f"✅ Found {len(df)} rejected records to update on Job-Room")
    print("\nRecords to update:")
    for _, row in df.iterrows():
        company = row.get("Company", "N/A")
        role = row.get("Role", "N/A")
        update_date = row.get("Last Update Date", "N/A")
        print(f"   • {company} - {role} (rejected: {update_date})")

    driver, wait = _create_driver()

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


if __name__ == "__main__":
    main()
