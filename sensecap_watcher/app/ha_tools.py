import httpx
import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

HA_TOOLS = [
    {
        "name": "get_states",
        "description": "Get current states of Home Assistant entities",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of entity IDs to query",
                }
            },
            "required": ["entity_ids"],
        },
    },
    {
        "name": "call_service",
        "description": "Call a Home Assistant service",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "The service domain (e.g., light, switch)",
                },
                "service": {
                    "type": "string",
                    "description": "The service name (e.g., turn_on, toggle)",
                },
                "data": {"type": "object", "description": "Service data parameters"},
            },
            "required": ["domain", "service", "data"],
        },
    },
    {
        "name": "get_weather",
        "description": "Get current weather information from a weather entity",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "The weather entity ID (e.g., weather.home)",
                }
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "send_notification",
        "description": "Send a persistent notification to Home Assistant",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The notification message content",
                },
                "title": {
                    "type": "string",
                    "description": "Optional notification title",
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "get_calendar",
        "description": "Get events from a Home Assistant calendar entity",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "The calendar entity ID",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days ahead to fetch events",
                    "default": 7,
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "control_media",
        "description": "Control a media player entity",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "The media_player entity ID",
                },
                "action": {
                    "type": "string",
                    "enum": [
                        "media_play",
                        "media_pause",
                        "media_stop",
                        "media_next_track",
                        "media_previous_track",
                        "toggle",
                    ],
                    "description": "The action to perform",
                },
            },
            "required": ["entity_id", "action"],
        },
    },
]


class HATools:
    def __init__(self, config):
        self.base_url = "http://supervisor/core/api"
        self.headers = {
            "Authorization": f"Bearer {config.supervisor_token}",
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(
            headers=self.headers, base_url=self.base_url, timeout=10.0
        )

    async def execute(self, tool_name: str, args: dict) -> Any:
        method = getattr(self, tool_name, None)
        if not method:
            raise ValueError(f"Unknown tool: {tool_name}")
        return await method(**args)

    async def get_states(self, entity_ids: List[str]) -> List[dict]:
        states = []
        for entity_id in entity_ids:
            try:
                resp = await self.client.get(f"/states/{entity_id}")
                resp.raise_for_status()
                states.append(resp.json())
            except Exception as e:
                logger.error(f"Error fetching state for {entity_id}: {e}")
                states.append({"entity_id": entity_id, "error": str(e)})
        return states

    async def call_service(self, domain: str, service: str, data: dict) -> dict:
        resp = await self.client.post(f"/services/{domain}/{service}", json=data)
        resp.raise_for_status()
        return resp.json()

    async def get_weather(self, entity_id: str) -> dict:
        resp = await self.client.get(f"/states/{entity_id}")
        resp.raise_for_status()
        return resp.json()

    async def send_notification(self, message: str, title: str = None) -> dict:
        data = {"message": message}
        if title:
            data["title"] = title
        resp = await self.client.post(
            "/services/notify/persistent_notification", json=data
        )
        resp.raise_for_status()
        return resp.json()

    async def get_calendar(self, entity_id: str, days: int = 7) -> List[dict]:
        resp = await self.client.get(f"/calendars/{entity_id}")
        resp.raise_for_status()
        return resp.json()

    async def control_media(self, entity_id: str, action: str) -> dict:
        data = {"entity_id": entity_id}
        resp = await self.client.post(f"/services/media_player/{action}", json=data)
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self.client.aclose()
