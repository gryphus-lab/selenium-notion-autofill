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


def _open_base_domain(driver):
    driver.get("https://www.job-room.ch")
    time.sleep(3)


def _load_cookies():
    with open(COOKIES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _apply_cookies(driver, cookies):
    for cookie in cookies:
        if "sameSite" in cookie:
            cookie.pop("sameSite")
        try:
            driver.add_cookie(cookie)
        except Exception:
            continue


def _restore_storage(driver):
    if not os.path.exists(STORAGE_FILE):
        return

    with open(STORAGE_FILE, "r", encoding="utf-8") as f:
        storage = json.load(f)

    local = storage.get("localStorage") or {}
    for key, value in local.items():
        driver.execute_script(
            "window.localStorage.setItem(arguments[0], arguments[1]);",
            key,
            value,
        )

    session = storage.get("sessionStorage") or {}
    for key, value in session.items():
        driver.execute_script(
            "window.sessionStorage.setItem(arguments[0], arguments[1]);",
            key,
            value,
        )


def load_session(driver):
    """Load cookies and storage - more robust approach"""
    if not os.path.exists(COOKIES_FILE):
        return False

    try:
        _open_base_domain(driver)
        cookies = _load_cookies()
        _apply_cookies(driver, cookies)

        driver.refresh()
        time.sleep(4)

        _restore_storage(driver)

        print("   ✅ Session restored (cookies + storage)")
        return True

    except Exception as e:
        print(f"   ⚠️ Failed to restore session: {e}")
        return False
