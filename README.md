# MorseBox Mini — WiFi CW Trainer

A Morse keyer in a box. It serves a web page over its own WiFi: join the
network, open the page, key with a real paddle or the touch paddle on screen,
and read back your keying as text. The sidetone comes straight off the GPIO
pins with zero lag, on up to three piezo buzzers at once.

Two builds, **the same features and the same web UI**:

| Build | Folder | Board | Display |
|---|---|---|---|
| **Raspberry Pi** | root (`server.py`, `install.sh`, …) | Pi 4 / 5 / Zero 2 W | MAX7219 8x8 (optional) |
| **ESP32 / MicroPython** | [`esp32/`](esp32/) | classic ESP32 (also C3/C6/S3 with small pin changes) | SSD1306 OLED or LCD1602 I2C (optional) |

![MorseBox assembled](box.png)

## Quick install

**Raspberry Pi** (Raspberry Pi OS) — one command:

```bash
sudo apt install -y git && git clone https://github.com/iu2vwk-ita/morsebox-mini.git morsebox && cd morsebox && sudo bash install.sh
```

**ESP32 / MicroPython** — one command (first: `pip install mpremote`):

```bash
git clone https://github.com/iu2vwk-ita/morsebox-mini.git && cd morsebox/esp32 && bash deploy.sh
```

## What it does

* Iambic A / B, straight key and a **SINGLE** beginner mode (one tap = one
  element, no memory/repeat), 5 to 60 WPM, paddle reverse (DX⇄SX)
* Live decoded text on the web page and on the display
* Sidetone pitch (400–4000 Hz) and volume from the page, on 1 to 3 piezos
* Key with a paddle, a straight key, the on-screen paddle, or the keyboard
  (`Z` / `X` / space)
* **Exercise mode / CW courses** — a built-in trainer (see below)

![Web UI](screenshot-ui.png)

## Exercise mode (CW courses)

A guided trainer, available on **both** builds. Open the menu by keying **SOS**,
pick a drill with **N dots**, then confirm with **`..`** (or exit with `--`).
The target is **shown on the display and played on the piezo** at the chosen
WPM; for multi-letter targets the whole word is shown and the letter to key
**blinks**. A correct letter **flashes** as confirmation.

| N dots | Name on LCD | Drill |
|---|---|---|
| `.` | ALPHABET | Alphabet A-Z |
| `..` | NUMBERS | Numbers 0-9 |
| `...` | KOCH | Koch order |
| `....` | LETTERS | 20 random letters |
| `.....` | DIGITS | 20 random digits |
| `......` | MIXED | 20 random mixed letters/digits |
| `.......` | CALLSIGNS | Common callsigns |
| `........` | ABBREV | Q-codes / abbreviations |
| `.........` | PUNCT | Punctuation / prosigns |
| `-` | FULL | Full drill: A-Z then 0-9 |

When you pick a number the display shows its name (e.g. `3 KOCH ?`) before you
confirm with `..`, so the mapping is always visible on the device.

During a drill: **`......`** (6 dots, one group) = **stop**,
**`------`** (6 dashes, one group) = **skip**. A correct answer advances, a
wrong one restarts the target; the run ends with `DONE n/m`. You can also start
directly with `TEST` (full drill) or `TEST1`..`TEST9`.

## Open the web UI

The board is the access point. No home router, no internet needed.

1. Power the box, wait a few seconds
2. Join the WiFi **`IU2VWK-MORSE`** (password `morse1234`). The phone will say
   "connected without internet": that is normal, stay on it
3. Open **`http://10.42.0.1`**

The lid has two QR codes: **WIFI** joins the network, **APP** opens the page.
At home the Raspberry Pi version also works over Ethernet on port 80.

## Raspberry Pi — hardware and wiring

* Raspberry Pi (4, 5, Zero 2 W or similar) with Raspberry Pi OS Lite
* Paddle or straight key wired to the GPIO header (contacts to GND, internal
  pull-ups, no extra parts)
* 1 to 3 passive piezo buzzers (KY-006 3-pin modules)
* Optional MAX7219 8x8 LED matrix (shows WPM plus live decoded text)

| Function | BCM GPIO | Header pin |
|---|---|---|
| DIT (paddle) | 17 | 11 |
| DAH (paddle) | 27 | 13 |
| Straight key | 22 | 15 |
| GND | — | 6, 9, 14… |
| Piezo 1 signal | 24 | 18 |
| Piezo 2 signal | 25 | 22 |
| Piezo 3 signal | 12 | 32 |
| MAX7219 DIN / CLK / CS | 10 / 11 / 8 | 19 / 23 / 24 |

Each KY-006 module: `S` to its signal pin, `+` (middle) to 5V, `−` to GND. All
`5V` pins are one rail and all `GND` pins are one rail, so power wires can
share. Default buzzer mode is `passive`; with a self-beeping active buzzer use
`--buzzer-mode active`.

<img src="piezo.png" alt="The three piezos wired in" width="751">

Install (the one-liner above does all of this): it sets the hostname to
`iu2vwk-morse`, installs the autostart service and brings up the
`IU2VWK-MORSE` access point. Three buzzers:

```bash
# /etc/systemd/system/iu2vwk-morse.service
ExecStart=/usr/bin/python3 /opt/iu2vwk-morse/server.py --port 80 --buzz-pins 24,25,12
sudo systemctl daemon-reload && sudo systemctl restart iu2vwk-morse
```

## ESP32 / MicroPython — hardware and wiring

Code in [`esp32/`](esp32/), full guide in
[`esp32/README-ESP32.md`](esp32/README-ESP32.md) (flashing, LCD1602, wiring).

| Function | GPIO |
|---|---|
| DIT | 32 |
| DAH | 33 |
| STRAIGHT | 14 |
| PIEZO 1 / 2 / 3 | 25 / 26 / 27 |
| I2C SDA / SCL (OLED or LCD1602) | 21 / 22 |
| MAX7219 SCK / MOSI / CS | 18 / 23 / 4 |

Key contacts to GND, internal pull-ups. The firmware auto-detects the display
at boot: **SSD1306 OLED first, then LCD1602, then MAX7219, then none**. Both
I2C displays share the same two wires:

* **SSD1306 OLED** (0.96"/1.3", 128x64, I2C 4-pin) — the nicest option: ~5-6
  lines of text, no cramped 16x2 window. `VCC` to **3.3V**, `GND`, `SCL` to
  GPIO22, `SDA` to GPIO21. Address 0x3C/0x3D (auto-detected).
* **LCD1602** with I2C backpack — `VCC` to 5V (VIN), `GND`, same SDA/SCL.
  Address 0x27/0x3F.

### Display options (pick one, or none)

The firmware detects the display automatically, in this order:
**SSD1306 OLED -> LCD1602 -> MAX7219 -> no display**. Nothing to configure.

* **With SSD1306 OLED** (recommended — "the nice one") — 128x64 graphical
  display, same two I2C wires as the LCD. Top line `WPM xx` + keyer mode, then
  the decoded text wrapped over several lines; the exercise target and its `^`
  cursor are far easier to read. The driver is loaded **only** if the I2C bus
  answers at 0x3C/0x3D, so with no OLED there is no RAM cost.

* **With LCD1602** — line 1 `WPM xx` + keyer mode, line 2 the decoded text.

  ![MorseBox ESP32 with LCD1602](box-lcd.png)

* **Without display (simpler)** — no display: everything is controlled from the
  phone web app (speed, mode, tone, volume and the decoded text). This is the
  easiest build.

  ![MorseBox ESP32 without LCD](box-noscreen.png)

## Box and fair material

* `qr-1-wifi.png` / `qr-2-pagina.png` — the **WIFI** and **APP** QR codes for
  the lid
* `qr-1-wifi.dxf` / `qr-2-pagina.dxf` — same QRs as 2 mm geometry for laser
  engraving in Autodesk Inventor
* `screenshot-ui-phone.png` — how the page looks on a phone
* `CW BOX SMALL.3mf` — the box, ready to 3D print, all versions on separate
  plates: ESP32 with LCD, ESP32 without LCD, and Raspberry Pi

73 de IU2VWK · Angelo — https://iu2vwk.com

Thanks to Panko for the inspiration and the original
[Simple CW Keyer](https://github.com/Panko74/Simple-CW-Keyer).
