"""Helper functions for managing Selenium WebDriver sessions."""

import json
import os
from pathlib import Path

COOKIES_FILE = "cookies/jobroom_cookies.json"


def save_cookies(driver):
    """Save cookies after manual login.
    
    Args:
        driver: Selenium WebDriver instance
    """
    os.makedirs("cookies", exist_ok=True)
    cookies = driver.get_cookies()
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f)
    print(f"✅ Cookies saved to {COOKIES_FILE}")


def load_cookies(driver):
    """Load saved cookies.
    
    Args:
        driver: Selenium WebDriver instance
        
    Returns:
        bool: True if cookies were loaded successfully, False otherwise
    """
    if not os.path.exists(COOKIES_FILE):
        return False

    try:
        with open(COOKIES_FILE, "r") as f:
            cookies = json.load(f)

        # Go to the domain first
        driver.get("https://www.job-room.ch/work-efforts")
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                print(f"⚠️ Failed to add cookie: {e}")
        print("✅ Cookies loaded successfully")
        return True
    except Exception as e:
        print(f"⚠️ Failed to load cookies: {e}")
        return False
