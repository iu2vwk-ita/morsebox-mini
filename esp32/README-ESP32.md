# MorseBox Mini - ESP32 / MicroPython version

Port of the Raspberry Pi version to a classic **ESP32** with **MicroPython**.
The web UI is **identical** to the Pi one: the same `static/index.html`,
`static/style.css`, `static/app.js` files are served unchanged, and the
WebSocket protocol is the same.

## What it does

- The ESP32 creates the access point **`IU2VWK-MORSE`** (password `morse1234`).
- HTTP + WebSocket web server on port **80**, IP **10.42.0.1**
  (same IP as the Pi: the lid QR codes keep working).
- Iambic A / B + straight keyer, 5-60 WPM, reverse DX/SX, CW to text decoder.
- **Zero-latency hardware PWM sidetone** on 1-3 piezos, no audio pipeline.
- Optional MAX7219 8x8 display.
- Optional **LCD1602 I2C** display: line 1 `WPM xx` + keyer mode, line 2 the
  decoded CW text.

## Pinout

| Function | GPIO | Mode |
|---|---|---|
| DIT | 32 | `Pin.IN, PULL_UP` (contact to GND) |
| DAH | 33 | `Pin.IN, PULL_UP` (contact to GND) |
| STRAIGHT | 14 | `Pin.IN, PULL_UP` (contact to GND) |
| PIEZO 1 | 25 | `machine.PWM` |
| PIEZO 2 | 26 | `machine.PWM` |
| PIEZO 3 | 27 | `machine.PWM` |
| MAX7219 SCK | 18 | hardware SPI VSPI |
| MAX7219 MOSI | 23 | hardware SPI VSPI |
| MAX7219 CS | 4 | output |
| LCD1602 SDA | 21 | I2C |
| LCD1602 SCL | 22 | I2C |

The three piezos sound together: even one is enough.
The key contacts go to GND; the pull-ups are internal to the ESP32.
For the LCD1602 I2C backpack: `VCC` to 5V (VIN), `GND` to GND.

## Requirements

- ESP32 (WROOM-32) with recent MicroPython firmware (>= 1.20).
- `mpremote` on the PC: `pip install mpremote`.

If the ESP32 has no MicroPython, flash it with esptool:

```bash
esptool.py --chip esp32 --port /dev/ttyUSB0 erase_flash
esptool.py --chip esp32 --port /dev/ttyUSB0 write_flash -z 0x1000 \
  ESP32_GENERIC-20240602-v1.23.0.bin
```

## Deploy

```bash
bash deploy.sh                 # auto port
bash deploy.sh /dev/ttyUSB0    # explicit port
```

The script copies the `.py` files to the ESP32 root, creates `/static` with the
web UI and resets the board. On boot `main.py` starts.

## Test (no hardware)

The logic can be verified on a PC with CPython, using `uasyncio`/`time` stubs:

```bash
python3 tests/test_all.py
```

It covers: iambic A/B keyer, reverse, straight, decoder, WebSocket handshake,
frame encode/decode, HTTP parsing, routes and path traversal.

## Usage

1. Power the board, wait a few seconds.
2. On your phone, join the Wi-Fi **`IU2VWK-MORSE`** (password `morse1234`).
   The phone will say "no internet": that is normal, stay on that network.
3. Open **`http://10.42.0.1`**.
4. Key with the paddle, the straight key, the touch paddles or the keyboard
   (`Z` / `X` / space bar).

## Configuration

In `config.py`:

- `LCD_ENABLED = True` to use the LCD1602 I2C display (default `True`).
- `DISPLAY_ENABLED = True` to use the MAX7219 matrix (default `False`).
- `BUZZER_MODE = "passive"` for piezos (default). `"active"` for buzzers with
  a built-in oscillator (DC on/off drive).
- `AP_SSID` / `AP_PASS` / `AP_IP` to change the network.

The WPM, tone, volume, mode and reverse settings are saved in `settings.json`
and persist across reboots.

## Differences from the Pi version

| | Raspberry Pi | ESP32 MicroPython |
|---|---|---|
| Concurrency | threads | single `uasyncio` event loop |
| Web server | `http.server` + custom WS | native `uasyncio` sockets + custom WS |
| AP | hostapd + dnsmasq | native `network.WLAN(AP_IF)` |
| AP IP | 10.42.0.1 | 10.42.0.1 |
| mDNS hostname | `iu2vwk-morse.local` | not available (use the IP) |
| Deploy | `install.sh` + systemd | `deploy.sh` + `main.py` |
| Mic audio decoder | yes (optional) | **no** (dropped) |

## Technical notes

- The keyer runs at a ~1 ms tick and uses `time.ticks_ms()`: loop jitter does
  not accumulate, because every element is computed from the current instant.
- The sidetone is switched directly by the key state through `machine.PWM`:
  no audio buffer, no perceivable delay.
- `hub.broadcast()` never blocks the keyer: every WebSocket client has a queue;
  a slow client is dropped without stopping the key.
