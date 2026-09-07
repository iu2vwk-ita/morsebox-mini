# MorseBox Mini — WiFi CW Trainer

A standalone Morse keyer in a box. A Raspberry Pi 4 serves a web UI over its own
WiFi access point: join the network, open the page, key with a real paddle (or
the on-screen touch paddle) and read live decoded text. Zero-latency sidetone
from one or more piezo buzzers driven straight from the GPIO pins — no audio
pipeline, no lag.

![MorseBox assembled](box.png)

## What it does

- Iambic A / B and straight-key modes, 5–40 WPM, paddle reverse (DX⇄SX)
- Live CW decoding shown on the web page and on the optional MAX7219 LED matrix
- Sidetone with adjustable pitch (400–4000 Hz) and volume, played on up to 3
  piezo buzzers at once (`--buzz-pins 24,25,12`)
- Works with a physical paddle, a straight key, the touch paddle, or the
  keyboard (`Z`/`X`/space)
- No dependencies: pure Python 3 standard library. A physical paddle is optional
  (demo/touch mode works without one)

![Web UI](screenshot-ui.png)

## Open the web UI

The Pi **is the access point**. No home router, no internet needed.

1. Power the box, wait ~30 seconds
2. Join the WiFi **`IU2VWK-MORSE`** (password `morse1234`) — your phone will say
   "connected without internet", that's normal, stay connected
3. Open **`http://10.42.0.1`**

The lid carries two QR codes: **WIFI** (joins the network) and **APP** (opens
the page). At home the box also joins your LAN over Ethernet and answers on
port 80.

## Hardware

- Raspberry Pi 4 (also runs on Pi 5 / Zero 2 W) + power supply + microSD with
  Raspberry Pi OS Lite (64-bit)
- Paddle or straight key wired to the GPIO header (contacts to GND, internal
  pull-ups — no extra parts)
- 1–3 passive piezo buzzers (KY-006 3-pin modules)
- Optional MAX7219 8×8 LED matrix (shows WPM + live decoded text)

### Wiring (BCM numbering, key contacts to GND)

| Function | GPIO | Header pin |
|----------|------|------------|
| DIT (paddle) | 17 | 11 |
| DAH (paddle) | 27 | 13 |
| Straight key | 22 | 15 |
| GND | — | 6, 9, 14… |
| Piezo 1 signal | 24 | 18 |
| Piezo 2 signal | 25 | 22 |
| Piezo 3 signal | 12 | 32 |
| MAX7219 DIN / CLK / CS | 10 / 11 / 8 | 19 / 23 / 24 |

Each KY-006 module: `S` → signal pin, `+` (middle) → 5V (pins 2/4), `−` → GND.
Every `5V` pin is the same rail, every `GND` is the same rail — power wires may
share pins, but each `S` needs its own GPIO. Buzzer mode is `passive` by
default; for self-oscillating active buzzers add `--buzzer-mode active`.

## Install

```bash
sudo apt install git -y
git clone <this-repo> morsebox
cd morsebox
sudo bash install.sh
```

This sets hostname `iu2vwk-morse`, installs the autostart service, and creates
the `IU2VWK-MORSE` access point (password `morse1234`, changeable at the top of
`install.sh`). From then on: **power = on-air trainer**.

Multiple buzzers:

```bash
# /etc/systemd/system/iu2vwk-morse.service
ExecStart=/usr/bin/python3 /opt/iu2vwk-morse/server.py --port 80 --buzz-pins 24,25,12
sudo systemctl daemon-reload && sudo systemctl restart iu2vwk-morse
```

## Box & fair material

- `qr-1-wifi.png` / `qr-2-pagina.png` — **WIFI** and **APP** QR codes for the lid
- `qr-1-wifi.dxf` / `qr-2-pagina.dxf` — same QRs as 2 mm-module geometry for
  laser engraving in Autodesk Inventor
- `screenshot-ui-phone.png` — mobile layout reference

73 de IU2VWK · Angelo — https://iu2vwk.com
