# MorseBox Mini - ESP32 / MicroPython version

Port of the Raspberry Pi version to a classic **ESP32** with **MicroPython**.
The web UI is **identical** to the Pi one: the same `static/index.html`,
`static/style.css`, `static/app.js` files are served unchanged, and the
WebSocket protocol is the same.

## What it does

- The ESP32 creates the access point **`IU2VWK-MORSE`** (password `morse1234`).
- HTTP + WebSocket web server on port **80**, IP **10.42.0.1**
  (same IP as the Pi: the lid QR codes keep working).
- Iambic A / B + straight keyer + **SINGLE** beginner mode (one tap = one
  element, no memory/repeat), 5-60 WPM, reverse DX/SX, CW to text decoder.
- **Zero-latency hardware PWM sidetone** on 1-3 piezos, no audio pipeline.
- Optional MAX7219 8x8 display.
- Optional **LCD1602 I2C** display: line 1 `WPM xx` + keyer mode, line 2 the
  decoded CW text.

## Exercise mode

**Beginner-friendly start:** key **`SOS`** (`...---...`) to open the exercise
menu, key **N dots** to pick a drill, then **`..`** to confirm (or **`--`** to
exit). The target is **shown on the LCD and played on the piezo** (always
together) at the selected WPM, then you key it back.

| N dots | Name on LCD | Exercise |
|---|---|---|
| `.` | ALPHABET | TEST1 - Alphabet A-Z |
| `..` | NUMBERS | TEST2 - Numbers 0-9 |
| `...` | KOCH | TEST3 - Koch order |
| `....` | LETTERS | TEST4 - 20 random letters |
| `.....` | DIGITS | TEST5 - 20 random digits |
| `......` | MIXED | TEST6 - 20 random mixed |
| `.......` | CALLSIGNS | TEST7 - Common callsigns |
| `........` | ABBREV | TEST8 - Q-codes / abbreviations |
| `.........` | PUNCT | TEST9 - Punctuation / prosigns |
| `-` | FULL | Full drill: A-Z then 0-9 |

When you pick a number the LCD shows its name (e.g. `3 KOCH ?`) before you
confirm with `..`.

You can also key **`TEST`** (full drill) or **`TEST1`..`TEST9`** directly.

Controls: **`......`** (6 dots) = stop, **`------`** (6 dashes) = skip. A
correct answer advances; a wrong one repeats the same target. The end of the
run shows `DONE n/m`.

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

It covers: iambic A/B keyer, single mode, reverse, straight, decoder, WebSocket handshake,
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

## Module reference

| Module | Main entry points | What it does |
|---|---|---|
| `main.py` | `main()` | Boot: AP, settings, paddle, piezo, display, event loop |
| `config.py` | constants | Pin map, defaults, boot messages |
| `wifi_ap.py` | `start_ap()` | Creates the `IU2VWK-MORSE` access point |
| `gpio.py` | `Paddle.read()` | Reads DIT / DAH / STRAIGHT (active low, pull-up) |
| `sidetone.py` | `Sidetone.set()`, `set_freq()`, `set_volume()` | Zero-latency PWM on 1-3 piezos |
| `keyer.py` | `Keyer.run()` | Iambic A/B + straight + single state machine and CW decoder |
| `keyer.py` | `_set_key()`, `_flush_letter()`, `_check_exercise_trigger()`, `_menu_select()` | Key output, letter decoding, exercise triggers and menu |
| `exercise.py` | `build(n)` | Builds the target list for drill `n` (0..9) |
| `exercise.py` | `Exercise.enter_menu()`, `select()`, `confirm()`, `cancel()`, `start()`, `feed()`, `run()` | Menu, confirmation, per-letter progress, blinking target, playback |
| `hub.py` | `Hub.broadcast()`, `remote()`, `hold()` | WebSocket clients, remote paddle holds, text history |
| `wsproto.py` | `ws_accept()`, `ws_encode()`, `ws_read_frame()` | Minimal RFC 6455 WebSocket |
| `webserver.py` | `WebServer.start()` | HTTP routes + WebSocket upgrade (native sockets) |
| `lcd1602.py` | `I2cLcd`, `Screen` | 16x2 I2C display: WPM/mode, decoded text, exercise target |
| `display.py` | `Max7219`, `Screen` | Optional 8x8 matrix (scrolling text) |
| `settings.py` | `Settings.get()`, `patch()` | Persistent settings on `settings.json` |
| `morse.py` | `MORSE`, `FROM_MORSE` | Morse table and its reverse |
| `tests/test_all.py` | — | 19 host-side tests (CPython, `uasyncio`/`time` stubs) |
| `tests/selftest_device.py` | — | On-device self-test: AP, GPIO, PWM, HTTP, WS, keyer |

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
