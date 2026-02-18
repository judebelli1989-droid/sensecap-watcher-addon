import httpx
import base64
import json
import logging
from typing import List, Dict, Any, Optional

from llm_base import LLMAdapter, LLMResponse

logger = logging.getLogger(__name__)


class OllamaAdapter(LLMAdapter):
    def __init__(self, config):
        self.config = config
        self.client = httpx.AsyncClient(timeout=60.0)
        self.url = config.ollama_url.rstrip("/")
        self.model = config.ollama_model
        self.vision_model = config.ollama_vision_model

    async def chat(
        self, messages: List[Dict[str, Any]], tools: Optional[List[Dict]] = None
    ) -> LLMResponse:
        payload = {"model": self.model, "messages": messages, "stream": False}

        if tools:
            payload["tools"] = tools

        try:
            response = await self.client.post(f"{self.url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

            message = data.get("message", {})
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])

            return LLMResponse(
                text=content, tool_calls=tool_calls, confidence=1.0 if content else 0.0
            )

        except httpx.HTTPError as e:
            logger.error(f"Ollama chat error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Ollama chat: {e}")
            raise

    async def vision(self, image_bytes: bytes, prompt: str) -> Dict[str, Any]:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "model": self.vision_model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
        }

        try:
            response = await self.client.post(f"{self.url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()

            description = data.get("response", "")

            return {
                "description": description,
                "confidence": 1.0 if description else 0.0,
            }

        except httpx.HTTPError as e:
            logger.error(f"Ollama vision error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Ollama vision: {e}")
            raise

    async def close(self):
        await self.client.aclose()
