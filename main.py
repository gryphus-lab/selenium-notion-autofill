#!/usr/bin/env python3
"""Notion → Selenium Autofill Script"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
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


def main():
    # Load Notion data
    notion = NotionHelper(NOTION_API_KEY)
    df = notion.get_database_data(DATABASE_ID)

    df["Date"] = df["Date"].apply(extract_formatted_date)

    df = df.head(1)  # For testing - remove this line to process all records

    for column in df.columns:
        print(f"{column}: {df[column].iloc[0]}")

    print(f"✅ Loaded {len(df)} records from Notion")

    # Chrome setup
    options = Options()
    options.add_argument("--start-maximized")
    # options.add_argument("--headless=new")  # Uncomment later

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )

    try:
        print("🌐 Opening Job-Room...")

        # Try loading saved session
        if load_cookies(driver):
            driver.get(WEBSITE_URL)
            time.sleep(4)
            print("✅ Session restored!")
        else:
            driver.get(WEBSITE_URL)
            print("\n⚠️ No saved session found.")
            print("Please login manually using AGOV now.")
            input("Press Enter AFTER you have successfully logged in...")

            # Save cookies after successful login
            save_cookies(driver)
            print("✅ Login session saved for future use!")

        # Now we are logged in - ready to automate
        print("\n🚀 Starting automation...")

        for index, row in df.iterrows():
            print(
                f"\nProcessing {index + 1}/{len(df)}: '{row.get('Role', 'No Role')}' at '{row.get('Company', 'No Company')}' on '{row.get('Date', 'No Date')}'"
            )

            driver.get(WEBSITE_URL + "/create")  # Navigate to the form page
            time.sleep(3)

            # Fill in the form fields based on FIELD_SELECTORS
            for field, selector in FIELD_SELECTORS.items():
                value = row.get(field, "")
                if value:
                    try:
                        driver.find_element(By.CSS_SELECTOR, selector).send_keys(
                            str(value)
                        )
                        print(f"   → Filled {field} with '{value}'")
                    except Exception as e:
                        print(f"   ❌ Could not fill {field}: {e}")

            print("   → Record processed")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        input("\nPress Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    main()
