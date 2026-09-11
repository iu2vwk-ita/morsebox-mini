#!/bin/bash
# Deploy MorseBox Mini to an ESP32 with MicroPython via mpremote.
# Usage:  bash deploy.sh [port]      (default: auto)
set -e
cd "$(dirname "$0")"
PORT="${1:-}"

MP="mpremote"
if [ -n "$PORT" ]; then
  MP="mpremote connect $PORT"
fi

if ! command -v mpremote >/dev/null 2>&1; then
  echo "mpremote not found. Install it with:  pip install mpremote"
  exit 1
fi

echo "[1/3] Copying Python modules..."
for f in config.py settings.py morse.py gpio.py sidetone.py \
         hub.py wsproto.py keyer.py webserver.py display.py \
         lcd1602.py wifi_ap.py main.py; do
  echo "  -> $f"
  $MP fs cp "$f" ":$f"
done

echo "[2/3] Copying the web UI to /static..."
$MP fs mkdir :static 2>/dev/null || true
for f in index.html style.css app.js; do
  echo "  -> static/$f"
  $MP fs cp "static/$f" ":static/$f"
done

echo "[3/3] Resetting the ESP32..."
$MP reset
echo "Done. Join the Wi-Fi IU2VWK-MORSE (morse1234) and open http://10.42.0.1"
