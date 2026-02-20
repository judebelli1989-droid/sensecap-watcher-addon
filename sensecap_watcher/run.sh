#!/usr/bin/env bash
set -e

CONFIG=/data/options.json

if [ ! -f "$CONFIG" ]; then
    echo "ERROR: $CONFIG not found!"
    echo "Using defaults from environment..."
else
    echo "Reading config from $CONFIG"
    cat "$CONFIG"
    export WATCHER_WS=$(jq -r '.device_ws' $CONFIG)
    export MQTT_HOST=$(jq -r '.mqtt_host' $CONFIG)
    export MQTT_PORT=$(jq -r '.mqtt_port' $CONFIG)
    export MQTT_USER=$(jq -r '.mqtt_user' $CONFIG)
    export MQTT_PASS=$(jq -r '.mqtt_pass' $CONFIG)
    export WATCHER_GREETING_PROMPT=$(jq -r '.greeting_prompt' $CONFIG)
    export WATCHER_ANALYSIS_PROMPT=$(jq -r '.analysis_prompt' $CONFIG)
fi

echo "Starting SenseCAP Watcher Bridge..."
echo "Device: $WATCHER_WS"
echo "MQTT: $MQTT_HOST:$MQTT_PORT"

exec python3 -u /watcher_bridge.py
