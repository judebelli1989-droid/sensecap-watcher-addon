from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class LLMResponse:
    text: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0


class LLMAdapter(ABC):
    @abstractmethod
    async def chat(
        self, messages: List[Dict[str, Any]], tools: Optional[List[Dict]] = None
    ) -> LLMResponse:
        """Send chat messages, optionally with tools. Returns LLMResponse."""
        pass

    @abstractmethod
    async def vision(self, image_bytes: bytes, prompt: str) -> Dict[str, Any]:
        """Analyze image with prompt. Returns dict with 'description' and 'confidence'."""
        pass


def create_llm_adapter(config) -> LLMAdapter:
    """Factory to create appropriate LLM adapter based on config.llm_provider."""
    if config.llm_provider == "ollama":
        from ollama_adapter import OllamaAdapter

        return OllamaAdapter(config)
    else:  # default to claude
        from claude_adapter import ClaudeAdapter

        return ClaudeAdapter(config)
