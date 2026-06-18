#!/usr/bin/env python3
"""Notion → Selenium Autofill Script - Main entry point."""

import ast
import traceback
from datetime import datetime, timezone

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

from selenium_notion_autofill.config import (
    DATABASE_ID,
    NOTION_API_KEY,
)

try:
    from webdriver_manager.chrome import ChromeDriverManager
except Exception:  # pragma: no cover - optional dependency
    ChromeDriverManager = None
    import shutil

from selenium_notion_autofill.utils import NotionHelper
from selenium_notion_autofill.utils.selenium_helper import (
    handle_login,
    process_records,
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


def get_month_filter():
    """Get filter for current month records.

    Returns:
        Dictionary with Notion filter criteria
    """
    now = datetime.now(timezone.utc)
    start_of_month = datetime(now.year, now.month, 1).strftime("%Y-%m-%d")
    if now.month == 12:
        end_of_month = datetime(now.year + 1, 1, 1).strftime("%Y-%m-%d")
    else:
        end_of_month = datetime(now.year, now.month + 1, 1).strftime("%Y-%m-%d")

    return {
        "and": [
            {"property": "Applied date", "date": {"on_or_after": start_of_month}},
            {"property": "Applied date", "date": {"before": end_of_month}},
            {"property": "Tracked", "checkbox": {"equals": False}},
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


def main():
    """Main entry point for the autofill script."""
    notion = NotionHelper(NOTION_API_KEY)
    month_filter = get_month_filter()
    df = notion.get_database_data(DATABASE_ID, filter=month_filter)

    if df.empty:
        print("\n     ⚠️ No new records to process for this month. ")
        print("     Please check your Notion database.")
        print("     Exiting...\n")
        return

    prepare_dataframe(df)
    print(f"✅ Loaded {len(df)} records from Notion")

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

    try:
        print("🌐 Opening Job-Room...")

        # Try to restore session first
        handle_login(driver)

        print("\n🚀 Starting automation...")

        process_records(driver, wait, df, notion)
    except Exception:
        print("❌ Error:")
        driver.save_screenshot("results/jobroom_main_error.png")
        traceback.print_exc()
    finally:
        input("\nPress Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    main()
