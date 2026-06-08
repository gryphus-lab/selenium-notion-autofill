import json
import os
import time
from pathlib import Path

COOKIES_FILE = "cookies/jobroom_cookies.json"
STORAGE_FILE = "cookies/jobroom_storage.json"


def save_session(driver):
    """Save both cookies and localStorage/sessionStorage"""
    Path("cookies").mkdir(exist_ok=True)

    # Save cookies
    cookies = driver.get_cookies()
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2, ensure_ascii=False)

    # Save localStorage and sessionStorage
    storage = {}
    try:
        storage["localStorage"] = driver.execute_script(
            "return Object.assign({}, window.localStorage);"
        )
        storage["sessionStorage"] = driver.execute_script(
            "return Object.assign({}, window.sessionStorage);"
        )
    except Exception as e:
        print(f"   ⚠️ Could not save storage: {e}")

    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(storage, f, indent=2, ensure_ascii=False)

    print("   ✅ Full session saved (cookies + storage)")


def load_session(driver):
    """Load cookies and storage - more robust approach"""
    if not os.path.exists(COOKIES_FILE):
        return False

    try:
        # 1. Go to base domain first
        driver.get("https://www.job-room.ch")
        time.sleep(3)

        # 2. Load cookies
        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            cookies = json.load(f)

        for cookie in cookies:
            try:
                # Remove domain-specific fields that often cause issues
                if "sameSite" in cookie:
                    cookie.pop("sameSite")
                driver.add_cookie(cookie)
            except Exception:
                pass

        # 3. Refresh to apply cookies
        driver.refresh()
        time.sleep(4)

        # 4. Restore localStorage + sessionStorage
        if os.path.exists(STORAGE_FILE):
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                storage = json.load(f)

            if storage.get("localStorage"):
                for key, value in storage["localStorage"].items():
                    driver.execute_script(
                        f"window.localStorage.setItem('{key}', '{value}');"
                    )

            if storage.get("sessionStorage"):
                for key, value in storage["sessionStorage"].items():
                    driver.execute_script(
                        f"window.sessionStorage.setItem('{key}', '{value}');"
                    )

        print("   ✅ Session restored (cookies + storage)")
        return True

    except Exception as e:
        print(f"   ⚠️ Failed to restore session: {e}")
        return False
