import json
import logging
import asyncio
from enum import Enum

logger = logging.getLogger(__name__)


class DisplayMode(Enum):
    CLOCK = "clock"
    WEATHER = "weather"
    STATUS = "status"
    AI_LOG = "ai_log"
    CUSTOM = "custom"


EMOTIONS = [
    "neutral",
    "happy",
    "sad",
    "angry",
    "surprised",
    "confused",
    "thinking",
    "sleeping",
    "winking",
    "love",
    "cool",
    "crying",
    "laughing",
    "scared",
    "sick",
    "dizzy",
    "dead",
    "robot",
    "alien",
    "ghost",
    "devil",
    "angel",
    "cat",
    "dog",
]


class DisplayManager:
    """
    Manages the SenseCAP device display including modes, power, and animations.
    """

    def __init__(self, websocket_send_func):
        """
        Initialize DisplayManager.

        Args:
            websocket_send_func: Coroutine function to send messages via WebSocket.
        """
        self._ws_send = websocket_send_func
        self._current_mode: DisplayMode = DisplayMode.CLOCK
        self._power: bool = True

    async def set_mode(self, mode: DisplayMode):
        """
        Set the current display mode.
        """
        self._current_mode = mode
        logger.info(f"Setting display mode to: {mode.value}")
        await self._send_display_command({"action": "set_mode", "mode": mode.value})

    async def get_mode(self) -> DisplayMode:
        """
        Get the current display mode.
        """
        return self._current_mode

    async def set_power(self, on: bool):
        """
        Set the display power state.
        """
        self._power = on
        logger.info(f"Setting display power: {'ON' if on else 'OFF'}")
        await self._send_display_command({"action": "power", "state": on})

    async def get_power(self) -> bool:
        """
        Get the current power state.
        """
        return self._power

    async def show_message(self, text: str, duration: int = 5000):
        """
        Display a text message on the device.

        Args:
            text: Message text.
            duration: Duration in milliseconds.
        """
        logger.debug(f"Showing message: {text} for {duration}ms")
        await self._send_display_command(
            {"action": "show_text", "text": text, "duration": duration}
        )

    async def show_emotion(self, emotion: str, duration: int = 3000):
        """
        Show an emotion animation.

        Args:
            emotion: Emotion name from EMOTIONS list.
            duration: Duration in milliseconds.
        """
        if emotion not in EMOTIONS:
            logger.warning(f"Invalid emotion: {emotion}")
            return

        logger.debug(f"Showing emotion: {emotion} for {duration}ms")
        await self._send_display_command(
            {"action": "show_emotion", "emotion": emotion, "duration": duration}
        )

    async def show_weather(self, temp: float, condition: str, icon: str):
        """
        Display weather information.
        """
        logger.debug(f"Showing weather: {temp}°C, {condition}")
        await self._send_display_command(
            {
                "action": "show_weather",
                "temp": temp,
                "condition": condition,
                "icon": icon,
            }
        )

    async def show_ai_log(self, entries: list):
        """
        Show recent AI analysis entries on the display.
        """
        logger.debug(f"Showing AI log with {len(entries)} entries")
        await self._send_display_command({"action": "show_ai_log", "entries": entries})

    async def _send_display_command(self, command: dict):
        """
        Format and send a display command via WebSocket.
        """
        message = {"type": "display", "payload": command}
        try:
            await self._ws_send(json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to send display command: {e}")
