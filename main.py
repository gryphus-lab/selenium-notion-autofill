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

from config import FIELD_SELECTORS, NOTION_API_KEY, DATABASE_ID, WEBSITE_URL
from utils.notion_helper import NotionHelper
from utils.session_helper import load_cookies, save_cookies


def extract_formatted_field(val):
    try:
        return ast.literal_eval(str(val)).get("string")
    except (ValueError, SyntaxError, TypeError):
        return val


def fill_field(driver, wait, field_name, selector, value):
    """Enhanced field filler with support for typeahead"""
    try:
        element = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", element
        )
        time.sleep(0.5)

        if not value or str(value).strip() == "":
            print(f"   ⏭️ Skipped {field_name} (empty)")
            return

        # === TYPEAHEAD / AUTOCOMPLETE ===
        if "single-typeahead" in selector or "typeahead" in selector.lower():
            element.clear()
            element.click()
            time.sleep(1)
            element.send_keys(str(value))
            time.sleep(2)  # Wait for dropdown to appear

            # Try to select first suggestion
            try:
                suggestion = wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.CSS_SELECTOR,
                            "div[role='option'], li[role='option'], .suggestion, .dropdown-item",
                        )
                    )
                )
                suggestion.click()
                print(f"   ✓ Typeahead selected for {field_name}: {value}")
            except Exception:
                # Fallback: Press Enter
                element.send_keys(Keys.ENTER)
                print(f"   ✓ Typeahead entered (Enter) for {field_name}: {value}")

        # === CHECKBOX ===
        elif "checkbox" in selector.lower():
            if str(value).lower() in ["electronic", "phone"]:
                if element.is_selected():
                    driver.execute_script("arguments[0].click();", element)
                print(f"   ✓ Checked {field_name}")
            else:
                print(f"   ⏭️ Skipped checkbox {field_name}")

        # === RADIO ===
        elif "radio" in selector.lower():
            if value:
                driver.execute_script("arguments[0].click();", element)
                print(f"   ✓ Selected radio {field_name}")

        # === DEFAULT TEXT INPUT ===
        else:
            element.clear()
            element.send_keys(str(value))
            print(f"   ✓ Filled {field_name} → {value}")

    except Exception as e:
        print(f"   ❌ Could not fill {field_name}: {e}")


def main():
    # Load Notion data
    notion = NotionHelper(NOTION_API_KEY)
    df = notion.get_database_data(DATABASE_ID)

    if "Date" in df.columns:
        df["Date"] = df["Date"].apply(extract_formatted_field)
    if "Type" in df.columns:
        df["Type"] = df["Type"].apply(extract_formatted_field)

    df["RAV"] = "false"
    df["Arbeitspensum"] = "false"
    df["Status"] = "false"
    df["PLZ"] = "8001"

    df = df.head(1)  # Remove this when ready for full run

    for column in df.columns:
        print(f"{column}: {df[column].iloc[0]}")

    print(f"✅ Loaded {len(df)} records from Notion")

    # Browser setup
    options = Options()
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    wait = WebDriverWait(driver, 20)

    try:
        print("🌐 Opening Job-Room...")

        if load_cookies(driver):
            driver.get(WEBSITE_URL)
            time.sleep(4)
            print("✅ Session restored!")
        else:
            driver.get(WEBSITE_URL)
            print("Please login manually with AGOV...")
            input("Press Enter AFTER login...")
            save_cookies(driver)

        print("\n🚀 Starting automation...")

        for index, row in df.iterrows():
            print(f"\nProcessing {index + 1}/{len(df)}: {row.get('Role', 'N/A')}")

            driver.get(WEBSITE_URL + "/create")
            time.sleep(5)  # Important: wait for form to fully load

            for field, selector in FIELD_SELECTORS.items():
                value = row.get(field)
                fill_field(driver, wait, field, selector, value)

            print("   → Record processed")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        input("\nPress Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    main()
