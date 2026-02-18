"""Main orchestrator for SenseCAP Watcher addon."""

import asyncio
import base64
import json
import logging
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

import websockets
from aiohttp import web
from sensecraft_mcp import SenseCraftMCP

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

        # Camera
        self._last_photo: Optional[bytes] = None
        self._photo_event: Optional[asyncio.Event] = None

        # Tasks
        self._monitoring_task: Optional[asyncio.Task] = None

        # MQTT device state
        self._device_mac: Optional[str] = None
        self._device_command_topic: Optional[str] = None

        # Command queue for offline delivery
        self._command_queue = []  # Queue of JSON strings to send to device

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
            await self._ha_integration.publish_initial_states()
            await self._ha_integration.subscribe_commands(self._handle_ha_command)
            self._ha_integration.set_device_message_callback(
                self.process_device_message
            )
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

        # Start SenseCraft MCP bridge (connects to SenseCraft Agent cloud)
        self._sensecraft_mcp: Optional[SenseCraftMCP] = None
        if self.config.sensecraft_mcp_url:
            self._sensecraft_mcp = SenseCraftMCP(
                self.config.sensecraft_mcp_url, self._ha_tools
            )
            await self._sensecraft_mcp.start()
            logger.info("SenseCraft MCP bridge started")

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
                await self._send_to_device(
                    json.dumps(
                        {
                            "type": "alert",
                            "status": "Analyzing",
                            "message": "Analyzing scene...",
                            "emotion": "thinking",
                        }
                    )
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
                await self._send_to_device(
                    json.dumps(
                        {"type": "tts", "state": "sentence_start", "text": payload}
                    )
                )

            elif component == "siren" and object_id == "alarm":
                if payload.upper() == "ON":
                    await self._send_to_device(
                        json.dumps(
                            {
                                "type": "alert",
                                "status": "ALARM",
                                "message": "Alarm triggered!",
                                "emotion": "shocked",
                            }
                        )
                    )
                else:
                    await self._send_to_device(
                        json.dumps({"type": "llm", "emotion": "neutral"})
                    )
                await self._ha_integration.publish_state("siren/alarm", payload)

            elif component == "select" and object_id == "display_mode":
                mode_to_emotion = {
                    "Clock": "neutral",
                    "Weather": "cool",
                    "Status": "thinking",
                    "AI Log": "confident",
                    "Custom": "neutral",
                }
                if payload in mode_to_emotion:
                    await self._send_to_device(
                        json.dumps({"type": "llm", "emotion": mode_to_emotion[payload]})
                    )
                    await self._display.set_mode_local(payload)
                    await self._ha_integration.publish_state(
                        "select/display_mode", payload
                    )

            elif component == "text" and object_id == "display_message":
                await self._send_to_device(
                    json.dumps(
                        {"type": "tts", "state": "sentence_start", "text": payload}
                    )
                )
                await self._ha_integration.publish_state(
                    "text/display_message", payload
                )

            elif component == "switch" and object_id == "display_power":
                on = payload.upper() == "ON"
                if on:
                    await self._send_to_device(
                        json.dumps({"type": "llm", "emotion": "neutral"})
                    )
                await self._ha_integration.publish_state(
                    "switch/display_power", "ON" if on else "OFF"
                )

            elif component == "raw" and object_id == "mcp":
                # Send raw MCP tool call to device
                # payload = tool name, or JSON {"name": "...", "arguments": {...}}
                try:
                    params = json.loads(payload)
                    tool_name = params.get("name", payload)
                    tool_args = params.get("arguments", {})
                except (json.JSONDecodeError, AttributeError):
                    tool_name = payload
                    tool_args = {}

                self._mcp_id = getattr(self, "_mcp_id", 0) + 1
                mcp_msg = {
                    "type": "mcp",
                    "payload": {
                        "jsonrpc": "2.0",
                        "id": self._mcp_id,
                        "method": "tools/call",
                        "params": {
                            "name": tool_name,
                            "arguments": tool_args,
                        },
                    },
                }
                await self._send_to_device(json.dumps(mcp_msg))
                logger.info(f"Sent MCP tool call: {tool_name}({tool_args})")

        except Exception as e:
            logger.error(f"Error handling HA command: {e}")

    async def _send_to_device(self, message: str):
        """Send command to device via WebSocket, or queue if offline."""
        if self._device_ws:
            try:
                await self._device_ws.send(message)
                logger.info("Sent to device via WebSocket")
                return
            except Exception as e:
                logger.warning(f"WebSocket send failed: {e}")

        self._command_queue.append(message)
        logger.info(
            f"Command queued for delivery (queue size: {len(self._command_queue)})"
        )

    async def _flush_command_queue(self):
        """Send all queued commands to device."""
        if not self._command_queue or not self._device_ws:
            return

        logger.info(f"Flushing {len(self._command_queue)} queued commands")
        while self._command_queue:
            msg = self._command_queue.pop(0)
            try:
                await self._device_ws.send(msg)
                logger.info("Delivered queued command")
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"Failed to deliver queued command: {e}")
                self._command_queue.insert(0, msg)
                break

    async def _subscribe_device_mqtt(self, mac_clean: str):
        """Subscribe to device MQTT topic to receive device messages."""
        device_topic = f"xiaozhi/device/{mac_clean}"
        if self._ha_integration and self._ha_integration._client:
            result, mid = self._ha_integration._client.subscribe(device_topic)
            logger.info(f"Subscribed to device topic {device_topic}: result={result}")

            self._device_command_topic = f"xiaozhi/server/{mac_clean}"

            if self._ha_integration:
                await self._ha_integration.publish_state(
                    "binary_sensor/connected", "ON"
                )
        else:
            logger.warning("Cannot subscribe to device topic: MQTT not connected")

    # ==================== WebSocket Server ====================

    async def start_websocket_server(self):
        """Start WebSocket server for device connections."""
        self._ws_server = await websockets.serve(
            self.handle_device_connection,
            "0.0.0.0",
            self.config.websocket_port,
        )
        logger.info(f"WebSocket server started on port {self.config.websocket_port}")

    async def handle_device_connection(self, websocket):
        """Handle device WebSocket connection.

        Args:
            websocket: WebSocket connection
        """
        logger.info(f"Device connected from {websocket.remote_address}")

        self._device_ws = websocket
        self.reset_reconnect_delay()

        # Update connected state in HA
        if self._ha_integration:
            await self._ha_integration.publish_state("binary_sensor/connected", "ON")

        await self._flush_command_queue()

        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    # Binary message = opus audio data
                    await self._handle_binary_message(message)
                else:
                    # Text message = JSON
                    await self.process_device_message(message)
        except websockets.ConnectionClosed as e:
            logger.warning(f"Device disconnected: {e}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            self._device_ws = None
            await self.handle_disconnect()

    async def process_device_message(self, message: str):
        """Process incoming JSON message from device."""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")
            payload = data.get("payload", {})

            logger.info(f"Device message: type={msg_type}")

            if msg_type == "hello":
                session_id = str(uuid.uuid4())
                hello_response = {
                    "type": "hello",
                    "transport": "websocket",
                    "session_id": session_id,
                    "audio_params": {"sample_rate": 24000, "frame_duration": 60},
                }
                await self._send_to_device(json.dumps(hello_response))
                logger.info(f"Hello handshake completed, session: {session_id}")

                # Send MCP initialize with vision capabilities
                self._mcp_id = getattr(self, "_mcp_id", 0) + 1
                mcp_init = {
                    "type": "mcp",
                    "payload": {
                        "jsonrpc": "2.0",
                        "id": self._mcp_id,
                        "method": "initialize",
                        "params": {
                            "capabilities": {
                                "vision": {
                                    "url": f"http://{self.config.host_ip}:{self.config.ota_port}/vision/explain",
                                    "token": "sensecap-local",
                                }
                            }
                        },
                    },
                }
                await self._send_to_device(json.dumps(mcp_init))
                logger.info("Sent MCP initialize with vision URL")
                return

            elif msg_type == "listen":
                state = data.get("state", "")
                logger.info(f"Device listen state: {state}")

                if state in ("detect", "start"):
                    await asyncio.sleep(0.5)
                    stop_msg = json.dumps({"type": "tts", "state": "stop"})
                    if self._device_ws:
                        await self._device_ws.send(stop_msg)
                        logger.info("Sent TTS stop to end listen session")

                    await self._flush_command_queue()
                return

            elif msg_type == "audio":
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

            elif msg_type == "mcp":
                logger.info(
                    f"MCP response from device: {json.dumps(payload, ensure_ascii=False)[:500]}"
                )
                if self._ha_integration:
                    await self._ha_integration.publish_state(
                        "sensor/last_event",
                        f"MCP: {json.dumps(payload, ensure_ascii=False)[:255]}",
                    )

            elif msg_type == "wheel":
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

    async def _handle_binary_message(self, data: bytes):
        """Handle binary message (opus audio) from device."""
        # Just log receipt for now - noise detection and STT not configured
        if not hasattr(self, "_binary_msg_count"):
            self._binary_msg_count = 0
        self._binary_msg_count += 1
        if self._binary_msg_count == 1 or self._binary_msg_count % 100 == 0:
            logger.debug(
                f"Received {self._binary_msg_count} audio frames ({len(data)} bytes)"
            )

    # ==================== OTA HTTP Server ====================

    async def start_ota_server(self):
        """Start OTA HTTP server."""
        app = web.Application()
        app.router.add_get("/ota/version", self.handle_ota_version)
        app.router.add_get("/ota/firmware", self.handle_ota_firmware)
        app.router.add_post("/ota/", self.handle_ota_post)
        app.router.add_post("/ota", self.handle_ota_post)
        app.router.add_post("/vision/explain", self.handle_vision_explain)

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

    async def handle_ota_post(self, request: web.Request) -> web.Response:
        """Handle xiaozhi OTA check-in from device."""
        try:
            body = await request.read()
            try:
                device_info = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                device_info = {}

            app_info = device_info.get("application", {})
            board_info = device_info.get("board", {})
            device_version = app_info.get("version", "unknown")
            device_ip = board_info.get("ip", request.remote)
            mac = device_info.get("mac_address", "unknown")
            # Clean MAC for topic use (remove colons)
            mac_clean = mac.replace(":", "").lower() if mac != "unknown" else "unknown"

            logger.info(
                f"OTA check-in: device={mac}, version={device_version}, ip={device_ip}"
            )

            # Store device MAC for MQTT topic routing
            self._device_mac = mac_clean

            # Use WebSocket protocol - device connects on demand
            # MQTT protocol causes crash on SenseCAP Watcher firmware
            ha_host = request.host.split(":")[0]  # IP device used to reach OTA
            ws_port = self.config.websocket_port

            response = {
                "server_time": {
                    "timestamp": int(time.time() * 1000),
                    "timezone_offset": 0,
                },
                "websocket": {
                    "url": f"ws://{ha_host}:{ws_port}/ws",
                },
                "firmware": {},
            }

            logger.info(f"OTA response: websocket=ws://{ha_host}:{ws_port}/ws")
            return web.json_response(response)
        except Exception as e:
            logger.error(f"OTA POST handler error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_vision_explain(self, request: web.Request) -> web.Response:
        """Receive JPEG from device camera and return AI analysis."""
        try:
            reader = await request.multipart()
            image_data = None
            question = "What do you see?"

            async for part in reader:
                if part.name == "file" or part.filename:
                    image_data = await part.read()
                elif part.name == "question":
                    question = (await part.read()).decode("utf-8")

            if not image_data:
                return web.json_response(
                    {"success": False, "message": "No image received"}, status=400
                )

            logger.info(
                f"Received camera image: {len(image_data)} bytes, question: {question}"
            )

            self._last_photo = image_data
            if self._photo_event:
                self._photo_event.set()

            # Publish JPEG to HA as camera entity via MQTT
            if self._ha_integration:
                await self._ha_integration._publish(
                    f"{HAIntegration.NODE_ID}/image/snapshot/image",
                    image_data,
                    retain=True,
                )

            # Save to /data for debugging
            photo_path = Path("/data/last_photo.jpg")
            photo_path.write_bytes(image_data)

            # Try LLM vision analysis if available
            description = f"Photo captured ({len(image_data)} bytes)"
            if self._llm_adapter and hasattr(self._llm_adapter, "analyze_image"):
                try:
                    img_b64 = base64.b64encode(image_data).decode("utf-8")
                    description = await self._llm_adapter.analyze_image(
                        img_b64, question
                    )
                except Exception as e:
                    logger.warning(f"LLM vision analysis failed: {e}")

            if self._ha_integration:
                await self._ha_integration.publish_state(
                    "sensor/last_event", description[:255]
                )

            return web.json_response({"success": True, "message": description})

        except Exception as e:
            logger.error(f"Vision explain error: {e}")
            return web.json_response({"success": False, "message": str(e)}, status=500)

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
