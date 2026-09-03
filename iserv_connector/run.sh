#!/usr/bin/env sh
set -e

if [ -f /data/options.json ]; then
  ISERV_PASSPHRASE="$(python -c 'import json;print(json.load(open("/data/options.json")).get("passphrase",""))' 2>/dev/null || true)"
  export ISERV_PASSPHRASE

  ISERV_MQTT_HOST="$(python -c 'import json;print(json.load(open("/data/options.json")).get("mqtt_host",""))' 2>/dev/null || true)"
  if [ -n "$ISERV_MQTT_HOST" ]; then
    export ISERV_MQTT_HOST
    ISERV_MQTT_PORT="$(python -c 'import json;print(json.load(open("/data/options.json")).get("mqtt_port",1883))' 2>/dev/null || true)"
    ISERV_MQTT_USER="$(python -c 'import json;print(json.load(open("/data/options.json")).get("mqtt_user",""))' 2>/dev/null || true)"
    ISERV_MQTT_PASSWORD="$(python -c 'import json;print(json.load(open("/data/options.json")).get("mqtt_password",""))' 2>/dev/null || true)"
    export ISERV_MQTT_PORT ISERV_MQTT_USER ISERV_MQTT_PASSWORD
  fi
fi

export ISERV_ENABLE_POLLER="${ISERV_ENABLE_POLLER:-1}"
export ISERV_ENABLE_CALENDAR="${ISERV_ENABLE_CALENDAR:-1}"
export ISERV_CALENDAR_PORT="${ISERV_CALENDAR_PORT:-8100}"
exec uvicorn app.main:app --host 0.0.0.0 --port 8099
