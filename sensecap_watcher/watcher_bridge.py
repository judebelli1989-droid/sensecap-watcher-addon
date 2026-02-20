#!/usr/bin/env python3
"""
SenseCAP Watcher → Home Assistant MQTT Bridge

Connects to the device's local WebSocket, listens for detection events
and MCP tool responses, and publishes them as HA entities via MQTT Discovery.

Entities created:
  - binary_sensor.watcher_motion    — object detected (on/off)
  - sensor.watcher_detection        — last detection details (target, count)
  - sensor.watcher_analysis         — AI scene analysis text
  - camera.watcher_snapshot         — camera image (JPEG via MQTT)
  - switch.watcher_model            — enable/disable vision model
  - number.watcher_threshold        — detection confidence threshold
  - button.watcher_snapshot         — take a photo on demand

Usage:
  pip install websockets paho-mqtt
  python3 watcher_bridge.py
"""

import asyncio
import base64
import json
import logging
import os
import signal
import time

import paho.mqtt.client as mqtt
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("watcher_bridge")

# --- Config ---
DEVICE_WS = os.environ.get("WATCHER_WS", "ws://localhost:8080/ws")
MQTT_HOST = os.environ.get("MQTT_HOST", "core-mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASS", "")
DEVICE_ID = "sensecap_watcher"
DEVICE_NAME = "SenseCAP Watcher"

# MQTT topics
PREFIX = f"homeassistant"
STATE_TOPIC = f"watcher/{DEVICE_ID}"
CMD_TOPIC = f"watcher/{DEVICE_ID}/cmd"

# HA device block (shared across all entities)
HA_DEVICE = {
    "identifiers": [DEVICE_ID],
    "name": DEVICE_NAME,
    "manufacturer": "Seeed Studio",
    "model": "SenseCAP Watcher",
}

ANALYSIS_QUESTION = os.environ.get(
    "WATCHER_ANALYSIS_PROMPT",
    "Describe what you see in the image. If you see people or unusual activity, report it.",
)

GREETING_PROMPT = os.environ.get(
    "WATCHER_GREETING_PROMPT",
    "Ты камера-охранник у входа. Ты только что обнаружила человека. "
    "Поприветствуй его коротко и дружелюбно, спроси чем можешь помочь. "
    "Отвечай на русском, кратко — максимум 2 предложения.",
)


class WatcherBridge:
    def __init__(self):
        self.ws = None
        self.mqttc = mqtt.Client(client_id="watcher_bridge")
        self.rpc_id = 100
        self.pending = {}  # rpc_id -> asyncio.Future
        self.model_enabled = False
        self.motion_on = False
        self.last_target = ""
        self.loop = None
        self._snapshot_lock = asyncio.Lock()

    # --- MQTT setup ---
    def mqtt_connect(self):
        if MQTT_USER:
            self.mqttc.username_pw_set(MQTT_USER, MQTT_PASS)
        self.mqttc.on_connect = self._on_mqtt_connect
        self.mqttc.on_message = self._on_mqtt_message
        self.mqttc.will_set(f"{STATE_TOPIC}/available", "offline", retain=True)
        self.mqttc.connect(MQTT_HOST, MQTT_PORT)
        self.mqttc.loop_start()

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        log.info(f"MQTT connected (rc={rc})")
        self._publish_discovery()
        client.subscribe(f"{CMD_TOPIC}/#")
        client.publish(f"{STATE_TOPIC}/available", "online", retain=True)

    def _on_mqtt_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()
        log.info(f"MQTT cmd: {topic} = {payload}")
        if topic == f"{CMD_TOPIC}/model_switch":
            enable = 1 if payload == "ON" else 0
            if self.loop:
                asyncio.run_coroutine_threadsafe(self._call_tool("self.model.enable", {"enable": enable}), self.loop)
        elif topic == f"{CMD_TOPIC}/threshold":
            try:
                val = int(float(payload))
                if self.loop:
                    asyncio.run_coroutine_threadsafe(self._call_tool("self.model.param_set", {"threshold": val}), self.loop)
            except ValueError:
                pass
        elif topic == f"{CMD_TOPIC}/snapshot":
            if self.loop:
                asyncio.run_coroutine_threadsafe(self._snapshot_and_analyze(), self.loop)

    # --- PLACEHOLDER_DISCOVERY ---

    def _publish_discovery(self):
        entities = [
            {
                "component": "binary_sensor",
                "object_id": "watcher_motion",
                "config": {
                    "name": "Motion",
                    "device_class": "motion",
                    "state_topic": f"{STATE_TOPIC}/motion",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "availability_topic": f"{STATE_TOPIC}/available",
                },
            },
            {
                "component": "sensor",
                "object_id": "watcher_detection",
                "config": {
                    "name": "Last Detection",
                    "icon": "mdi:eye",
                    "state_topic": f"{STATE_TOPIC}/detection",
                    "value_template": "{{ value_json.target }}",
                    "json_attributes_topic": f"{STATE_TOPIC}/detection",
                    "availability_topic": f"{STATE_TOPIC}/available",
                },
            },
            {
                "component": "switch",
                "object_id": "watcher_model",
                "config": {
                    "name": "Vision Model",
                    "icon": "mdi:eye-outline",
                    "state_topic": f"{STATE_TOPIC}/model_state",
                    "command_topic": f"{CMD_TOPIC}/model_switch",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "availability_topic": f"{STATE_TOPIC}/available",
                },
            },
            {
                "component": "number",
                "object_id": "watcher_threshold",
                "config": {
                    "name": "Detection Threshold",
                    "icon": "mdi:tune",
                    "state_topic": f"{STATE_TOPIC}/threshold",
                    "command_topic": f"{CMD_TOPIC}/threshold",
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "unit_of_measurement": "%",
                    "availability_topic": f"{STATE_TOPIC}/available",
                },
            },
            {
                "component": "button",
                "object_id": "watcher_snapshot",
                "config": {
                    "name": "Take Snapshot",
                    "icon": "mdi:camera",
                    "command_topic": f"{CMD_TOPIC}/snapshot",
                    "availability_topic": f"{STATE_TOPIC}/available",
                },
            },
            {
                "component": "camera",
                "object_id": "watcher_camera",
                "config": {
                    "name": "Camera",
                    "topic": f"{STATE_TOPIC}/camera/image",
                    "image_encoding": "b64",
                    "availability_topic": f"{STATE_TOPIC}/available",
                },
            },
            {
                "component": "sensor",
                "object_id": "watcher_analysis",
                "config": {
                    "name": "Scene Analysis",
                    "icon": "mdi:brain",
                    "state_topic": f"{STATE_TOPIC}/analysis",
                    "value_template": "{{ value_json.summary[:250] }}",
                    "json_attributes_topic": f"{STATE_TOPIC}/analysis",
                    "availability_topic": f"{STATE_TOPIC}/available",
                },
            },
        ]
        for e in entities:
            topic = f"{PREFIX}/{e['component']}/{DEVICE_ID}/{e['object_id']}/config"
            cfg = {**e["config"], "unique_id": e["object_id"], "device": HA_DEVICE}
            self.mqttc.publish(topic, json.dumps(cfg), retain=True)
            log.info(f"Discovery: {e['component']}/{e['object_id']}")

    # --- PLACEHOLDER_WS ---

    async def _call_tool(self, name, arguments, timeout=10):
        if not self.ws:
            return None
        self.rpc_id += 1
        rid = self.rpc_id
        msg = {"jsonrpc": "2.0", "id": rid, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
        fut = self.loop.create_future()
        self.pending[rid] = fut
        await self.ws.send(json.dumps(msg))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self.pending.pop(rid, None)
            log.warning(f"Tool call timeout: {name}")
            return None

    def _handle_detection_event(self, data):
        event = data.get("event", "")
        if event == "object_appeared":
            self.motion_on = True
            self.last_target = data.get("target", "unknown")
            self.mqttc.publish(f"{STATE_TOPIC}/motion", "ON", retain=True)
            det = {"target": self.last_target, "count": data.get("count", 0),
                   "event": event, "time": time.strftime("%H:%M:%S")}
            self.mqttc.publish(f"{STATE_TOPIC}/detection", json.dumps(det), retain=True)
            log.info(f"Motion ON: {self.last_target}")
        elif event == "object_left":
            self.motion_on = False
            self.mqttc.publish(f"{STATE_TOPIC}/motion", "OFF", retain=True)
            log.info("Motion OFF")
        elif event == "triggered":
            det = {"target": data.get("target", "unknown"), "count": data.get("count", 0),
                   "event": "triggered", "model_type": data.get("model_type", 0),
                   "time": time.strftime("%H:%M:%S")}
            self.mqttc.publish(f"{STATE_TOPIC}/detection", json.dumps(det), retain=True)
            log.info(f"Detection triggered: {det['target']} — snapshot + analysis + greeting")
            if self.loop:
                asyncio.ensure_future(self._on_detection_triggered())
        elif event == "cooldown_complete":
            self.motion_on = False
            self.mqttc.publish(f"{STATE_TOPIC}/motion", "OFF", retain=True)
            log.info("Cooldown complete, motion OFF")

    def _handle_rpc_response(self, data):
        rid = data.get("id")
        if rid and rid in self.pending:
            self.pending.pop(rid).set_result(data)

    async def _take_snapshot(self):
        """Call self.camera.snapshot and publish JPEG to MQTT camera topic."""
        r = await self._call_tool("self.camera.snapshot", {})
        if not r or "result" not in r:
            log.warning("Snapshot failed: no response")
            return None
        try:
            content = r["result"]["content"][0]
            img_json = json.loads(content["image"])
            b64_data = img_json["data"]
            # Publish base64 JPEG to camera image topic
            self.mqttc.publish(f"{STATE_TOPIC}/camera/image", b64_data)
            jpeg_bytes = base64.b64decode(b64_data)
            log.info(f"Snapshot published: {len(jpeg_bytes)} bytes")
            return b64_data
        except (KeyError, json.JSONDecodeError, IndexError) as e:
            log.warning(f"Snapshot parse error: {e}")
            return None

    async def _analyze_scene(self, question=None):
        """Call self.camera.take_photo (Vision AI) and publish analysis."""
        q = question or ANALYSIS_QUESTION
        r = await self._call_tool("self.camera.take_photo", {"question": q}, timeout=30)
        if not r or "result" not in r:
            log.warning("Analysis failed: no response")
            return None
        try:
            raw_text = r["result"]["content"][0]["text"]
            # take_photo returns JSON: {"success":true,"filename":"...","text":"AI description"}
            inner = json.loads(raw_text)
            if not inner.get("success"):
                log.warning(f"Analysis failed on device: {raw_text[:200]}")
                return None
            description = inner.get("text", "")
            analysis = {"summary": description, "question": q,
                        "filename": inner.get("filename", ""),
                        "time": time.strftime("%H:%M:%S")}
            self.mqttc.publish(f"{STATE_TOPIC}/analysis",
                               json.dumps(analysis), retain=True)
            log.info(f"Analysis: {description[:100]}")
            return description
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            log.warning(f"Analysis parse error: {e}")
            return None

    async def _snapshot_and_analyze(self):
        """Take snapshot + AI analysis. Used on detection trigger and button press."""
        async with self._snapshot_lock:
            await self._take_snapshot()
            await self._analyze_scene()

    async def _greet_voice(self, prompt=None):
        """Send text to cloud AI — device will speak the response via TTS."""
        text = prompt or GREETING_PROMPT
        r = await self._call_tool("self.chat.send_text", {"text": text}, timeout=5)
        if r and "result" in r:
            log.info(f"Greeting sent to AI: {text[:80]}")
        else:
            log.warning("Greeting failed")

    async def _on_detection_triggered(self):
        """Full detection flow: greeting + snapshot + analysis."""
        await self._greet_voice()
        await self._snapshot_and_analyze()

    async def _sync_state(self):
        """Fetch current model state and publish to MQTT."""
        r = await self._call_tool("self.model.enable", {})
        if r and "result" in r:
            text = r["result"]["content"][0]["text"]
            state = json.loads(text)
            self.model_enabled = state.get("enable", 0) == 1
            self.mqttc.publish(f"{STATE_TOPIC}/model_state",
                               "ON" if self.model_enabled else "OFF", retain=True)

        r2 = await self._call_tool("self.model.param_get", {})
        if r2 and "result" in r2:
            text = r2["result"]["content"][0]["text"]
            params = json.loads(text)
            self.mqttc.publish(f"{STATE_TOPIC}/threshold",
                               str(params.get("threshold", 75)), retain=True)

    async def run(self):
        self.loop = asyncio.get_event_loop()
        log.info("Starting MQTT connection...")
        self.mqtt_connect()
        log.info("MQTT loop started, entering WebSocket loop...")

        while True:
            try:
                log.info(f"Connecting to {DEVICE_WS}")
                async with websockets.connect(DEVICE_WS, open_timeout=10,
                                              ping_interval=20, ping_timeout=10) as ws:
                    self.ws = ws
                    log.info("WebSocket connected")
                    self.mqttc.publish(f"{STATE_TOPIC}/available", "online", retain=True)
                    self.mqttc.publish(f"{STATE_TOPIC}/motion", "OFF", retain=True)

                    # Run sync and message loop concurrently
                    async def read_loop():
                        async for raw in ws:
                            try:
                                data = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            if data.get("type") == "detection":
                                self._handle_detection_event(data)
                            elif "jsonrpc" in data:
                                self._handle_rpc_response(data)

                    async def delayed_sync():
                        await asyncio.sleep(1)
                        await self._sync_state()

                    await asyncio.gather(read_loop(), delayed_sync())

            except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
                log.warning(f"Connection lost: {e}, reconnecting in 5s")
                self.ws = None
                self.mqttc.publish(f"{STATE_TOPIC}/available", "offline", retain=True)
                await asyncio.sleep(5)


def main():
    log.info("=== WatcherBridge starting ===")
    log.info(f"Config: DEVICE_WS={DEVICE_WS} MQTT_HOST={MQTT_HOST}:{MQTT_PORT} USER={MQTT_USER}")
    bridge = WatcherBridge()
    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, loop.stop)
    try:
        loop.run_until_complete(bridge.run())
    except KeyboardInterrupt:
        pass
    finally:
        bridge.mqttc.publish(f"{STATE_TOPIC}/available", "offline", retain=True)
        bridge.mqttc.disconnect()


if __name__ == "__main__":
    main()



