import json
import os
import time
from datetime import date, datetime
from pathlib import Path

COOKIES_FILE = "cookies/jobroom_cookies.json"
STORAGE_FILE = "cookies/jobroom_storage.json"
SESSION_INFO_FILE = "cookies/session_info.json"


def _is_session_from_today() -> bool:
    """Check if the saved session is from today"""
    if not os.path.exists(SESSION_INFO_FILE):
        return False
    try:
        with open(SESSION_INFO_FILE, "r", encoding="utf-8") as f:
            info = json.load(f)
        saved_date = datetime.fromisoformat(info.get("date")).date()
        return saved_date == date.today()
    except Exception:
        return False


def _delete_old_session():
    """Delete old session files from previous days"""
    for file_path in [COOKIES_FILE, STORAGE_FILE, SESSION_INFO_FILE]:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"   🗑️ Deleted old session file: {file_path}")
            except Exception as e:
                print(f"   ⚠️ Could not delete {file_path}: {e}")


def save_session(driver):
    """Save both cookies and localStorage/sessionStorage + mark as today's session"""
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

    # Save session metadata for daily control
    session_info = {
        "date": datetime.now().isoformat(),
        "last_login": datetime.now().isoformat(),
    }
    with open(SESSION_INFO_FILE, "w", encoding="utf-8") as f:
        json.dump(session_info, f, indent=2)

    print("   ✅ Full session saved for today")


def load_session(driver):
    """Load session only if saved today. Otherwise delete old files and return False."""
    if not os.path.exists(COOKIES_FILE):
        _delete_old_session()
        return False

    if os.path.exists(SESSION_INFO_FILE) and not _is_session_from_today():
        _delete_old_session()
        return False

    try:
        _open_base_domain(driver)
        cookies = _load_cookies()
        _apply_cookies(driver, cookies)

        driver.refresh()
        time.sleep(4)

        _restore_storage(driver)

        print("   ✅ Today's session restored successfully")
        return True

    except Exception as e:
        print(f"   ⚠️ Failed to restore session: {e}")
        return False


# Private helper functions (kept from your refactored version)
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
