"""Helper class for interacting with Notion API."""

import httpx
import pandas as pd
from typing import Optional, Dict, List, Any


class NotionHelper:
    """Helper class to interact with Notion database via API."""

    def __init__(self, api_key: str):
        """Initialize NotionHelper with API key.
        
        Args:
            api_key: Notion API key for authentication
        """
        self.api_key = api_key
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

    def get_database_data(
        self, database_id: str, filter: Optional[Dict] = None
    ) -> pd.DataFrame:
        """Fetch all rows from Notion database.
        
        Args:
            database_id: The ID of the Notion database
            filter: Optional filter to apply to the query
            
        Returns:
            pd.DataFrame: DataFrame containing the database records
            
        Raises:
            httpx.HTTPStatusError: If the API request fails
        """
        url = f"{self.base_url}/databases/{database_id}/query"
        results: List[Dict] = []
        has_more = True
        start_cursor = None

        while has_more:
            payload: Dict[str, Any] = {"page_size": 100}
            if filter:
                payload["filter"] = filter
            if start_cursor:
                payload["start_cursor"] = start_cursor

            response = httpx.post(url, headers=self.headers, json=payload, timeout=30)

            if response.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"Notion API error {response.status_code}: {response.text}",
                    request=response.request,
                    response=response,
                )

            data = response.json()
            results.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        # Convert to DataFrame
        data_rows = []
        for page in results:
            props = page.get("properties", {})
            row = {"id": page.get("id")}

            for prop_name, prop in props.items():
                row[prop_name] = self._get_property_value(prop)

            data_rows.append(row)

        return pd.DataFrame(data_rows)

    def update_row(self, page_id: str, properties: Dict[str, Any]) -> bool:
        """Update a Notion page with new properties.
        
        Args:
            page_id: The ID of the Notion page to update
            properties: Dictionary of properties to update
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        url = f"{self.base_url}/pages/{page_id}"

        payload = {"properties": properties}

        try:
            response = httpx.patch(url, headers=self.headers, json=payload, timeout=20)

            if response.status_code == 200:
                print(f"   ✅ Notion row updated successfully (ID: {page_id[:8]}...)")
                return True
            else:
                print(
                    f"   ❌ Failed to update Notion row: {response.status_code} - {response.text}"
                )
                return False

        except Exception as e:
            print(f"   ❌ Exception while updating Notion row: {e}")
            return False

    def _get_property_value(self, prop: Any) -> Any:
        """Extract the value from a Notion property object.
        
        Args:
            prop: The Notion property object
            
        Returns:
            The extracted value in the appropriate Python type
        """
        if not prop or not isinstance(prop, dict):
            return None

        def _plain_text_list(values: List[Dict[str, Any]]) -> str:
            return " ".join([t.get("plain_text", "") for t in values]).strip()

        type_handlers = {
            "title": lambda p: _plain_text_list(p.get("title", [])),
            "rich_text": lambda p: _plain_text_list(p.get("rich_text", [])),
            "email": lambda p: p.get("email") or "",
            "phone_number": lambda p: p.get("phone_number") or "",
            "url": lambda p: p.get("url") or "",
            "select": lambda p: (p.get("select") or {}).get("name", ""),
            "multi_select": lambda p: [
                item.get("name") for item in p.get("multi_select", [])
            ],
            "checkbox": lambda p: p.get("checkbox", False),
            "number": lambda p: p.get("number"),
            "date": lambda p: (p.get("date") or {}).get("start", ""),
        }

        prop_type = prop.get("type")
        handler = type_handlers.get(prop_type)
        if handler:
            return handler(prop)

        return str(prop.get(prop_type, ""))
