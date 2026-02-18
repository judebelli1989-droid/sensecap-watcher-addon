#!/usr/bin/with-contenv bashio

export MQTT_HOST=$(bashio::services mqtt "host")
export MQTT_PORT=$(bashio::services mqtt "port")
export MQTT_USER=$(bashio::services mqtt "username")
export MQTT_PASSWORD=$(bashio::services mqtt "password")
export SUPERVISOR_TOKEN=${SUPERVISOR_TOKEN}

bashio::log.info "Starting SenseCAP Watcher AI..."

exec python3 /app/main.py
