import os
import json
import logging
import urllib.request

logger = logging.getLogger(__name__)


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

        # MQTT credentials: try Supervisor API first, then env vars, then defaults
        self.supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "")
        mqtt = self._fetch_mqtt_from_supervisor()
        if mqtt:
            self.mqtt_host = mqtt["host"]
            self.mqtt_port = mqtt["port"]
            self.mqtt_user = mqtt["username"]
            self.mqtt_password = mqtt["password"]
        else:
            # Fallback to env vars
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

        # Final fallback: ensure host has a default
        if not self.mqtt_host:
            self.mqtt_host = "core-mosquitto"

        logger.info(
            "MQTT config: host=%s, port=%s, user=%r",
            self.mqtt_host,
            self.mqtt_port,
            self.mqtt_user,
        )

    def _fetch_mqtt_from_supervisor(self) -> dict | None:
        """Fetch MQTT credentials from HA Supervisor API.

        Returns:
            Dict with host, port, username, password on success; None on failure.
        """
        token = self.supervisor_token
        if not token:
            logger.warning(
                "SUPERVISOR_TOKEN not available, cannot fetch MQTT from Supervisor API"
            )
            return None

        try:
            req = urllib.request.Request(
                "http://supervisor/services/mqtt",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read()).get("data", {})

            host = data.get("host", "core-mosquitto")
            port = int(data.get("port", 1883))
            username = data.get("username", "")
            password = data.get("password", "")

            logger.info(
                "MQTT credentials fetched from Supervisor API (host=%s, port=%d, user=%r)",
                host,
                port,
                username,
            )
            return {
                "host": host,
                "port": port,
                "username": username,
                "password": password,
            }
        except Exception as e:
            logger.error("Failed to fetch MQTT from Supervisor API: %s", e)
            return None

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
