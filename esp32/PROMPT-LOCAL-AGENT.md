# Prompt to paste into a local AI agent (with filesystem and USB access)

You are an AI agent with access to this PC's filesystem and USB ports.
You must install MicroPython on an ESP32 board connected over USB, upload the
project inside `morsebox-esp32.zip` and run the automated tests.
Do not ask for confirmation for the commands: run them and report the result.
If a command fails, diagnose it and try the suggested alternatives.

## Project

- Folder `morsebox-esp32/` (inside the zip).
- MicroPython app: on boot `main.py` creates the access point
  **`IU2VWK-MORSE`** (password `morse1234`), IP **10.42.0.1**, web server on
  port **80**.
- Pinout: **DIT=GPIO32**, **DAH=GPIO33**, **STRAIGHT=GPIO14** (all `Pin.IN`
  with `PULL_UP`, contacts to GND); **PIEZO=GPIO25,26,27** (PWM); MAX7219
  optional on **SCK=18, MOSI=23, CS=4** (disabled by default); LCD1602 I2C on
  **SDA=21, SCL=22**.
- `static/` is the web UI: **do not modify it**.
- `tests/selftest_device.py` is the test that runs **on the board**.

## Phase 0 - extract and prepare the tools

```bash
unzip morsebox-esp32.zip
cd morsebox-esp32
python3 -m venv .venv && . .venv/bin/activate
pip install esptool mpremote
```

## Phase 1 - detect serial port and chip

```bash
# Linux
ls /dev/ttyUSB* /dev/ttyACM*
# macOS
ls /dev/cu.*
# detect the chip (replace <PORT>)
esptool.py --port <PORT> chip_id
```

If no port appears: change the cable (it must be a **data** cable, not
charge-only), try another USB port, or use a USB-TTL adapter on TX/RX/GND.
On Linux, if permission is denied: `sudo chmod a+rw <PORT>` or add the user to
the `dialout` group.

## Phase 2 - flash MicroPython

Pick the firmware based on the detected chip:

- Classic ESP32 -> `ESP32_GENERIC`
- ESP32-S3 -> `ESP32_GENERIC_S3`
- ESP32-C3 -> `ESP32_GENERIC_C3`

Download the latest `.bin` from <https://micropython.org/download/> and then:

```bash
esptool.py --chip esp32 --port <PORT> erase_flash
esptool.py --chip esp32 --port <PORT> --baud 460800 write_flash -z 0x1000 <firmware>.bin
```

If flashing fails, hold **BOOT** while connecting the board and retry.
Adapt `--chip` to the real chip (`esp32`, `esp32s3`, `esp32c3`).

## Phase 3 - deploy the project

```bash
bash deploy.sh <PORT>
```

Check the board contents:

```bash
mpremote connect <PORT> fs ls
mpremote connect <PORT> fs ls :static
```

## Phase 4 - on-device self-test

Disable autostart (so the REPL and port 80 are free), run the test, then
restore `main.py`:

```bash
mpremote connect <PORT> fs cp main.py :main.py.bak
mpremote connect <PORT> fs rm :main.py
mpremote connect <PORT> reset
sleep 3
mpremote connect <PORT> run tests/selftest_device.py
mpremote connect <PORT> fs cp main.py.bak :main.py
mpremote connect <PORT> fs rm :main.py.bak
mpremote connect <PORT> reset
```

Expect a sequence of `PASS` lines and at the end:

```
PASS: N   FAIL: 0
```

The test checks: AP active and IP `10.42.0.1`, GPIO read at idle, PWM on/off
and frequency, HTTP (`/`, `/style.css`, `/app.js`, `/api/settings`, 404),
WebSocket (101 + `hello`) and **Morse decoding driven by remote paddles**
(dit + dah -> `A`).

## Phase 5 - final report

Report concisely:

- serial port used and detected chip;
- MicroPython firmware used;
- full self-test output;
- any `FAIL` with its cause;
- confirmation that after the final reset the `IU2VWK-MORSE` AP is active.

## Success criteria

1. MicroPython installed and `main.py` restored (starts on boot).
2. Self-test with `FAIL: 0` (or every FAIL explained).
3. `IU2VWK-MORSE` AP active after the reset.

## What cannot be tested without hardware

- The physical paddle/straight key contacts and the real piezo sound.
- The MAX7219 display if not connected.

## Notes

- If the PC has no Wi-Fi it cannot join the AP: the self-test uses the board's
  own loopback (`127.0.0.1`), so it works anyway.
- Do not modify the files in `static/`: the UI must stay identical to the
  original.
