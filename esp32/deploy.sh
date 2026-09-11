#!/bin/bash
# Deploy MorseBox Mini su ESP32 con MicroPython via mpremote.
# Uso:  bash deploy.sh [porta]      (default: auto)
set -e
cd "$(dirname "$0")"
PORT="${1:-}"

MP="mpremote"
if [ -n "$PORT" ]; then
  MP="mpremote connect $PORT"
fi

if ! command -v mpremote >/dev/null 2>&1; then
  echo "mpremote non trovato. Installa con:  pip install mpremote"
  exit 1
fi

echo "[1/3] Copio i moduli Python…"
for f in config.py settings.py morse.py gpio.py sidetone.py \
         hub.py wsproto.py keyer.py webserver.py display.py \
         wifi_ap.py main.py; do
  echo "  -> $f"
  $MP fs cp "$f" ":$f"
done

echo "[2/3] Copio la web UI in /static…"
$MP fs mkdir :static 2>/dev/null || true
for f in index.html style.css app.js; do
  echo "  -> static/$f"
  $MP fs cp "static/$f" ":static/$f"
done

echo "[3/3] Reset ESP32…"
$MP reset
echo "Fatto. Cerca la Wi-Fi IU2VWK-MORSE (morse1234) e apri http://10.42.0.1"
