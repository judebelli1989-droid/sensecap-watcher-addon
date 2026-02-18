#!/bin/bash
set -e

echo "Starting SenseCAP Watcher AI..."

# Get MQTT credentials from Supervisor API (no bashio dependency)
if [ -n "${SUPERVISOR_TOKEN}" ]; then
    MQTT_INFO=$(curl -s -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" http://supervisor/services/mqtt 2>/dev/null || echo '{}')
    export MQTT_HOST=$(echo "${MQTT_INFO}" | python3 -c "import sys,json; d=json.load(sys.stdin).get('data',{}); print(d.get('host','localhost'))" 2>/dev/null || echo "localhost")
    export MQTT_PORT=$(echo "${MQTT_INFO}" | python3 -c "import sys,json; d=json.load(sys.stdin).get('data',{}); print(d.get('port','1883'))" 2>/dev/null || echo "1883")
    export MQTT_USER=$(echo "${MQTT_INFO}" | python3 -c "import sys,json; d=json.load(sys.stdin).get('data',{}); print(d.get('username',''))" 2>/dev/null || echo "")
    export MQTT_PASSWORD=$(echo "${MQTT_INFO}" | python3 -c "import sys,json; d=json.load(sys.stdin).get('data',{}); print(d.get('password',''))" 2>/dev/null || echo "")
else
    export MQTT_HOST="localhost"
    export MQTT_PORT="1883"
    export MQTT_USER=""
    export MQTT_PASSWORD=""
fi

echo "MQTT: ${MQTT_HOST}:${MQTT_PORT}"

exec python3 /app/main.py
