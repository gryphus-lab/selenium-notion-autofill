# Notion Selenium Autofill

Automates web form filling by reading records from a Notion database and using Selenium to populate a browser form.

## Features

- Queries Notion for records using the Notion REST API via `httpx`
- Converts Notion properties into a pandas `DataFrame`
- Opens Chrome with Selenium and `webdriver-manager`
- Fills text inputs, typeahead fields, checkboxes, and radio buttons
- Handles interview records by checking `Vorstellungsgespräch` only when Notion marks the row as an interview
- Marks processed Notion records as tracked by updating the `Tracked` checkbox

## Overview

- Filters Notion records for the current month where `Applied date` is within the month and `Tracked` is `false`
- Processes all matching records from Notion
- Requires a manual login step before automation continues
- Waits for user confirmation before form submission and before closing the browser

## Requirements

- Python 3.12+
- `uv` package manager (configured in `mise.toml`)
- Chrome browser installed
- `webdriver-manager` for automatic ChromeDriver management

## Installation

1. Sync dependencies using `uv`:

   ```bash
   uv sync
   ```

2. Copy the example environment file and fill in your local values:

   ```bash
   cp .env.example .env
   ```

3. Configure your credentials and target website in `.env`:
   - Set `NOTION_API_KEY`
   - Set `DATABASE_ID`
   - Set `WEBSITE_URL`

4. Update `FIELD_SELECTORS` in `src/selenium_notion_autofill/config.py` if the target form changes.

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
│       ├── selenium_helper.py   # Selenium form filling helpers
│       └── session_helper.py    # Selenium session management
├── tests/                       # Unit tests
│   ├── test_config.py
│   ├── test_notion_helper.py
│   ├── test_selenium_helper.py
│   └── test_session_helper.py
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
uv run pytest
```

Pytest writes terminal and HTML coverage reports, plus `coverage.xml` for SonarQube.

### Code quality

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check . --fix
```

## Configuration

Create a local `.env` file:

```bash
cp .env.example .env
```

Then set:

- `NOTION_API_KEY` — your Notion integration token
- `DATABASE_ID` — the Notion database ID to query
- `WEBSITE_URL` — the target website URL

Edit `src/selenium_notion_autofill/config.py` only when the target form selectors change:

- `FIELD_SELECTORS` — mapping of Notion columns to CSS selectors for the web form

### Important

- `Type` and `Interview` are handled specially in `utils/selenium_helper.py` using selector/value resolvers.
- `PLZ_Ort` is trimmed to the first 4 characters before being entered in the typeahead field.
- The script depends on the current target site's form structure and may require selector updates.

## CI and SonarQube

GitHub Actions runs `mise run install`, `mise run test`, and then the SonarQube scan. The test step generates `coverage.xml`, which is read by Sonar through `sonar.python.coverage.reportPaths`.

The SonarQube scan requires `SONAR_TOKEN` to be configured as a GitHub Actions secret.

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
