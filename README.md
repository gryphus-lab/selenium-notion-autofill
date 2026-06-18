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
- `uv` package manager (configured in `mise.toml`)
- Chrome browser installed
- `webdriver-manager` for automatic ChromeDriver management

## Installation

1. Sync dependencies using `uv`:

    ```bash
    uv sync
    ```

2. Configure your credentials in `src/selenium_notion_autofill/config.py`:
   - Set `NOTION_API_KEY`
   - Set `DATABASE_ID`
   - Update `WEBSITE_URL` and `FIELD_SELECTORS` as needed

## Project Structure

```text
selenium-notion-autofill/
├── src/selenium_notion_autofill/
│   ├── __init__.py              # Package initialization
│   ├── __main__.py              # Main entry point
│   ├── config.py                # Configuration variables
│   └── utils/
│       ├── __init__.py
│       ├── notion_helper.py     # Notion API client
│       └── session_helper.py    # Selenium session management
├── tests/                       # Unit tests
│   ├── test_config.py
│   └── test_notion_helper.py
├── docs/                        # Documentation
├── pyproject.toml              # Project configuration
├── mise.toml                   # Mise/task configuration
└── README.md
```

## Usage

### Run with uv

```bash
# Run the main script
uv run -m selenium_notion_autofill

# Or using mise
mise run main
```

### Run tests

```bash
uv run pytest tests/ -v
```

### Code quality

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check . --fix
```

## Configuration

Edit `src/selenium_notion_autofill/config.py`:

```bash
uv sync
source .venv/bin/activate
```

Install dependencies:

```bash
uv sync
```

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

## Execution

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
