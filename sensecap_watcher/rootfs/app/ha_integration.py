"""Home Assistant MQTT integration for SenseCAP Watcher."""

import asyncio
import json
import logging
from typing import Any, Optional

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class HAIntegration:
    """Home Assistant integration via MQTT discovery."""

    NODE_ID = "sensecap_watcher"
    DEVICE_INFO = {
        "identifiers": ["sensecap_watcher"],
        "name": "SenseCAP Watcher",
        "manufacturer": "Seeed Studio",
        "model": "SenseCAP Watcher",
    }

    def __init__(self, config):
        """Initialize HA integration.

        Args:
            config: Config object with mqtt_host, mqtt_port, mqtt_user, mqtt_password
        """
        self.config = config
        self._client: Optional[mqtt.Client] = None
        self._connected = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connect callback."""
        if rc == 0:
            logger.info("Connected to MQTT broker")
            if self._loop:
                self._loop.call_soon_threadsafe(self._connected.set)
        else:
            logger.error(f"MQTT connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnect callback."""
        logger.warning(f"Disconnected from MQTT broker (rc={rc})")
        self._connected.clear()

    async def connect(self) -> bool:
        """Connect to MQTT broker.

        Returns:
            True if connected successfully
        """
        self._loop = asyncio.get_event_loop()
        self._client = mqtt.Client(client_id=f"{self.NODE_ID}_integration")
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        if self.config.mqtt_user and self.config.mqtt_password:
            self._client.username_pw_set(
                self.config.mqtt_user, self.config.mqtt_password
            )

        try:
            self._client.connect_async(
                self.config.mqtt_host,
                self.config.mqtt_port,
                keepalive=60,
            )
            self._client.loop_start()

            # Wait for connection with timeout
            try:
                await asyncio.wait_for(self._connected.wait(), timeout=10.0)
                return True
            except asyncio.TimeoutError:
                logger.error("MQTT connection timeout")
                return False
        except Exception as e:
            logger.error(f"MQTT connection error: {e}")
            return False

    async def disconnect(self):
        """Gracefully disconnect from MQTT broker."""
        if self._client:
            # Publish offline status before disconnecting
            await self.publish_state("binary_sensor/connected", "OFF")
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
            self._connected.clear()
            logger.info("Disconnected from MQTT broker")

    def _discovery_topic(self, component: str, object_id: str) -> str:
        """Generate MQTT discovery topic.

        Args:
            component: HA component type (switch, sensor, etc.)
            object_id: Unique object identifier

        Returns:
            Discovery topic string
        """
        return f"homeassistant/{component}/{self.NODE_ID}/{object_id}/config"

    def _state_topic(self, component: str, object_id: str) -> str:
        """Generate state topic.

        Args:
            component: HA component type
            object_id: Object identifier

        Returns:
            State topic string
        """
        return f"{self.NODE_ID}/{component}/{object_id}/state"

    def _command_topic(self, component: str, object_id: str) -> str:
        """Generate command topic.

        Args:
            component: HA component type
            object_id: Object identifier

        Returns:
            Command topic string
        """
        return f"{self.NODE_ID}/{component}/{object_id}/set"

    async def _publish(self, topic: str, payload: Any, retain: bool = True):
        """Publish message to MQTT.

        Args:
            topic: MQTT topic
            payload: Message payload (will be JSON encoded if dict)
            retain: Whether to retain message
        """
        if not self._client or not self._connected.is_set():
            logger.warning("Cannot publish: not connected to MQTT")
            return

        if isinstance(payload, dict):
            payload = json.dumps(payload)
        elif not isinstance(payload, str):
            payload = str(payload)

        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._client.publish(topic, payload, retain=retain)
        )

    async def register_entities(self):
        """Register all 16 entities via MQTT discovery."""
        entities = self._get_entity_configs()

        for component, object_id, config in entities:
            topic = self._discovery_topic(component, object_id)
            await self._publish(topic, config)
            logger.debug(f"Registered entity: {component}/{object_id}")

        # Register events
        await self._register_events()

        logger.info(f"Registered {len(entities)} entities and 2 events")

    def _get_entity_configs(self) -> list:
        """Get all entity configurations.

        Returns:
            List of (component, object_id, config) tuples
        """
        entities = []

        # 1. image.watcher_snapshot — Last camera frame
        entities.append(
            (
                "image",
                "snapshot",
                {
                    "name": "Watcher Snapshot",
                    "unique_id": "sensecap_watcher_snapshot",
                    "image_topic": f"{self.NODE_ID}/image/snapshot/image",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 2. switch.watcher_monitoring — Main monitoring toggle
        entities.append(
            (
                "switch",
                "monitoring",
                {
                    "name": "Watcher Monitoring",
                    "unique_id": "sensecap_watcher_monitoring",
                    "state_topic": self._state_topic("switch", "monitoring"),
                    "command_topic": self._command_topic("switch", "monitoring"),
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 3. sensor.watcher_last_event — AI event text
        entities.append(
            (
                "sensor",
                "last_event",
                {
                    "name": "Watcher Last Event",
                    "unique_id": "sensecap_watcher_last_event",
                    "state_topic": self._state_topic("sensor", "last_event"),
                    "icon": "mdi:message-text",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 4. text.watcher_custom_prompt — Custom AI prompt
        entities.append(
            (
                "text",
                "custom_prompt",
                {
                    "name": "Watcher Custom Prompt",
                    "unique_id": "sensecap_watcher_custom_prompt",
                    "state_topic": self._state_topic("text", "custom_prompt"),
                    "command_topic": self._command_topic("text", "custom_prompt"),
                    "mode": "text",
                    "max": 500,
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 5. button.watcher_analyze_scene — Manual Vision AI trigger
        entities.append(
            (
                "button",
                "analyze_scene",
                {
                    "name": "Watcher Analyze Scene",
                    "unique_id": "sensecap_watcher_analyze_scene",
                    "command_topic": self._command_topic("button", "analyze_scene"),
                    "payload_press": "PRESS",
                    "icon": "mdi:eye",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 6. binary_sensor.watcher_motion_detected — Local motion detection
        entities.append(
            (
                "binary_sensor",
                "motion_detected",
                {
                    "name": "Watcher Motion Detected",
                    "unique_id": "sensecap_watcher_motion_detected",
                    "state_topic": self._state_topic(
                        "binary_sensor", "motion_detected"
                    ),
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "device_class": "motion",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 7. number.watcher_monitoring_interval — Polling interval (10-300)
        entities.append(
            (
                "number",
                "monitoring_interval",
                {
                    "name": "Watcher Monitoring Interval",
                    "unique_id": "sensecap_watcher_monitoring_interval",
                    "state_topic": self._state_topic("number", "monitoring_interval"),
                    "command_topic": self._command_topic(
                        "number", "monitoring_interval"
                    ),
                    "min": 10,
                    "max": 300,
                    "step": 1,
                    "unit_of_measurement": "s",
                    "icon": "mdi:timer",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 8. number.watcher_confidence_threshold — AI confidence (0-100)
        entities.append(
            (
                "number",
                "confidence_threshold",
                {
                    "name": "Watcher Confidence Threshold",
                    "unique_id": "sensecap_watcher_confidence_threshold",
                    "state_topic": self._state_topic("number", "confidence_threshold"),
                    "command_topic": self._command_topic(
                        "number", "confidence_threshold"
                    ),
                    "min": 0,
                    "max": 100,
                    "step": 1,
                    "unit_of_measurement": "%",
                    "icon": "mdi:percent",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 9. switch.watcher_voice_assistant — Voice assistant toggle
        entities.append(
            (
                "switch",
                "voice_assistant",
                {
                    "name": "Watcher Voice Assistant",
                    "unique_id": "sensecap_watcher_voice_assistant",
                    "state_topic": self._state_topic("switch", "voice_assistant"),
                    "command_topic": self._command_topic("switch", "voice_assistant"),
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "icon": "mdi:microphone",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 10. tts.watcher — Text-to-speech (using notify platform)
        entities.append(
            (
                "notify",
                "tts",
                {
                    "name": "Watcher TTS",
                    "unique_id": "sensecap_watcher_tts",
                    "command_topic": self._command_topic("notify", "tts"),
                    "icon": "mdi:text-to-speech",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 11. siren.watcher — Alarm/siren
        entities.append(
            (
                "siren",
                "alarm",
                {
                    "name": "Watcher Siren",
                    "unique_id": "sensecap_watcher_siren",
                    "state_topic": self._state_topic("siren", "alarm"),
                    "command_topic": self._command_topic("siren", "alarm"),
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "available_tones": ["alarm", "alert", "chime"],
                    "support_duration": True,
                    "support_volume_set": True,
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 12. binary_sensor.watcher_noise_detected — Noise detection
        entities.append(
            (
                "binary_sensor",
                "noise_detected",
                {
                    "name": "Watcher Noise Detected",
                    "unique_id": "sensecap_watcher_noise_detected",
                    "state_topic": self._state_topic("binary_sensor", "noise_detected"),
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "device_class": "sound",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 13. select.watcher_display_mode — Display mode
        entities.append(
            (
                "select",
                "display_mode",
                {
                    "name": "Watcher Display Mode",
                    "unique_id": "sensecap_watcher_display_mode",
                    "state_topic": self._state_topic("select", "display_mode"),
                    "command_topic": self._command_topic("select", "display_mode"),
                    "options": ["Clock", "Weather", "Status", "AI Log", "Custom"],
                    "icon": "mdi:monitor",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 14. text.watcher_display_message — Display message
        entities.append(
            (
                "text",
                "display_message",
                {
                    "name": "Watcher Display Message",
                    "unique_id": "sensecap_watcher_display_message",
                    "state_topic": self._state_topic("text", "display_message"),
                    "command_topic": self._command_topic("text", "display_message"),
                    "mode": "text",
                    "max": 100,
                    "icon": "mdi:message-text-outline",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 15. switch.watcher_display_power — Display on/off
        entities.append(
            (
                "switch",
                "display_power",
                {
                    "name": "Watcher Display Power",
                    "unique_id": "sensecap_watcher_display_power",
                    "state_topic": self._state_topic("switch", "display_power"),
                    "command_topic": self._command_topic("switch", "display_power"),
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "icon": "mdi:monitor-shimmer",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        # 16. binary_sensor.watcher_connected — Device online status
        entities.append(
            (
                "binary_sensor",
                "connected",
                {
                    "name": "Watcher Connected",
                    "unique_id": "sensecap_watcher_connected",
                    "state_topic": self._state_topic("binary_sensor", "connected"),
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "device_class": "connectivity",
                    "device": self.DEVICE_INFO,
                },
            )
        )

        return entities

    async def _register_events(self):
        """Register event entities for HA."""
        # Event 1: sensecap_watcher_alert
        alert_config = {
            "name": "Watcher Alert",
            "unique_id": "sensecap_watcher_alert",
            "state_topic": f"{self.NODE_ID}/event/alert/state",
            "event_types": ["alert"],
            "device": self.DEVICE_INFO,
        }
        await self._publish(
            f"homeassistant/event/{self.NODE_ID}_alert/config",
            alert_config,
        )

        # Event 2: sensecap_watcher_voice_command
        voice_config = {
            "name": "Watcher Voice Command",
            "unique_id": "sensecap_watcher_voice_command",
            "state_topic": f"{self.NODE_ID}/event/voice_command/state",
            "event_types": ["voice_command"],
            "device": self.DEVICE_INFO,
        }
        await self._publish(
            f"homeassistant/event/{self.NODE_ID}_voice_command/config",
            voice_config,
        )

    async def publish_state(self, entity_id: str, state: Any):
        """Publish state update for an entity.

        Args:
            entity_id: Entity identifier in format "component/object_id"
            state: State value to publish
        """
        if "/" in entity_id:
            component, object_id = entity_id.split("/", 1)
            topic = self._state_topic(component, object_id)
        else:
            topic = f"{self.NODE_ID}/{entity_id}/state"

        await self._publish(topic, state)
        logger.debug(f"Published state for {entity_id}: {state}")

    async def publish_initial_states(self):
        """Publish initial default states for all entities."""
        initial_states = {
            # Switches default OFF
            "switch/monitoring": "OFF",
            "switch/voice_assistant": "OFF",
            "switch/display_power": "ON",
            # Binary sensors default OFF
            "binary_sensor/connected": "OFF",
            "binary_sensor/motion_detected": "OFF",
            "binary_sensor/noise_detected": "OFF",
            # Sensors default empty/zero
            "sensor/last_event": "",
            # Numbers default values
            "number/monitoring_interval": "30",
            "number/confidence_threshold": "50",
            # Text fields default empty
            "text/custom_prompt": "",
            "text/display_message": "",
            # Select default
            "select/display_mode": "Clock",
            # Siren default OFF
            "siren/alarm": "OFF",
        }

        for entity_id, state in initial_states.items():
            await self.publish_state(entity_id, state)

        logger.info(f"Published initial states for {len(initial_states)} entities")

    async def fire_event(self, event_type: str, data: dict):
        """Fire a Home Assistant event via MQTT.

        Args:
            event_type: Event type (alert, voice_command)
            data: Event data dictionary
        """
        topic = f"{self.NODE_ID}/event/{event_type}/state"
        payload = {
            "event_type": event_type,
            **data,
        }
        await self._publish(topic, payload, retain=False)
        logger.info(f"Fired event {event_type}: {data}")

    async def subscribe_commands(self, callback):
        """Subscribe to command topics.

        Args:
            callback: Async callback function(topic, payload)
        """
        if not self._client:
            logger.warning("Cannot subscribe: not connected")
            return

        def on_message(client, userdata, msg):
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    callback(msg.topic, msg.payload.decode()), self._loop
                )

        self._client.on_message = on_message
        self._client.subscribe(f"{self.NODE_ID}/+/+/set")
        logger.info("Subscribed to command topics")
