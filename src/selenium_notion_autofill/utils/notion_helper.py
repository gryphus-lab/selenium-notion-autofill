"""Helper class for interacting with Notion API."""

from typing import Any, Dict, List, Mapping, Optional

import httpx
import pandas as pd


def build_notion_properties(
    properties: Dict[str, Any],
    prop_name_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Convert simple scalar properties to Notion API property objects."""
    notion_props: Dict[str, Any] = {}

    for key, val in properties.items():
        if val is None:
            continue

        actual_name = _actual_property_name(key, prop_name_map)
        notion_props[actual_name] = _build_notion_property(key, val)

    return notion_props


def _actual_property_name(key: str, prop_name_map: Optional[Mapping[str, str]]) -> str:
    if isinstance(prop_name_map, Mapping):
        return prop_name_map.get(key, key)
    return key


def _build_notion_property(key: str, val: Any) -> Dict[str, Any]:
    canonical = key.lower()
    if canonical == "role":
        return {"title": [_text_property(val)]}
    if canonical in (
        "date",
        "applied_date",
        "applied date",
        "last_update_date",
        "last update date",
    ):
        return {"date": {"start": str(val)}}
    if canonical == "type":
        return {"select": {"name": str(val)}}
    if canonical == "stage":
        return {"status": {"name": str(val)}}
    if canonical == "source":
        return {"select": {"name": str(val)}}
    if canonical == "company":
        return {"rich_text": [_text_property(val)]}
    if canonical in ("url", "website", "link"):
        return {"url": str(val)}
    if canonical == "email":
        return {"email": str(val)}
    if canonical in ("phone", "phone_number"):
        return {"phone_number": str(val)}
    if isinstance(val, bool):
        return {"checkbox": val}
    if isinstance(val, (int, float)):
        return {"number": val}
    return {"rich_text": [_text_property(val)]}


def _text_property(val: Any) -> Dict[str, Dict[str, str]]:
    return {"text": {"content": str(val)}}


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

        # Ensure Authorization header uses the provided API key (was masked in source)
        self.headers["Authorization"] = f"Bearer {self.api_key}"

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
            res = httpx.patch(url, headers=self.headers, json=payload, timeout=20)

            if res.status_code == 200:
                print(f"   ✅ Notion row updated successfully (ID: {page_id[:8]}...)")
                return True
            print(f"   ❌ Failed to update Notion row: {res.status_code} - {res.text}")
            return False
        except httpx.RequestError as exc:
            print(f"   ❌ Exception while updating Notion row: {exc}")
            return False

    def create_page(
        self,
        database_id: str,
        properties: Dict[str, Any],
        prop_name_map: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Create a new page (row) in a Notion database from simple properties.

        properties: mapping of canonical property names (Company, Role, URL,
        Applied date, Description, Tracked)to scalar values. If prop_name_map is
        provided it should map canonical names to the actual property names used
        in the target Notion database.

        Returns the created page id on success or None on failure.
        """
        url = f"{self.base_url}/pages"

        notion_props = build_notion_properties(properties, prop_name_map)
        payload = {"parent": {"database_id": database_id}, "properties": notion_props}

        try:
            res = httpx.post(url, headers=self.headers, json=payload, timeout=20)
            if res.status_code in (200, 201):
                data = res.json()
                page_id = data.get("id")
                print(
                    f"   ✅ Notion page created (ID: {page_id[:8]}...)"
                    if page_id
                    else "   ✅ Notion page created"
                )
                return page_id
            print(f"   ❌ Failed to create Notion page: {res.status_code} - {res.text}")
            return None
        except httpx.RequestError as exc:
            print(f"   ❌ Exception while creating Notion page: {exc}")
            return None

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
            return "".join([t.get("plain_text", "") for t in values]).strip()

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
        # prop_type can be None or non-string; ensure we only use str keys for lookup
        handler = type_handlers.get(prop_type) if isinstance(prop_type, str) else None
        if handler:
            retval = handler(prop)
            print(f"prop_type: {prop_type}, return value: {retval} ")
            return retval

        if isinstance(prop_type, str):
            return str(prop.get(prop_type, ""))
        return ""
