#!/bin/bash
# Update the MorseBox Raspberry Pi version from this git repo and restart it.
#   bash update.sh
set -e
cd "$(dirname "$0")"
APP=/opt/iu2vwk-morse

echo "[1/3] git pull..."
git pull --ff-only

echo "[2/3] copy files to $APP..."
mkdir -p "$APP"
cp server.py display.py exercise.py reflex.py easter.py audio.py morse.py "$APP/"
rm -rf "$APP/static"
cp -r static "$APP/"

echo "[3/3] restart service..."
systemctl daemon-reload
systemctl restart iu2vwk-morse
sleep 2
echo "Done. service: $(systemctl is-active iu2vwk-morse)  web: $(curl -s -o /dev/null -w '%{http_code}' -m 5 http://127.0.0.1/)"
