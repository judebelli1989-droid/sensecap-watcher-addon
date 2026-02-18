"""Main orchestrator for SenseCAP Watcher addon."""

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import websockets
from aiohttp import web

from config import Config
from llm_base import create_llm_adapter, LLMAdapter
from ha_integration import HAIntegration
from monitoring import MonitoringService
from display import DisplayManager
from yandex_speechkit import YandexSpeechKit
from ha_tools import HATools, HA_TOOLS

logger = logging.getLogger(__name__)


class WatcherServer:
    """Main server orchestrating WebSocket, OTA, and all components."""

    def __init__(self, config: Config):
        """Initialize WatcherServer.

        Args:
            config: Configuration object
        """
        self.config = config

        # WebSocket state
        self._device_ws: Optional[websockets.WebSocketServerProtocol] = None
        self._reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 60.0
        self._running: bool = True

        # Components (initialized in initialize())
        self._llm_adapter: Optional[LLMAdapter] = None
        self._ha_integration: Optional[HAIntegration] = None
        self._monitoring: Optional[MonitoringService] = None
        self._display: Optional[DisplayManager] = None
        self._speechkit: Optional[YandexSpeechKit] = None
        self._ha_tools: Optional[HATools] = None

        # Servers
        self._ws_server = None
        self._ota_runner = None
        self._ota_site = None

        # Tasks
        self._monitoring_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """Initialize all components."""
        logger.info("Initializing WatcherServer components...")

        # Create LLM adapter via factory
        self._llm_adapter = create_llm_adapter(self.config)
        logger.info(f"LLM adapter created: {self.config.llm_provider}")

        # Create and connect HA integration
        self._ha_integration = HAIntegration(self.config)
        connected = await self._ha_integration.connect()
        if connected:
            logger.info("Connected to MQTT broker")
            await self._ha_integration.register_entities()
            await self._ha_integration.subscribe_commands(self._handle_ha_command)
        else:
            logger.warning("Failed to connect to MQTT broker")

        # Create monitoring service
        self._monitoring = MonitoringService(
            self.config, self._llm_adapter, self._ha_integration
        )

        # Create display manager
        self._display = DisplayManager(self._send_to_device)

        # Create Yandex SpeechKit
        self._speechkit = YandexSpeechKit(self.config)

        # Create HA Tools
        self._ha_tools = HATools(self.config)

        logger.info("All components initialized")

    async def _handle_ha_command(self, topic: str, payload: str):
        """Handle commands from Home Assistant.

        Args:
            topic: MQTT topic
            payload: Command payload
        """
        logger.debug(f"HA command: {topic} = {payload}")

        # Parse topic to get component and object_id
        # Format: sensecap_watcher/{component}/{object_id}/set
        parts = topic.split("/")
        if len(parts) < 4:
            return

        component = parts[1]
        object_id = parts[2]

        try:
            if component == "switch" and object_id == "monitoring":
                enabled = payload.upper() == "ON"
                self._monitoring.set_monitoring_enabled(enabled)
                await self._ha_integration.publish_state(
                    "switch/monitoring", "ON" if enabled else "OFF"
                )

            elif component == "button" and object_id == "analyze_scene":
                # Trigger manual scene analysis
                if self._device_ws:
                    await self._send_to_device(
                        json.dumps({"type": "request_frame", "payload": {}})
                    )

            elif component == "text" and object_id == "custom_prompt":
                self.config.custom_prompt = payload
                await self._ha_integration.publish_state("text/custom_prompt", payload)

            elif component == "number" and object_id == "monitoring_interval":
                self.config.monitoring_interval = int(payload)
                await self._ha_integration.publish_state(
                    "number/monitoring_interval", payload
                )

            elif component == "number" and object_id == "confidence_threshold":
                self.config.confidence_threshold = float(payload) / 100.0
                await self._ha_integration.publish_state(
                    "number/confidence_threshold", payload
                )

            elif component == "switch" and object_id == "voice_assistant":
                # Toggle voice assistant
                await self._ha_integration.publish_state(
                    "switch/voice_assistant", payload
                )

            elif component == "notify" and object_id == "tts":
                # Text-to-speech
                audio = await self._speechkit.synthesize(payload)
                if audio and self._device_ws:
                    await self._send_to_device(
                        json.dumps(
                            {
                                "type": "audio_play",
                                "payload": {"data": audio.hex(), "format": "opus"},
                            }
                        )
                    )

            elif component == "siren" and object_id == "alarm":
                # Siren control
                if self._device_ws:
                    await self._send_to_device(
                        json.dumps(
                            {"type": "siren", "payload": {"state": payload.upper()}}
                        )
                    )
                await self._ha_integration.publish_state("siren/alarm", payload)

            elif component == "select" and object_id == "display_mode":
                from display import DisplayMode

                mode_map = {
                    "Clock": DisplayMode.CLOCK,
                    "Weather": DisplayMode.WEATHER,
                    "Status": DisplayMode.STATUS,
                    "AI Log": DisplayMode.AI_LOG,
                    "Custom": DisplayMode.CUSTOM,
                }
                if payload in mode_map:
                    await self._display.set_mode(mode_map[payload])
                    await self._ha_integration.publish_state(
                        "select/display_mode", payload
                    )

            elif component == "text" and object_id == "display_message":
                await self._display.show_message(payload)
                await self._ha_integration.publish_state(
                    "text/display_message", payload
                )

            elif component == "switch" and object_id == "display_power":
                on = payload.upper() == "ON"
                await self._display.set_power(on)
                await self._ha_integration.publish_state(
                    "switch/display_power", "ON" if on else "OFF"
                )

        except Exception as e:
            logger.error(f"Error handling HA command: {e}")

    async def _send_to_device(self, message: str):
        """Send message to connected device.

        Args:
            message: JSON message string
        """
        if self._device_ws:
            try:
                await self._device_ws.send(message)
            except Exception as e:
                logger.error(f"Failed to send to device: {e}")

    # ==================== WebSocket Server ====================

    async def start_websocket_server(self):
        """Start WebSocket server for device connections."""
        self._ws_server = await websockets.serve(
            self.handle_device_connection,
            "0.0.0.0",
            self.config.websocket_port,
        )
        logger.info(f"WebSocket server started on port {self.config.websocket_port}")

    async def handle_device_connection(self, websocket, path):
        """Handle device WebSocket connection.

        Args:
            websocket: WebSocket connection
            path: Connection path
        """
        logger.info(f"Device connected from {websocket.remote_address}")

        self._device_ws = websocket
        self.reset_reconnect_delay()

        # Update connected state in HA
        if self._ha_integration:
            await self._ha_integration.publish_state("binary_sensor/connected", "ON")

        try:
            async for message in websocket:
                await self.process_device_message(message)
        except websockets.ConnectionClosed as e:
            logger.warning(f"Device disconnected: {e}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            self._device_ws = None
            await self.handle_disconnect()

    async def process_device_message(self, message: str):
        """Process incoming message from device.

        Args:
            message: JSON message string
        """
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")
            payload = data.get("payload", {})

            logger.debug(f"Device message: type={msg_type}")

            if msg_type == "audio":
                # Audio data from device (for STT)
                audio_bytes = bytes.fromhex(payload.get("data", ""))
                if audio_bytes:
                    # Check for noise
                    noise_detected = await self._monitoring.detect_noise(audio_bytes)
                    if self._ha_integration:
                        await self._ha_integration.publish_state(
                            "binary_sensor/noise_detected",
                            "ON" if noise_detected else "OFF",
                        )

                    # Perform STT
                    text = await self._speechkit.recognize(audio_bytes)
                    if text:
                        logger.info(f"STT result: {text}")
                        if self._ha_integration:
                            await self._ha_integration.fire_event(
                                "voice_command", {"text": text}
                            )

            elif msg_type == "image":
                # Image frame from device
                image_bytes = bytes.fromhex(payload.get("data", ""))
                if image_bytes:
                    # Publish to HA image entity
                    if self._ha_integration:
                        await self._ha_integration._publish(
                            f"{HAIntegration.NODE_ID}/image/snapshot/image",
                            image_bytes,
                            retain=True,
                        )

                    # Check for motion and analyze if needed
                    motion = await self._monitoring.detect_motion(image_bytes)
                    if self._ha_integration:
                        await self._ha_integration.publish_state(
                            "binary_sensor/motion_detected", "ON" if motion else "OFF"
                        )

                    if motion:
                        result = await self._monitoring.analyze_scene(image_bytes)
                        if result and self._ha_integration:
                            await self._ha_integration.publish_state(
                                "sensor/last_event",
                                result.get("description", "")[:255],
                            )

            elif msg_type == "wheel":
                # Wheel rotation event
                direction = payload.get("direction", "")
                logger.info(f"Wheel event: {direction}")

            elif msg_type == "button":
                # Button press event
                action = payload.get("action", "")
                logger.info(f"Button event: {action}")

            elif msg_type == "status":
                # Device status update
                logger.debug(f"Device status: {payload}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from device: {e}")
        except Exception as e:
            logger.error(f"Error processing device message: {e}")

    # ==================== OTA HTTP Server ====================

    async def start_ota_server(self):
        """Start OTA HTTP server."""
        app = web.Application()
        app.router.add_get("/ota/version", self.handle_ota_version)
        app.router.add_get("/ota/firmware", self.handle_ota_firmware)

        self._ota_runner = web.AppRunner(app)
        await self._ota_runner.setup()
        self._ota_site = web.TCPSite(self._ota_runner, "0.0.0.0", self.config.ota_port)
        await self._ota_site.start()
        logger.info(f"OTA HTTP server started on port {self.config.ota_port}")

    async def handle_ota_version(self, request: web.Request) -> web.Response:
        """Handle OTA version request.

        Args:
            request: HTTP request

        Returns:
            JSON response with version info
        """
        version_info = {
            "version": "1.0.0",
            "build": "1",
            "date": "2024-01-01",
        }
        return web.json_response(version_info)

    async def handle_ota_firmware(self, request: web.Request) -> web.Response:
        """Handle OTA firmware download request.

        Args:
            request: HTTP request

        Returns:
            Firmware file or 404
        """
        firmware_path = Path("/data/firmware.bin")
        if firmware_path.exists():
            return web.FileResponse(firmware_path)
        return web.Response(status=404, text="Firmware not found")

    # ==================== Reconnect Logic ====================

    async def handle_disconnect(self):
        """Handle device disconnection with exponential backoff."""
        if self._ha_integration:
            await self._ha_integration.publish_state("binary_sensor/connected", "OFF")

        # Exponential backoff
        self._reconnect_delay = min(
            self._reconnect_delay * 2, self._max_reconnect_delay
        )
        logger.info(
            f"Device disconnected. Next reconnect delay: {self._reconnect_delay}s"
        )

    def reset_reconnect_delay(self):
        """Reset reconnect delay to initial value."""
        self._reconnect_delay = 1.0

    # ==================== Graceful Shutdown ====================

    async def shutdown(self):
        """Gracefully shutdown all components."""
        logger.info("Shutting down WatcherServer...")
        self._running = False

        # Cancel monitoring task
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        # Close device WebSocket
        if self._device_ws:
            await self._device_ws.close()
            self._device_ws = None

        # Close WebSocket server
        if self._ws_server:
            self._ws_server.close()
            await self._ws_server.wait_closed()

        # Close OTA server
        if self._ota_runner:
            await self._ota_runner.cleanup()

        # Disconnect from MQTT
        if self._ha_integration:
            await self._ha_integration.disconnect()

        # Close adapters
        if self._llm_adapter and hasattr(self._llm_adapter, "close"):
            await self._llm_adapter.close()

        if self._speechkit:
            await self._speechkit.close()

        if self._ha_tools:
            await self._ha_tools.close()

        logger.info("WatcherServer shutdown complete")

    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        def signal_handler():
            logger.info("Received shutdown signal")
            asyncio.create_task(self.shutdown())

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)


async def main():
    """Main entry point."""
    # Load config
    config = Config()

    # Setup logging
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )

    logger.info("Starting SenseCAP Watcher addon...")
    logger.info(f"WebSocket port: {config.websocket_port}")
    logger.info(f"OTA port: {config.ota_port}")
    logger.info(f"LLM provider: {config.llm_provider}")
    logger.info(f"MQTT host: {config.mqtt_host}, port: {config.mqtt_port}")
    logger.info(
        f"MQTT user: {config.mqtt_user!r}, has_password: {bool(config.mqtt_password)}"
    )
    logger.info(f"SUPERVISOR_TOKEN present: {bool(config.supervisor_token)}")
    import os

    logger.debug(f"ENV MQTT_HOST={os.environ.get('MQTT_HOST', 'NOT SET')}")
    logger.debug(f"ENV MQTT_USER={os.environ.get('MQTT_USER', 'NOT SET')}")

    # Create server
    server = WatcherServer(config)

    # Setup signal handlers
    server.setup_signal_handlers()

    # Initialize components
    await server.initialize()

    # Start servers
    await server.start_websocket_server()
    await server.start_ota_server()

    logger.info("SenseCAP Watcher addon started successfully")

    # Wait for shutdown
    while server._running:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
