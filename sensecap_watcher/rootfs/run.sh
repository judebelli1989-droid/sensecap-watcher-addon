#!/bin/bash

echo "Starting SenseCAP Watcher AI..."

# Get MQTT credentials from Supervisor API
if [ -n "${SUPERVISOR_TOKEN}" ]; then
    echo "SUPERVISOR_TOKEN found, fetching MQTT config..."
    MQTT_INFO=$(curl -s -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" http://supervisor/services/mqtt 2>/dev/null)
    
    if echo "${MQTT_INFO}" | python3 -c "import sys,json; json.load(sys.stdin)['data']" >/dev/null 2>&1; then
        export MQTT_HOST=$(echo "${MQTT_INFO}" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['host'])")
        export MQTT_PORT=$(echo "${MQTT_INFO}" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['port'])")
        export MQTT_USER=$(echo "${MQTT_INFO}" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['username'])")
        export MQTT_PASSWORD=$(echo "${MQTT_INFO}" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['password'])")
        echo "MQTT config loaded from Supervisor"
    else
        echo "WARNING: Failed to parse MQTT config, using defaults"
        export MQTT_HOST="core-mosquitto"
        export MQTT_PORT="1883"
        export MQTT_USER=""
        export MQTT_PASSWORD=""
    fi
else
    echo "WARNING: No SUPERVISOR_TOKEN, using defaults"
    export MQTT_HOST="core-mosquitto"
    export MQTT_PORT="1883"
    export MQTT_USER=""
    export MQTT_PASSWORD=""
fi

echo "MQTT: ${MQTT_HOST}:${MQTT_PORT} (user: ${MQTT_USER})"

exec python3 /app/main.py
