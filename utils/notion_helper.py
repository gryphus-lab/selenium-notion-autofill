import httpx
import pandas as pd
from typing import Optional, Dict, List, Any


class NotionHelper:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",  # You can try "2025-09-03" later
        }

    def get_database_data(
        self, database_id: str, filter: Optional[Dict] = None
    ) -> pd.DataFrame:
        """Fetch all rows from Notion database using direct HTTP calls"""
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
                raise Exception(
                    f"Notion API error {response.status_code}: {response.text}"
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

    def _get_property_value(self, prop: Any) -> Any:
        if not prop or not isinstance(prop, dict):
            return None

        prop_type = prop.get("type")

        if prop_type == "title":
            return " ".join(
                [t.get("plain_text", "") for t in prop.get("title", [])]
            ).strip()
        elif prop_type == "rich_text":
            return " ".join(
                [t.get("plain_text", "") for t in prop.get("rich_text", [])]
            ).strip()
        elif prop_type in ["email", "phone_number", "url"]:
            return prop.get(prop_type) or ""
        elif prop_type == "select":
            select = prop.get("select")
            return select.get("name") if select else ""
        elif prop_type == "multi_select":
            return [item.get("name") for item in prop.get("multi_select", [])]
        elif prop_type == "checkbox":
            return prop.get("checkbox", False)
        elif prop_type == "number":
            return prop.get("number")
        elif prop_type == "date":
            date = prop.get("date")
            return date.get("start") if date else ""
        else:
            return str(prop.get(prop_type, ""))
