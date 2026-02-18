#!/usr/bin/with-contenv bashio

echo "=== DIAG: run.sh started ==="
echo "SUPERVISOR_TOKEN env: ${SUPERVISOR_TOKEN:+SET (${#SUPERVISOR_TOKEN} chars)}"
echo "SUPERVISOR_TOKEN env: ${SUPERVISOR_TOKEN:-NOT SET}"
echo "s6 file /run/s6/container_environment/SUPERVISOR_TOKEN exists: $(test -f /run/s6/container_environment/SUPERVISOR_TOKEN && echo YES || echo NO)"
echo "s6 file /var/run/s6/container_environment/SUPERVISOR_TOKEN exists: $(test -f /var/run/s6/container_environment/SUPERVISOR_TOKEN && echo YES || echo NO)"
ls -la /run/s6/container_environment/ 2>/dev/null || echo "DIR /run/s6/container_environment/ NOT FOUND"
ls -la /var/run/s6/container_environment/ 2>/dev/null || echo "DIR /var/run/s6/container_environment/ NOT FOUND"
echo "=== DIAG: launching python ==="

exec python3 /app/main.py
