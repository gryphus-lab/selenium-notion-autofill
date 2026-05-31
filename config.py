NOTION_API_KEY = (
    "***REMOVED_NOTION_API_KEY***"  # From Notion Integrations
)
DATABASE_ID = "962d7936a028461f8abc397b9a3d2e2e"

# Website selectors (update these!)
WEBSITE_URL = "https://www.job-room.ch/work-efforts"
FIELD_SELECTORS = {
    "Date": "input[id*='date']",
    "Company": "input[id*='company.name']",
    "Role": "input[id*='job-title']",
    "URL": "input[id*='online-form-url']",
    "Type": "label[for='alv-checkbox-portal.work-efforts.edit-form.apply-channel.electronic-0']", "label[for='alv-checkbox-portal.work-efforts.edit-form.apply-channel.phone-0']"
    "RAV": "label[for='alv-radio-button-0-false']",
    "Arbeitspensum": "label[for='alv-radio-button-1-FULLTIME']",
    "Status": "label[for='alv-radio-button-2-PENDING']",
    "PLZ": "input[id='alv-single-typeahead-plz-/-ort-0']",
    # Add more as needed
}
