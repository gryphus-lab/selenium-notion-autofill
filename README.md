# Notion Selenium Autofill

Automates web form filling by reading records from a Notion database and using Selenium to populate a browser form.

## Features

- Queries Notion for records using the Notion REST API via `httpx`
- Converts Notion properties into a pandas `DataFrame`
- Opens Chrome with Selenium and `webdriver-manager`
- Fills text inputs, typeahead fields, checkboxes, and radio buttons
- Marks processed Notion records as tracked by updating the `Tracked` checkbox

## Overview

- Filters Notion records for the current month where `Applied date` is within the month and `Tracked` is `false`
- Processes all matching records from Notion
- Requires a manual login step before automation continues
- Waits for user confirmation before form submission and before closing the browser

## Requirements

- Python 3.11+
- `uv` package manager
- Chrome browser installed

## Installation

1. Create or sync the virtual environment:

    ```bash
    uv sync
    source .venv/bin/activate
    ```

2. Install dependencies:

    ```bash
    uv sync
    ```

## Configuration

Edit `config.py` to match your Notion workspace and target form:

- `NOTION_API_KEY` — your Notion integration token
- `DATABASE_ID` — the Notion database ID to query
- `WEBSITE_URL` — the target website URL
- `FIELD_SELECTORS` — mapping of Notion columns to CSS selectors for the web form

### Important

- `Type` is handled specially in `main.py` using a selector resolver.
- `PLZ_Ort` is trimmed to the first 4 characters before being entered in the typeahead field.
- The script depends on the current target site's form structure and may require selector updates.

> Do not commit real API keys or secrets to version control.

## Usage

Run the project with:

```bash
uv run autofill
```

The script will:

1. query Notion for current-month, untracked records
2. open Chrome and navigate to the configured site
3. prompt for manual login
4. process each matching row
5. wait for confirmation before submission
6. update the Notion page's `Tracked` checkbox on success

## Notes

- Error screenshots are saved under `results/jobroom_fill_field_error.png` and `results/jobroom_main_error.png`.
- `utils/notion_helper.py` uses `httpx` directly instead of the official Notion SDK.
- The project includes a development dependency on `ruff`.
