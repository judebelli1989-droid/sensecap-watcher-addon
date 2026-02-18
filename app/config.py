import os
import json
import logging


class Config:
    def __init__(self, options_path: str = "/data/options.json"):
        self.options_path = options_path
        options = {}
        if os.path.exists(options_path):
            try:
                with open(options_path, "r") as f:
                    options = json.load(f)
            except Exception as e:
                logging.error(f"Failed to load options from {options_path}: {e}")

        # JSON options
        self.claude_proxy_url = options.get("claude_proxy_url", "")
        self.claude_proxy_key = options.get("claude_proxy_key", "")
        self.claude_fallback_url = options.get("claude_fallback_url", "")
        self.claude_fallback_key = options.get("claude_fallback_key", "")
        self.claude_model = options.get("claude_model", "claude-3-5-sonnet-20240620")
        self.yandex_api_key = options.get("yandex_api_key", "")
        self.yandex_folder_id = options.get("yandex_folder_id", "")
        self.monitoring_interval = options.get("monitoring_interval", 60)
        self.confidence_threshold = options.get("confidence_threshold", 0.7)
        self.custom_prompt = options.get("custom_prompt", "")
        self.websocket_port = options.get("websocket_port", 8000)
        self.ota_port = options.get("ota_port", 8001)
        self.log_level = options.get("log_level", "info")
        self.llm_provider = options.get("llm_provider", "claude")
        self.ollama_url = options.get("ollama_url", "http://localhost:11434")
        self.ollama_model = options.get("ollama_model", "llama3")
        self.ollama_vision_model = options.get("ollama_vision_model", "llava")

        # Env vars
        self.supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "")
        self.mqtt_host = os.environ.get("MQTT_HOST", "")

        mqtt_port_env = os.environ.get("MQTT_PORT")
        if mqtt_port_env:
            try:
                self.mqtt_port = int(mqtt_port_env)
            except ValueError:
                self.mqtt_port = 1883
        else:
            self.mqtt_port = 1883

        self.mqtt_user = os.environ.get("MQTT_USER", "")
        self.mqtt_password = os.environ.get("MQTT_PASSWORD", "")

    def _mask(self, val: str) -> str:
        if not val or not isinstance(val, str):
            return "***" if val else ""
        return val[:3] + "***"

    def __repr__(self):
        return (
            f"Config("
            f"claude_proxy_url={self.claude_proxy_url!r}, "
            f"claude_proxy_key={self._mask(self.claude_proxy_key)!r}, "
            f"claude_fallback_url={self.claude_fallback_url!r}, "
            f"claude_fallback_key={self._mask(self.claude_fallback_key)!r}, "
            f"claude_model={self.claude_model!r}, "
            f"yandex_api_key={self._mask(self.yandex_api_key)!r}, "
            f"yandex_folder_id={self.yandex_folder_id!r}, "
            f"monitoring_interval={self.monitoring_interval!r}, "
            f"confidence_threshold={self.confidence_threshold!r}, "
            f"websocket_port={self.websocket_port!r}, "
            f"ota_port={self.ota_port!r}, "
            f"log_level={self.log_level!r}, "
            f"llm_provider={self.llm_provider!r}, "
            f"ollama_url={self.ollama_url!r}, "
            f"ollama_model={self.ollama_model!r}, "
            f"ollama_vision_model={self.ollama_vision_model!r}, "
            f"mqtt_host={self.mqtt_host!r}, "
            f"mqtt_port={self.mqtt_port!r}, "
            f"mqtt_user={self.mqtt_user!r}, "
            f"mqtt_password={self._mask(self.mqtt_password)!r}"
            f")"
        )
