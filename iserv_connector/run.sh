#!/usr/bin/env sh
set -e

if [ -f /data/options.json ]; then
  ISERV_PASSPHRASE="$(python -c 'import json;print(json.load(open("/data/options.json")).get("passphrase",""))' 2>/dev/null || true)"
  export ISERV_PASSPHRASE
fi

export ISERV_ENABLE_POLLER="${ISERV_ENABLE_POLLER:-1}"
export ISERV_ENABLE_CALENDAR="${ISERV_ENABLE_CALENDAR:-1}"
export ISERV_CALENDAR_PORT="${ISERV_CALENDAR_PORT:-8100}"
exec uvicorn app.main:app --host 0.0.0.0 --port 8099
