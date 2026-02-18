"""Integration tests for SenseCAP Watcher Add-on."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest


class TestModuleImports:
    """Test that all modules can be imported."""

    def test_import_config(self):
        from config import Config

        assert Config is not None

    def test_import_llm_base(self):
        from llm_base import LLMAdapter, LLMResponse, create_llm_adapter

        assert LLMAdapter is not None
        assert LLMResponse is not None

    def test_import_claude_adapter(self):
        from claude_adapter import ClaudeAdapter
        from llm_base import LLMAdapter

        assert issubclass(ClaudeAdapter, LLMAdapter)

    def test_import_ollama_adapter(self):
        from ollama_adapter import OllamaAdapter
        from llm_base import LLMAdapter

        assert issubclass(OllamaAdapter, LLMAdapter)

    def test_import_yandex_speechkit(self):
        from yandex_speechkit import YandexSpeechKit

        assert YandexSpeechKit is not None

    def test_import_ha_tools(self):
        from ha_tools import HATools, HA_TOOLS

        assert HATools is not None
        assert len(HA_TOOLS) == 6

    def test_import_ha_integration(self):
        from ha_integration import HAIntegration

        assert HAIntegration is not None

    def test_import_monitoring(self):
        from monitoring import MonitoringService

        assert MonitoringService is not None

    def test_import_display(self):
        from display import DisplayManager, DisplayMode, EMOTIONS

        assert DisplayManager is not None
        assert len(DisplayMode) == 5
        assert len(EMOTIONS) == 24

    def test_import_main(self):
        from main import WatcherServer

        assert WatcherServer is not None


class TestLLMFactory:
    """Test LLM adapter factory."""

    def test_factory_creates_claude_adapter(self):
        from llm_base import create_llm_adapter
        from claude_adapter import ClaudeAdapter

        class MockConfig:
            llm_provider = "claude"
            claude_proxy_url = "http://test"
            claude_proxy_key = "key"
            claude_fallback_url = "http://test"
            claude_fallback_key = "key"
            claude_model = "claude-3"

        adapter = create_llm_adapter(MockConfig())
        assert isinstance(adapter, ClaudeAdapter)

    def test_factory_creates_ollama_adapter(self):
        from llm_base import create_llm_adapter
        from ollama_adapter import OllamaAdapter

        class MockConfig:
            llm_provider = "ollama"
            ollama_url = "http://localhost:11434"
            ollama_model = "llama3"
            ollama_vision_model = "llava"

        adapter = create_llm_adapter(MockConfig())
        assert isinstance(adapter, OllamaAdapter)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
