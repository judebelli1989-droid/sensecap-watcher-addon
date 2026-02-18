#!/bin/bash
set -e

# Source bashio if available
if [ -f /usr/lib/bashio/bashio.sh ]; then
    source /usr/lib/bashio/bashio.sh
fi

# Get MQTT credentials from HA services
export MQTT_HOST=$(bashio::services mqtt "host" 2>/dev/null || echo "localhost")
export MQTT_PORT=$(bashio::services mqtt "port" 2>/dev/null || echo "1883")
export MQTT_USER=$(bashio::services mqtt "username" 2>/dev/null || echo "")
export MQTT_PASSWORD=$(bashio::services mqtt "password" 2>/dev/null || echo "")
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN}"

bashio::log.info "Starting SenseCAP Watcher AI..." 2>/dev/null || echo "Starting SenseCAP Watcher AI..."

exec python3 /app/main.py
