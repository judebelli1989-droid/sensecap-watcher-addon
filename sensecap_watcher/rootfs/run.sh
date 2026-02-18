#!/usr/bin/with-contenv bashio

# Fetch MQTT credentials from HA Supervisor via bashio
if bashio::services.available "mqtt"; then
    export MQTT_HOST="$(bashio::services mqtt "host")"
    export MQTT_PORT="$(bashio::services mqtt "port")"
    export MQTT_USER="$(bashio::services mqtt "username")"
    export MQTT_PASSWORD="$(bashio::services mqtt "password")"
    bashio::log.info "MQTT from Supervisor: ${MQTT_HOST}:${MQTT_PORT} (user: ${MQTT_USER})"
else
    bashio::log.warning "MQTT service not available, using defaults"
    export MQTT_HOST="core-mosquitto"
    export MQTT_PORT="1883"
    export MQTT_USER=""
    export MQTT_PASSWORD=""
fi

# Pass SUPERVISOR_TOKEN explicitly
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN}"

exec python3 /app/main.py
