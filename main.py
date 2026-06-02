#!/usr/bin/env python3
"""Notion → Selenium Autofill Script"""


from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import time
import ast
import traceback

from config import FIELD_SELECTORS, NOTION_API_KEY, DATABASE_ID, WEBSITE_URL
from utils.notion_helper import NotionHelper
from datetime import datetime, timezone

# Constants
EXECUTE_SCRIPT_CLICK = "arguments[0].click();"


def extract_formatted_field(val):
    try:
        return ast.literal_eval(str(val)).get("string")
    except (ValueError, SyntaxError, TypeError):
        return val


def resolve_type_selector(value):
    """Resolve selector for Type field based on value"""
    type_value = str(value).strip().lower()

    if type_value == "electronic":
        return "label[for='alv-checkbox-portal.work-efforts.edit-form.apply-channel.electronic-0']"
    elif type_value == "phone":
        return "label[for='alv-checkbox-portal.work-efforts.edit-form.apply-channel.phone-0']"
    else:
        print(f"   ⚠️ Unknown Type: {type_value}")
        return None


def fill_typeahead(driver, wait, element, field_name, value):
    """Fill typeahead field"""
    if element.is_displayed():
        driver.execute_script(EXECUTE_SCRIPT_CLICK, element)

    element.send_keys(str(value))
    time.sleep(2)
    try:
        suggestion = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[id*='ngb-typeahead-']")
            )
        )

        suggestion.click()
        final_value = element.get_attribute("value")
        print(
            f"   ✓ Typeahead: {field_name} → Clicked suggestion - Selected value: {final_value}"
        )
    except Exception:
        element.send_keys(Keys.ENTER)
        final_value = element.get_attribute("value")
        print(
            f"   ✓ Typeahead (Enter): {field_name} - tried pressing Enter without waiting for dropdown → Selected value: {final_value}"
        )


def fill_checkbox(driver, element, field_name):
    """Fill checkbox field"""
    if element.is_displayed():
        driver.execute_script(EXECUTE_SCRIPT_CLICK, element)
        print(f"   ✓ Checked {field_name}")
    else:
        print(f"   ⚠️ Checkbox not visible: {field_name}")


def fill_radio(driver, element, field_name, value):
    """Fill radio field"""
    if value:
        driver.execute_script(EXECUTE_SCRIPT_CLICK, element)
        print(f"   ✓ Selected radio {field_name}")


def fill_text(element, field_name, value):
    """Fill text input field"""
    element.clear()
    element.send_keys(str(value))
    print(f"   ✓ Filled {field_name} → {value}")


def fill_field(driver, wait, field_name, selector, value, row=None):
    """Smart filler with special handling for Type checkboxes"""
    try:
        if field_name == "Type" and row is not None:
            selector = resolve_type_selector(value)
            if selector is None:
                return
            print(f"   → Setting Type to: {str(value).strip().lower()}")

        element = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
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
    notion = NotionHelper(NOTION_API_KEY)

    now = datetime.now(timezone.utc)
    start_of_month = datetime(now.year, now.month, 1).strftime("%Y-%m-%d")
    if now.month == 12:
        end_of_month = datetime(now.year + 1, 1, 1).strftime("%Y-%m-%d")
    else:
        end_of_month = datetime(now.year, now.month + 1, 1).strftime("%Y-%m-%d")

    # 3. Construct the filter payload
    # (Change "Date" to match your exact Notion property column name)
    month_filter = {
        "and": [
            {"property": "Applied date", "date": {"on_or_after": start_of_month}},
            {"property": "Applied date", "date": {"before": end_of_month}},
        ]
    }
    df = notion.get_database_data(DATABASE_ID, filter=month_filter)

    if "Date" in df.columns:
        df["Date"] = df["Date"].apply(extract_formatted_field)
    if "Type" in df.columns:
        df["Type"] = df["Type"].apply(extract_formatted_field)

    df["RAV"] = "false"
    df["Arbeitspensum"] = "false"
    df["Status"] = "false"
    df["PLZ"] = (
        "8001"  # Temporary hardcoded value for testing, replace with actual data from Notion if needed
    )

    df = df.head(1)  # Takes most recent entry only, remove this line later

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
        time.sleep(1)

        # Click AGOV button
        driver.find_element(
            By.CSS_SELECTOR, "button[class*='idp-card small xtb-default']"
        ).click()
        time.sleep(1)

        print("Please login manually...")

        input("Press Enter AFTER successful login...")

        print("\n🚀 Starting automation...")

        for index, row in df.iterrows():
            print(f"\nProcessing {index + 1}/{len(df)}: {row.get('Role', 'N/A')}")

            driver.get(WEBSITE_URL + "/create")
            time.sleep(5)

            for field, selector in FIELD_SELECTORS.items():
                value = row.get(field)
                fill_field(driver, wait, field, selector, value, row=row)

            input("\nPress Enter to submit the form after reviewing the filled data...")
            print("   → Record processed")

    except Exception:
        print("❌ Error:")
        driver.save_screenshot("results/jobroom_main_error.png")
        traceback.print_exc()
    finally:
        input("\nPress Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    main()
