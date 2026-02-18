import httpx
import base64
import json
import logging
from typing import List, Dict, Any, Optional
from llm_base import LLMAdapter, LLMResponse

logger = logging.getLogger(__name__)


class ClaudeAdapter(LLMAdapter):
    def __init__(self, config):
        self.config = config
        self.client = httpx.AsyncClient(timeout=30.0)
        self.anthropic_version = "2023-06-01"

    async def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Helper to handle proxy/fallback logic."""
        urls = [
            (self.config.claude_proxy_url, self.config.claude_proxy_key),
            (self.config.claude_fallback_url, self.config.claude_fallback_key),
        ]

        last_error = None
        for url, api_key in urls:
            if not url or not api_key:
                continue

            headers = {
                "x-api-key": api_key,
                "anthropic-version": self.anthropic_version,
                "content-type": "application/json",
            }

            try:
                response = await self.client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.warning(f"Failed to call Claude API at {url}: {e}")
                last_error = e
                continue

        raise last_error or Exception("No valid Claude API configuration found")

    async def chat(
        self, messages: List[Dict[str, Any]], tools: Optional[List[Dict]] = None
    ) -> LLMResponse:
        payload = {
            "model": self.config.claude_model,
            "max_tokens": 4096,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools

        try:
            data = await self._make_request(payload)

            text = ""
            tool_calls = []

            for content in data.get("content", []):
                if content["type"] == "text":
                    text += content["text"]
                elif content["type"] == "tool_use":
                    tool_calls.append(
                        {
                            "id": content["id"],
                            "name": content["name"],
                            "input": content["input"],
                        }
                    )

            return LLMResponse(text=text, tool_calls=tool_calls)
        except Exception as e:
            logger.error(f"Claude chat error: {e}")
            raise

    async def vision(self, image_bytes: bytes, prompt: str) -> Dict[str, Any]:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64_image,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        # We expect a JSON response from the prompt for vision tasks in this addon
        # usually defining description and confidence.
        payload = {
            "model": self.config.claude_model,
            "max_tokens": 4096,
            "messages": messages,
        }

        try:
            data = await self._make_request(payload)
            response_text = ""
            for content in data.get("content", []):
                if content["type"] == "text":
                    response_text += content["text"]

            # Simple heuristic or JSON parsing for vision response
            # Expected format: {"description": "...", "confidence": 0.9}
            try:
                # Find JSON block in response if it's mixed with text
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                if start != -1 and end != 0:
                    result = json.loads(response_text[start:end])
                else:
                    result = {"description": response_text, "confidence": 0.5}
            except json.JSONDecodeError:
                result = {"description": response_text, "confidence": 0.5}

            return {
                "description": result.get("description", response_text),
                "confidence": result.get("confidence", 0.5),
            }
        except Exception as e:
            logger.error(f"Claude vision error: {e}")
            raise
