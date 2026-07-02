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
    NOTION_API_KEY,
)

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:  # pragma: no cover - optional dependency
    ChromeDriverManager = None
    import shutil

from selenium_notion_autofill.utils import NotionHelper
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
    try:
        return ast.literal_eval(str(val)).get("string")
    except (ValueError, SyntaxError, TypeError):
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

    if mode == "update-rejections":
        _run_update_rejections(notion)
    elif mode == "new":
        _run_new_entries(notion)
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: uv run -m selenium_notion_autofill [new|update-rejections]")
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
        driver.save_screenshot("results/jobroom_main_error.png")
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

    # Filter to only those with Update Details (rejection reason)
    df = df[
        df["Update Details"].apply(
            lambda x: pd.notna(x) and str(x).strip() != ""
        )
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
