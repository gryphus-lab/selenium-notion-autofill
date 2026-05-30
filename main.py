#!/usr/bin/env python3
"""Notion → Selenium Autofill Script"""

#!/usr/bin/env python3
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import sys
import pandas as pd

from config import NOTION_API_KEY, DATABASE_ID, WEBSITE_URL, FIELD_SELECTORS
from utils.notion_helper import NotionHelper


def fetch_database_data():
    try:
        df = NotionHelper(NOTION_API_KEY).get_database_data(DATABASE_ID)
        print(f"✅ Loaded {len(df)} records from Notion")
        print("\nColumns available:", df.columns.tolist())
        print("\nFirst row preview:")
        print(df.head(1).to_string())
        return df
    except Exception as e:
        print(f"❌ Notion Error: {e}")
        sys.exit(1)


def fill_form_fields(wait, row):
    for field, selector in FIELD_SELECTORS.items():
        try:
            element = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )

            value = row.get(field)
            if pd.notna(value) and str(value).strip() != "":
                if element.tag_name == "select":
                    element.send_keys(str(value))
                else:
                    element.clear()
                    element.send_keys(str(value))
                print(f"   ✓ Filled '{field}' → {value}")
            else:
                print(f"   ⏭️ Skipped '{field}' (empty)")
        except Exception as e:
            print(f"   ⚠️ Failed to fill '{field}': {e}")


def process_records(driver, wait, df):
    for index, row in df.iterrows():
        print(
            f"\n📝 Processing record {index + 1}/{len(df)}: {row.get('Name', 'Unnamed')}"
        )

        driver.get(WEBSITE_URL)
        time.sleep(3)  # Give page time to load fully
        fill_form_fields(wait, row)

        # TODO: Add your Submit button logic here
        # submit_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']")))
        # submit_btn.click()
        # time.sleep(4)

        print(f"   → Record {index + 1} completed")


def main():
    print("🔄 Connecting to Notion...")
    df = fetch_database_data()

    print("\n🌐 Starting browser...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    wait = WebDriverWait(driver, 15)

    try:
        process_records(driver, wait, df)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        input("\nPress Enter to close browser...")  # Keeps browser open for debugging
        driver.quit()


if __name__ == "__main__":
    main()
