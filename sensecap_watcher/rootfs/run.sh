#!/usr/bin/with-contenv bash

echo "Starting SenseCAP Watcher AI..."

# with-contenv injects SUPERVISOR_TOKEN from s6-overlay
echo "DEBUG: SUPERVISOR_TOKEN length = ${#SUPERVISOR_TOKEN}"

# Get MQTT credentials from Supervisor API
if [ -n "${SUPERVISOR_TOKEN}" ]; then
    echo "Fetching MQTT config from Supervisor..."
    MQTT_INFO=$(curl -s -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" http://supervisor/services/mqtt 2>/dev/null)
    echo "DEBUG MQTT_INFO: ${MQTT_INFO}"

    MQTT_PARSED=$(echo "${MQTT_INFO}" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin).get('data', {})
    print(data.get('host', 'core-mosquitto'))
    print(data.get('port', 1883))
    print(data.get('username', ''))
    print(data.get('password', ''))
except:
    print('core-mosquitto')
    print('1883')
    print('')
    print('')
" 2>/dev/null)

    export MQTT_HOST=$(echo "${MQTT_PARSED}" | sed -n '1p')
    export MQTT_PORT=$(echo "${MQTT_PARSED}" | sed -n '2p')
    export MQTT_USER=$(echo "${MQTT_PARSED}" | sed -n '3p')
    export MQTT_PASSWORD=$(echo "${MQTT_PARSED}" | sed -n '4p')
    echo "MQTT config loaded: host=${MQTT_HOST} port=${MQTT_PORT} user=${MQTT_USER}"
else
    echo "WARNING: No SUPERVISOR_TOKEN, using defaults"
    export MQTT_HOST="core-mosquitto"
    export MQTT_PORT="1883"
    export MQTT_USER=""
    export MQTT_PASSWORD=""
fi

echo "MQTT: ${MQTT_HOST}:${MQTT_PORT} (user: ${MQTT_USER})"

exec python3 /app/main.py
