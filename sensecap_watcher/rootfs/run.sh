#!/usr/bin/with-contenv bash

# Write debug to file and stdout
exec 2>&1

echo "[run.sh] Starting SenseCAP Watcher AI..."
echo "[run.sh] SUPERVISOR_TOKEN length = ${#SUPERVISOR_TOKEN}"

# Get MQTT credentials from Supervisor API
if [ -n "${SUPERVISOR_TOKEN}" ]; then
    echo "[run.sh] Fetching MQTT config from Supervisor..."
    MQTT_INFO=$(curl -s -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" http://supervisor/services/mqtt)
    echo "[run.sh] MQTT_INFO response: ${MQTT_INFO}"

    # Parse JSON in single python3 call
    eval $(echo "${MQTT_INFO}" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin).get('data', {})
    print(f'export MQTT_HOST=\"{data.get(\"host\", \"core-mosquitto\")}\"')
    print(f'export MQTT_PORT=\"{data.get(\"port\", 1883)}\"')
    print(f'export MQTT_USER=\"{data.get(\"username\", \"\")}\"')
    print(f'export MQTT_PASSWORD=\"{data.get(\"password\", \"\")}\"')
except Exception as e:
    print(f'export MQTT_HOST=\"core-mosquitto\"')
    print(f'export MQTT_PORT=\"1883\"')
    print(f'export MQTT_USER=\"\"')
    print(f'export MQTT_PASSWORD=\"\"')
    print(f'echo \"[run.sh] JSON parse error: {e}\"', file=sys.stderr)
")
    echo "[run.sh] MQTT parsed: host=${MQTT_HOST} port=${MQTT_PORT} user=${MQTT_USER}"
else
    echo "[run.sh] WARNING: No SUPERVISOR_TOKEN, using defaults"
    export MQTT_HOST="core-mosquitto"
    export MQTT_PORT="1883"
    export MQTT_USER=""
    export MQTT_PASSWORD=""
fi

export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN}"
echo "[run.sh] Starting Python with MQTT: ${MQTT_HOST}:${MQTT_PORT} user=${MQTT_USER}"

exec python3 /app/main.py
