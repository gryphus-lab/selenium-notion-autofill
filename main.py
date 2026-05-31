#!/usr/bin/env python3
"""Notion → Selenium Autofill Script"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import ast

from config import FIELD_SELECTORS, NOTION_API_KEY, DATABASE_ID, WEBSITE_URL
from utils.notion_helper import NotionHelper
from utils.session_helper import load_cookies, save_cookies


def extract_formatted_date(val):
    try:
        return ast.literal_eval(str(val)).get("string")
    except (ValueError, SyntaxError, TypeError):
        return val


def fill_field(driver, wait, field_name, selector, value):
    """Smart field filler that handles text, checkbox, and radio"""
    try:
        element = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )

        if not value or str(value).strip() == "":
            print(f"   ⏭️ Skipped {field_name} (empty)")
            return

        # Handle different field types
        if "checkbox" in selector or "radio" in selector:
            if isinstance(value, bool) or str(value).lower() in ["false", "0", "no"]:
                if not element.is_selected():
                    driver.execute_script("arguments[0].click();", element)
                print(f"   ✓ Checked {field_name}")
            else:
                print(f"   ⏭️ Skipped {field_name}")

        else:
            # Text input / date / URL fields
            driver.execute_script("arguments[0].scrollIntoView();", element)
            element.clear()
            element.send_keys(str(value))
            print(f"   ✓ Filled {field_name} → {value}")

    except Exception as e:
        print(f"   ❌ Could not fill {field_name}: {e}")


def main():
    # Load Notion data
    notion = NotionHelper(NOTION_API_KEY)
    df = notion.get_database_data(DATABASE_ID)

    # Process Date column if needed
    if "Date" in df.columns:
        df["Date"] = df["Date"].apply(extract_formatted_date)

    df["RAV"] = "false"
    df["Arbeitspensum"] = "false"
    df["Status"] = "false"
    
    df = df.head(1)  # Remove this line when ready for all records

    for column in df.columns:
        print(f"{column}: {df[column].iloc[0]}")
    
    print(f"✅ Loaded {len(df)} records from Notion")

    # Chrome setup
    options = Options()
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    wait = WebDriverWait(driver, 15)

    try:
        print("🌐 Opening Job-Room...")

        if load_cookies(driver):
            driver.get(WEBSITE_URL)
            time.sleep(4)
            print("✅ Session restored!")
        else:
            driver.get(WEBSITE_URL)
            print("\n⚠️ No saved session found. Please login manually.")
            input("Press Enter AFTER successful AGOV login...")
            save_cookies(driver)
            print("✅ Session saved!")

        print("\n🚀 Starting automation...")

        for index, row in df.iterrows():
            print(f"\nProcessing {index + 1}/{len(df)}: {row.get('Role', 'N/A')}")

            driver.get(WEBSITE_URL + "/create")
            time.sleep(4)  # Increased wait for form load

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