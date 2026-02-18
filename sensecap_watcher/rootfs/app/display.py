import json
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class DisplayMode(Enum):
    CLOCK = "clock"
    WEATHER = "weather"
    STATUS = "status"
    AI_LOG = "ai_log"
    CUSTOM = "custom"


MODE_TO_EMOTION = {
    DisplayMode.CLOCK: "neutral",
    DisplayMode.WEATHER: "cool",
    DisplayMode.STATUS: "thinking",
    DisplayMode.AI_LOG: "confident",
    DisplayMode.CUSTOM: "neutral",
}

# Valid emoji names supported by xiaozhi firmware (Twemoji32/64)
EMOTIONS = [
    "neutral",
    "happy",
    "laughing",
    "funny",
    "sad",
    "angry",
    "crying",
    "loving",
    "embarrassed",
    "surprised",
    "shocked",
    "thinking",
    "winking",
    "cool",
    "relaxed",
    "delicious",
    "kissy",
    "confident",
    "sleepy",
    "silly",
    "confused",
]


class DisplayManager:
    def __init__(self, websocket_send_func):
        self._ws_send = websocket_send_func
        self._current_mode: DisplayMode = DisplayMode.CLOCK
        self._power: bool = True

    async def set_mode(self, mode: DisplayMode):
        self._current_mode = mode
        emotion = MODE_TO_EMOTION.get(mode, "neutral")
        logger.info(f"Setting display mode to: {mode.value} (emotion: {emotion})")
        await self._send_xiaozhi({"type": "llm", "emotion": emotion})

    async def set_mode_local(self, mode_name: str):
        mode_map = {
            "Clock": DisplayMode.CLOCK,
            "Weather": DisplayMode.WEATHER,
            "Status": DisplayMode.STATUS,
            "AI Log": DisplayMode.AI_LOG,
            "Custom": DisplayMode.CUSTOM,
        }
        if mode_name in mode_map:
            self._current_mode = mode_map[mode_name]

    async def get_mode(self) -> DisplayMode:
        return self._current_mode

    async def set_power(self, on: bool):
        self._power = on
        logger.info(f"Setting display power: {'ON' if on else 'OFF'}")
        if on:
            await self._send_xiaozhi({"type": "llm", "emotion": "neutral"})

    async def get_power(self) -> bool:
        return self._power

    async def show_message(self, text: str):
        logger.debug(f"Showing message: {text}")
        await self._send_xiaozhi(
            {
                "type": "tts",
                "state": "sentence_start",
                "text": text,
            }
        )

    async def show_text(self, text: str):
        await self.show_message(text)

    async def show_emotion(self, emotion: str):
        if emotion not in EMOTIONS:
            logger.warning(f"Invalid emotion: {emotion}")
            return
        logger.debug(f"Showing emotion: {emotion}")
        await self._send_xiaozhi({"type": "llm", "emotion": emotion})

    async def show_alert(self, status: str, message: str, emotion: str = "surprised"):
        logger.debug(f"Showing alert: {status} - {message}")
        await self._send_xiaozhi(
            {
                "type": "alert",
                "status": status,
                "message": message,
                "emotion": emotion,
            }
        )

    async def _send_xiaozhi(self, message: dict):
        try:
            await self._ws_send(json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to send display command: {e}")
