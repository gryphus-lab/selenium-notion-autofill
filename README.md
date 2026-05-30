# Notion Selenium Autofill

Automates web form filling by reading records from a Notion database and using Selenium to populate fields in a browser.

## Features

- Reads a Notion database table into a pandas DataFrame
- Opens a Chrome browser via Selenium
- Uses CSS selectors from `config.py` to fill form fields
- Includes a `project.scripts` entrypoint for `uv run autofill`

## Requirements

- Python 3.11+
- `uv` package manager
- Chrome browser installed

## Setup

1. Create and activate the virtual environment if not already present:

```bash
uv sync
source .venv/bin/activate
```

2. Install dependencies:

```bash
uv sync
```

## Configuration

Edit `config.py` to set your project-specific values:

- `NOTION_API_KEY` — your Notion integration token
- `DATABASE_ID` — the Notion database ID to read
- `WEBSITE_URL` — the URL of the web form to fill
- `FIELD_SELECTORS` — a mapping of Notion fields to CSS selectors

> Tip: Do not commit real API keys or secrets to version control.

## Usage

Run the autofill script with:

```bash
uv run autofill
```

The script will open Chrome, navigate to `WEBSITE_URL`, and fill the configured fields for each record.

## Notes

- The script currently does not submit the form automatically.
- Update the selector values and form submit logic in `main.py` as needed.
- Use the browser output to verify field mapping and values.
