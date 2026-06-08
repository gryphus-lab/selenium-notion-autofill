import time
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as ec

from selenium_notion_autofill.config import (
    EXECUTE_SCRIPT_CLICK,
    FIELD_SELECTORS,
    WEBSITE_URL,
)
from selenium_notion_autofill.utils.session_helper import load_session, save_session


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


def process_records(driver, wait, df, notion):
    """Process each record from the dataframe.

    Args:
        driver: Selenium WebDriver instance
        wait: WebDriverWait instance
        df: Dataframe with records to process
        notion: NotionHelper instance
    """

    # Navigate to "Efforts to find work"
    driver.get(WEBSITE_URL + "work-efforts")
    time.sleep(3)

    for index, row in df.iterrows():
        print(f"\nProcessing {index + 1}/{len(df)}: {row.get('Role', 'N/A')}")

        driver.find_element(
            By.CSS_SELECTOR,
            ".add-work-effort-button",
        ).click()
        time.sleep(3)

        for field, selector in FIELD_SELECTORS.items():
            value = row.get(field)
            fill_field(driver, wait, field, selector, value, row=row)

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
            print("   → Failed to update Notion record. Please check Notion database.")


def handle_login(driver):
    """Handle session restoration or manual login.

    Args:
        driver: Selenium WebDriver instance
        wait: WebDriverWait instance

    Returns:
        Boolean indicating if logged in successfully
    """
    session_restored = load_session(driver)

    if session_restored:
        driver.get(WEBSITE_URL)
        time.sleep(5)
        print("✅ Session restored!")

        current_url = driver.current_url.lower()
        if any(x in current_url for x in ["login", "auth", "saml", "agov"]):
            print(
                "   ⚠️ Session restore did not log in automatically. "
                "Falling back to manual login."
            )
            session_restored = False

    if not session_restored:
        driver.get(WEBSITE_URL)
        print("\n⚠️ No valid session found. Starting manual login...")

        try:
            driver.find_element(
                By.CSS_SELECTOR,
                ".btn.btn-primary.d-none.d-lg-block.ng-star-inserted",
            ).click()
            time.sleep(3)
        except Exception as e:
            print(f"   Could not find Login button - already on login page?: {e}")

        try:
            driver.find_element(
                By.CSS_SELECTOR, "button[class*='idp-card small xtb-default']"
            ).click()
            time.sleep(3)
        except Exception as e:
            print(f"   Could not find AGOV button: {e}")

        input("✅ Press Enter AFTER successful AGOV login and QR code scan...")
        save_session(driver)
        print("✅ Full session (cookies + storage) saved for future use!")

    return True
