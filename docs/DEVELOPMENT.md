# Developer Guide

## Setup

### Prerequisites

- Python 3.11 or higher
- pip or uv (package manager)

### Installation

1. Clone the repository

```bash
git clone <repository-url>
cd selenium-notion-autofill
```

1. Create a virtual environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

1. Install in development mode

```bash
pip install -e ".[dev]"
# or with uv:
uv pip install -e ".[dev]"
```

## Project Structure

```text
selenium-notion-autofill/
├── src/
│   └── selenium_notion_autofill/     # Main package
│       ├── __init__.py
│       ├── __main__.py               # Entry point
│       ├── config.py                 # Configuration
│       └── utils/
│           ├── __init__.py
│           ├── notion_helper.py      # Notion API client
│           └── session_helper.py     # Selenium session management
├── tests/                            # Unit tests
│   ├── __init__.py
│   ├── test_config.py
│   └── test_notion_helper.py
├── docs/                             # Documentation
├── pyproject.toml                    # Project metadata and dependencies
├── README.md
└── .gitignore
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src/selenium_notion_autofill

# Run specific test file
pytest tests/test_config.py

# Run tests in verbose mode
pytest -v
```

## Code Quality

### Formatting

```bash
black src tests
```

### Linting

```bash
ruff check src tests
ruff check --fix src tests
```

## Running the Application

### As a module

```bash
python -m selenium_notion_autofill
```

### As a command

```bash
autofill
```

## Configuration

Update `src/selenium_notion_autofill/config.py` with:

- `NOTION_API_KEY`: Your Notion Integration API key
- `DATABASE_ID`: Your Notion database ID
- `WEBSITE_URL`: Target website URL
- `FIELD_SELECTORS`: CSS selectors for form fields

## Development Workflow

1. Create a feature branch
2. Make your changes
3. Run tests and linting
4. Create a pull request

## Common Tasks

### Adding a new dependency

```bash
# Edit pyproject.toml and add to dependencies section
# Then reinstall
pip install -e ".[dev]"
```

### Adding a new test

- Create test file in `tests/` directory
- Name it `test_*.py`
- Run `pytest` to verify

### Adding a new module

- Create module in `src/selenium_notion_autofill/`
- Update `src/selenium_notion_autofill/__init__.py` if needed
- Add tests in `tests/`
