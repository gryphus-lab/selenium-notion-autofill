#!/usr/bin/env python3
"""Notion → Selenium Autofill Script - Main entry point."""

import ast
import time
import traceback
from datetime import datetime, timezone

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from selenium_notion_autofill.config import (
    DATABASE_ID,
    FIELD_SELECTORS,
    NOTION_API_KEY,
    WEBSITE_URL,
)
from selenium_notion_autofill.utils import NotionHelper

# Constants
EXECUTE_SCRIPT_CLICK = "arguments[0].click();"


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


def resolve_type_selector(value):
    """Resolve selector for Type field based on value.

    Args:
        value: The type value to resolve

    Returns:
        str: The CSS selector for the type value, or None if unknown
    """
    type_value = str(value).strip().lower()

    if type_value == "electronic":
        return "label[for*='alv-checkbox-portal'][for*='electronic']"
    elif type_value == "phone":
        return "label[for*='alv-checkbox-portal'][for*='phone']"
    else:
        print(f"   ⚠️ Unknown Type: {type_value}")
        return None


def fill_typeahead(driver, wait, element, field_name, value):
    """Fill typeahead field.

    Args:
        driver: Selenium WebDriver instance
        wait: WebDriverWait instance
        element: The element to fill
        field_name: Name of the field for logging
        value: Value to fill
    """
    if element.is_displayed():
        driver.execute_script(EXECUTE_SCRIPT_CLICK, element)

    element.send_keys(str(value))
    time.sleep(2)
    try:
        suggestion = wait.until(
            ec.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[id*='ngb-typeahead-']")
            )
        )

        suggestion.click()
        final_value = element.get_attribute("value")
        print(f"   ✓ Typeahead: {field_name} → Selected value: {final_value}")
    except Exception:
        element.send_keys(Keys.ENTER)
        final_value = element.get_attribute("value")
        print(f"   ✓ Typeahead (Enter): {field_name} - Selected value: {final_value}")


def fill_checkbox(driver, element, field_name):
    """Fill checkbox field.

    Args:
        driver: Selenium WebDriver instance
        element: The checkbox element
        field_name: Name of the field for logging
    """
    if element.is_displayed():
        driver.execute_script(EXECUTE_SCRIPT_CLICK, element)
        print(f"   ✓ Checked {field_name}")
    else:
        print(f"   ⚠️ Checkbox not visible: {field_name}")


def fill_radio(driver, element, field_name, value):
    """Fill radio button field.

    Args:
        driver: Selenium WebDriver instance
        element: The radio button element
        field_name: Name of the field for logging
        value: Value indicating if it should be selected
    """
    if value:
        driver.execute_script(EXECUTE_SCRIPT_CLICK, element)
        print(f"   ✓ Selected radio {field_name}")


def fill_text(element, field_name, value):
    """Fill text input field.

    Args:
        element: The input element
        field_name: Name of the field for logging
        value: Value to fill
    """
    element.clear()
    element.send_keys(str(value))
    print(f"   ✓ Filled {field_name} → {value}")


def fill_field(driver, wait, field_name, selector, value, row=None):
    """Smart field filler with special handling for Type checkboxes.

    Args:
        driver: Selenium WebDriver instance
        wait: WebDriverWait instance
        field_name: Name of the field
        selector: CSS selector for the field
        value: Value to fill
        row: Optional row data for context
    """
    try:
        if field_name == "Type" and row is not None:
            selector = resolve_type_selector(value)
            if selector is None:
                return
            print(f"   → Setting Type to: {str(value).strip().lower()}")

        element = wait.until(
            ec.presence_of_element_located((By.CSS_SELECTOR, selector))
        )

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", element
        )
        time.sleep(0.8)

        if "single-typeahead" in selector or "typeahead" in selector.lower():
            fill_typeahead(driver, wait, element, field_name, value)
        elif "checkbox" in selector.lower() or field_name == "Type":
            fill_checkbox(driver, element, field_name)
        elif "radio" in selector.lower():
            fill_radio(driver, element, field_name, value)
        else:
            fill_text(element, field_name, value)

    except Exception:
        print(f"   ❌ Could not fill {field_name}: {value}")
        driver.save_screenshot("results/jobroom_fill_field_error.png")
        traceback.print_exc()


def main():
    """Main entry point for the autofill script."""
    notion = NotionHelper(NOTION_API_KEY)

    now = datetime.now(timezone.utc)
    start_of_month = datetime(now.year, now.month, 1).strftime("%Y-%m-%d")
    if now.month == 12:
        end_of_month = datetime(now.year + 1, 1, 1).strftime("%Y-%m-%d")
    else:
        end_of_month = datetime(now.year, now.month + 1, 1).strftime("%Y-%m-%d")

    # Filter only records with "Applied date" in current month and "Tracked" = false
    month_filter = {
        "and": [
            {"property": "Applied date", "date": {"on_or_after": start_of_month}},
            {"property": "Applied date", "date": {"before": end_of_month}},
            {"property": "Tracked", "checkbox": {"equals": False}},
        ]
    }
    df = notion.get_database_data(DATABASE_ID, filter=month_filter)

    if df.empty:
        print("No new records to process for this month. Exiting.")
        return

    if "Date" in df.columns:
        df["Date"] = df["Date"].apply(extract_formatted_field)
    if "Type" in df.columns:
        df["Type"] = df["Type"].apply(extract_formatted_field)

    df["PLZ_Ort"] = (
        df["PLZ_Ort"].astype(str).str[:4]
    )  # Only take PLZ from Notion, the Ort is lookedup via typeahead on the website
    df["RAV"] = "false"
    df["Arbeitspensum"] = "false"
    df["Status"] = "false"

    for column in df.columns:
        print(f"{column}: {df[column].iloc[0]}")

    print(f"✅ Loaded {len(df)} records from Notion")
    options = Options()
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    wait = WebDriverWait(driver, 20)

    try:
        print("🌐 Opening Job-Room...")
        driver.get(WEBSITE_URL)

        # click Login button
        driver.find_element(
            By.CSS_SELECTOR, ".btn.btn-primary.d-none.d-lg-block.ng-star-inserted"
        ).click()
        time.sleep(3)

        # Click AGOV button
        driver.find_element(
            By.CSS_SELECTOR, "button[class*='idp-card small xtb-default']"
        ).click()
        time.sleep(3)

        print("Please login manually...")
        input("Press Enter AFTER successful login...")
        print("\n🚀 Starting automation...")

        # Click "Efforts to find work"
        driver.find_element(
            By.XPATH,
            (
                "(//span[@class='nav-text ng-star-inserted']"
                "[normalize-space()='Efforts to find work'])[1]"
            ),
        ).click()
        time.sleep(3)

        # Loop through Notion records and fill the form
        for index, row in df.iterrows():
            print(f"\nProcessing {index + 1}/{len(df)}: {row.get('Role', 'N/A')}")

            # Click "Enter" button to go to form
            driver.find_element(
                By.CSS_SELECTOR,
                ".add-work-effort-button.btn.btn-primary.btn-block.btn-truncate",
            ).click()
            time.sleep(3)

            # Fill each field based on the mapping
            for field, selector in FIELD_SELECTORS.items():
                value = row.get(field)
                fill_field(driver, wait, field, selector, value, row=row)

            # Final review before submission
            input("\nPress Enter to submit the form after reviewing the filled data...")

            success = notion.update_row(
                page_id=row["id"],
                properties={
                    "Tracked": {"checkbox": True},
                },
            )
            if success:
                print("   → Record processed")
            else:
                print(
                    "   → Failed to update Notion record. Please check Notion database."
                )
    except Exception:
        print("❌ Error:")
        driver.save_screenshot("results/jobroom_main_error.png")
        traceback.print_exc()
    finally:
        input("\nPress Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    main()
