NOTION_API_KEY = (
    "***REMOVED_NOTION_API_KEY***"  # From Notion Integrations
)
DATABASE_ID = "962d7936a028461f8abc397b9a3d2e2e"

# Website selectors (update these!)
WEBSITE_URL = "https://www.job-room.ch/work-efforts"

FIELD_SELECTORS = {
    "Date": "input[id*='date']",
    "Type": "dummy",  # This will be overridden in code
    "Company": "input[id*='company.name']",
    "PLZ": "input[id*='single-typeahead-']",
    "Role": "input[id*='job-title']",
    "URL": "input[id*='online-form-url']",
    "RAV": "label[for*='radio-button-'][for$='false']",
    "Arbeitspensum": "label[for*='radio-button-'][for$='FULLTIME']",
    "Status": "label[for*='radio-button-'][for$='PENDING']",
}
