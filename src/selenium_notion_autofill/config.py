"""Configuration for Notion-Selenium Autofill."""

import json
import os

from dotenv import load_dotenv

# Load user/instance-specific secrets from a local .env file (see .env.example).
load_dotenv()


def _required_setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required configuration: {name}")
    return value


def validate_property_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise ValueError("must be a JSON object with string keys and values")
    return value


# From Notion Integrations — set these in your .env file, never commit them.
NOTION_API_KEY = _required_setting("NOTION_API_KEY")
DATABASE_ID = _required_setting("DATABASE_ID")

APPLIED_DATE = "Applied date"
EXIT_MESSAGE = "     Exiting...\n"
SCROLL_INTO_VIEW_SCRIPT = "arguments[0].scrollIntoView({block: 'center'});"

FIELD_SELECTORS = {
    "Date": "input[id*='date']",
    "Type": "dummy",  # This will be overridden in code
    "Company": "input[id*='company.name']",
    "Street": "input[id*='company.street']",
    "Number": "input[id*='company.house-number']",
    "POBox": "input[id*='company.postbox-number']",
    "PLZ_Ort": "input[id*='single-typeahead-']",
    "Contact": "input[id*='contact-person']",
    "Email": "input[id*='contact.email']",
    "Phone": "input[id*='global.phone']",
    "Role": "input[id*='job-title']",
    "URL": "input[id*='online-form-url']",
    "RAV": "label[for*='radio-button-'][for$='false']",
    "Arbeitspensum": "label[for*='radio-button-'][for$='FULLTIME']",
    "Interview": "dummy",
    "Status": "label[for*='radio-button-'][for$='PENDING']",
}

COOKIES_FILE = "cookies/jobroom_cookies.json"

EXECUTE_SCRIPT_CLICK = "arguments[0].click();"

# Selectors for updating an existing entry's status to "Absage"
REJECTION_SELECTORS = {
    "status_radio_absage": "label[for*='radio-button-'][for$='REJECTED']",
    "absagegrund_input": "textarea[id*='rejection-reason']",
}

ENTRY_SELECTOR = "alv-work-effort"

# Optional: supply a JSON mapping (string) via env var NOTION_PROPERTY_MAP_JSON
# mapping canonical keys (Company, Role, URL, Applied date, Description, Tracked)
# to your database property names. Example:
# NOTION_PROPERTY_MAP_JSON='{"Company": "Firma", "Role": "Stelle"}'
NOTION_PROPERTY_MAP_JSON = os.environ.get("NOTION_PROPERTY_MAP_JSON", "")
NOTION_PROPERTY_MAP = None
if NOTION_PROPERTY_MAP_JSON:
    try:
        parsed_property_map = json.loads(NOTION_PROPERTY_MAP_JSON)
        NOTION_PROPERTY_MAP = validate_property_map(parsed_property_map)
    except ValueError as exc:
        raise RuntimeError(
            "Invalid NOTION_PROPERTY_MAP_JSON: expected a JSON object "
            "with string keys and values"
        ) from exc


def get_website_url() -> str:
    return _required_setting("WEBSITE_URL")
