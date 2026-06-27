"""Configuration for Notion-Selenium Autofill."""

import os

from dotenv import load_dotenv

# Load user/instance-specific secrets from a local .env file (see .env.example).
load_dotenv()

# From Notion Integrations — set these in your .env file, never commit them.
NOTION_API_KEY = os.environ["NOTION_API_KEY"]
DATABASE_ID = os.environ["DATABASE_ID"]

# Website selectors
WEBSITE_URL = "https://www.job-room.ch/"

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
    # TODO: "Interview": "dummy",  # This will be overridden in code
    "Status": "label[for*='radio-button-'][for$='PENDING']",
}

COOKIES_FILE = "cookies/jobroom_cookies.json"

EXECUTE_SCRIPT_CLICK = "arguments[0].click();"
