# API Documentation

## NotionHelper

Helper class for interacting with Notion API.

### Usage

```python
from selenium_notion_autofill.utils import load_cookies, save_cookies
from selenium import webdriver

driver = webdriver.Chrome()

# Save cookies after login
save_cookies(driver)

# Load cookies in a new session
load_cookies(driver)
```

### Methods

#### `__init__(api_key: str)`

Initialize the helper with Notion API key.

**Parameters:**

- `api_key` (str): Notion Integration API key

#### `get_database_data(database_id: str, filter: Optional[Dict] = None) -> pd.DataFrame`

Fetch all rows from a Notion database.

**Parameters:**

- `database_id` (str): The ID of the Notion database
- `filter` (dict, optional): Filter to apply to the query

**Returns:**

- `pd.DataFrame`: DataFrame containing database records

**Raises:**

- `httpx.HTTPStatusError`: If the API request fails

#### `update_row(page_id: str, properties: Dict[str, Any]) -> bool`

Update a Notion page with new properties.

**Parameters:**

- `page_id` (str): The ID of the Notion page
- `properties` (dict): Dictionary of properties to update

**Returns:**

- `bool`: True if successful, False otherwise

## Session Helper

Helper functions for managing Selenium WebDriver sessions.

### Functions

#### `save_cookies(driver)`

Save cookies from the current driver session to a JSON file.

**Parameters:**

- `driver`: Selenium WebDriver instance

#### `load_cookies(driver) -> bool`

Load cookies from a JSON file into the driver session.

**Parameters:**

- `driver`: Selenium WebDriver instance

**Returns:**

- `bool`: True if cookies were loaded, False otherwise
