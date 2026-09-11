#!/usr/bin/env python3
"""IU2VWK Morse Simulator - iambic keyer + web UI for Raspberry Pi.

- Reads the paddle/straight key from the GPIO (mock fallback outside the Pi).
- Iambic A/B keyer + straight mode, 5-60 WPM, DX/SX swap.
- Serves the web UI, exposes a WebSocket for remote (touch) keys and live events.
- Decodes CW into text. Stdlib only: nothing to install.

Wiring (BCM): DIT=GPIO17 (pin 11), DAH=GPIO27 (pin 13), STRAIGHT=GPIO22 (pin 15),
GND on pin 6/9/14. Optional active buzzer on GPIO24 (pin 18). Contacts to GND.
"""
import argparse
import base64
import hashlib
import json
import os
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from morse import FROM_MORSE
from exercise import Exercise

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")

DEFAULTS = {"wpm": 20, "reverse": False, "mode": "iambic-b",
            "tone": 650, "buzzer": False, "volume": 70}

DIT_PIN, DAH_PIN, KEY_PIN, BUZZ_PIN = 17, 27, 22, 24
HOLD_TIMEOUT = 2.5  # s: forget remote paddles that stop reporting

# ---------------------------------------------------------------- settings
class Settings:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = dict(DEFAULTS)
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                self._data.update(json.load(f))
        except (OSError, ValueError):
            pass
        self._clamp()

    def _clamp(self):
        d = self._data
        d["wpm"] = max(5, min(60, int(d.get("wpm", 20))))
        d["tone"] = max(500, min(1000, int(d.get("tone", 650))))
        d["reverse"] = bool(d.get("reverse", False))
        if d.get("mode") not in ("iambic-a", "iambic-b", "straight"):
            d["mode"] = "iambic-b"
        d["buzzer"] = bool(d.get("buzzer", False))
        d["volume"] = max(0, min(100, int(d.get("volume", 70))))

    def get(self):
        with self._lock:
            return dict(self._data)

    def patch(self, p):
        with self._lock:
            for k in DEFAULTS:
                if k in p:
                    self._data[k] = p[k]
            self._clamp()
            data = dict(self._data)
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            pass
        return data


# ---------------------------------------------------------------- gpio
class GPIO:
    """Active-low pull-up inputs. Tries RPi.GPIO, then gpiozero, then mock."""

    def __init__(self, buzz_pins=None):
        self.backend = "mock"
        self._gpio = None
        self._dit = self._dah = self._key = None
        self._buzz = []
        # Extra buzzer pins (BCM), e.g. [24, 25]. Default: only 24 (pin 18).
        self.buzz_pins = list(buzz_pins) if buzz_pins else [BUZZ_PIN]
        try:
            import RPi.GPIO as G
            G.setmode(G.BCM)
            for p in (DIT_PIN, DAH_PIN, KEY_PIN):
                G.setup(p, G.IN, pull_up_down=G.PUD_UP)
            self._gpio = G
            self.backend = "RPi.GPIO"
        except Exception:
            try:
                from gpiozero import Button, LED
                self._dit = Button(DIT_PIN, pull_up=True)
                self._dah = Button(DAH_PIN, pull_up=True)
                self._key = Button(KEY_PIN, pull_up=True)
                self._buzz = [LED(p) for p in self.buzz_pins]
                self.backend = "gpiozero"
            except Exception:
                pass

    def read(self):
        """(dit, dah, straight) True = pressed."""
        if self._gpio is not None:
            G = self._gpio
            return (not G.input(DIT_PIN), not G.input(DAH_PIN),
                    not G.input(KEY_PIN))
        if self._dit is not None:
            return (self._dit.is_pressed, self._dah.is_pressed,
                    self._key.is_pressed)
        return (False, False, False)

    def buzzer(self, on):
        try:
            if self._gpio is not None and self._buzz_pin_ready():
                self._gpio.output(self.buzz_pins, self._gpio.HIGH if on
                                  else self._gpio.LOW)
            elif self._buzz:
                for b in self._buzz:
                    b.on() if on else b.off()
        except Exception:
            pass

    def _buzz_pin_ready(self):
        if not getattr(self, "_buzz_setup", False):
            try:
                for p in self.buzz_pins:
                    self._gpio.setup(p, self._gpio.OUT,
                                     initial=self._gpio.LOW)
            except Exception:
                return False
            self._buzz_setup = True
        return True


# ---------------------------------------------------------------- keyer
class Hub:
    """Holds WS clients, remote holds and text history. Thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self.clients = set()
        self.holds = {}  # cid -> {"dit":b,"dah":b,"key":b,"ts":t}
        self.history = ""

    def add(self, c):
        with self._lock:
            self.clients.add(c)

    def drop(self, c):
        with self._lock:
            self.clients.discard(c)
            self.holds.pop(id(c), None)

    def hold(self, c, dit, dah, key):
        with self._lock:
            self.holds[id(c)] = {"dit": bool(dit), "dah": bool(dah),
                                 "key": bool(key), "ts": time.monotonic()}

    def remote(self):
        now = time.monotonic()
        d = h = k = False
        with self._lock:
            for v in self.holds.values():
                if now - v["ts"] < HOLD_TIMEOUT:
                    d = d or v["dit"]
                    h = h or v["dah"]
                    k = k or v["key"]
        return d, h, k

    def push_text(self, ch):
        with self._lock:
            self.history = (self.history + ch)[-120:]

    def snapshot_text(self):
        with self._lock:
            return self.history

    def clear_text(self):
        with self._lock:
            self.history = ""

    def broadcast(self, msg, exclude=None):
        raw = json.dumps(msg)
        with self._lock:
            clients = list(self.clients)
        for c in clients:
            if c is exclude:
                continue
            try:
                c.send_text(raw)
            except Exception:
                self.drop(c)


class Keyer(threading.Thread):
    """Iambic keyer + decoder. 1 ms tick, events via hub.broadcast."""

    def __init__(self, gpio, settings, hub, exercise=None):
        super().__init__(daemon=True)
        self.gpio = gpio
        self.settings = settings
        self.hub = hub
        self.exercise = exercise
        self.key_out = False
        self._stop = threading.Event()
        self.screen = None  # matrix display (optional)
        self.sidetone = None  # note to the speaker (optional)

    def _set_key(self, on):
        if on == self.key_out:
            return
        self.key_out = on
        self.hub.broadcast({"t": "key", "on": on,
                            "dit": getattr(self, "_in_dit", False),
                            "dah": getattr(self, "_in_dah", False)})
        if self.sidetone and not (self.exercise and self.exercise.playing):
            self.sidetone.set(on)
        now = time.monotonic()
        if on:
            self._on_at = now
        else:
            self._decode_element(now - self._on_at, self._unit)
            self._off_at = now

    def _decode_element(self, dur, unit):
        self._buf += "-" if dur >= 2 * unit else "."
        self._buf_at = time.monotonic()

    def _flush_letter(self):
        if self._buf:
            buf = self._buf
            ch = FROM_MORSE.get(buf, "◇")
            if self.exercise and self.exercise.active:
                # during an exercise the decoded letter is the answer
                self.exercise.feed(ch, buf)
            elif self.exercise and self.exercise.menu:
                self._menu_select(buf)
            else:
                self.hub.push_text(ch)
                self.hub.broadcast({"t": "txt", "ch": ch})
                if self.screen:
                    self.screen.add_char(ch)
                self._check_exercise_trigger(buf)
            self._buf = ""

    def _menu_select(self, buf):
        """Menu: N dots = exercise N, one dash = full drill. Then confirm:
        .. = start, -- = exit."""
        ex = self.exercise
        if ex.pending is not None:
            if buf == "..":
                ex.confirm()
            else:
                ex.cancel()
            return
        if buf == "-":
            ex.select(0)
        elif buf and set(buf) == {"."}:
            n = len(buf)
            if 1 <= n <= 9:
                ex.select(n)
            else:
                ex.cancel()
        else:
            ex.cancel()

    def _check_exercise_trigger(self, buf=None):
        """Start an exercise on SOS (menu) or TEST / TESTn."""
        if not self.exercise:
            return
        if buf == "...---...":
            self.exercise.enter_menu()
            return
        txt = self.hub.snapshot_text().replace(" ", "").upper()
        if txt.endswith("SOS"):
            self.exercise.enter_menu()
            return
        for n in range(9, 0, -1):
            if txt.endswith("TEST%d" % n):
                self.exercise.start(n)
                return
        if txt.endswith("TEST"):
            self.exercise.start(0)

    def run(self):
        dit_mem = dah_mem = False
        last = "dah"
        sending = None
        t_end = t_gap = 0.0
        self._buf = ""
        self._buf_at = 0.0
        self._on_at = 0.0
        self._off_at = 0.0
        word_sent = True
        p_dit = p_dah = p_key = False
        self._pad_dit = self._pad_dah = False
        while not self._stop.is_set():
            now = time.monotonic()
            st = self.settings.get()
            unit = 1.2 / st["wpm"]
            self._unit = unit
            mode = st["mode"]
            rev = st["reverse"]

            pd, ph, pk = self.gpio.read()
            rd, rh, rk = self.hub.remote()
            # reverse: swap DIT/DAH on BOTH inputs (GPIO and touch)
            raw_dit = pd or rd
            raw_dah = ph or rh
            dit = raw_dah if rev else raw_dit
            dah = raw_dit if rev else raw_dah
            skey = pk or rk
            self._in_dit, self._in_dah = dit, dah
            if (dit, dah) != (self._pad_dit, self._pad_dah):
                self._pad_dit, self._pad_dah = dit, dah
                self.hub.broadcast({"t": "pad", "dit": dit, "dah": dah})

            # 5 ms debounce
            if (dit, dah, skey) != (p_dit, p_dah, p_key):
                p_dit, p_dah, p_key = dit, dah, skey
                time.sleep(0.002)
                continue

            if mode == "straight":
                dit_mem = dah_mem = False
                sending = None
                self._set_key(skey)
            elif sending is not None:
                if dit:
                    dit_mem = True
                if dah:
                    dah_mem = True
                if now >= t_end:
                    # end of element: mode A resamples, mode B keeps the memory
                    if mode == "iambic-a":
                        dit_mem, dah_mem = dit, dah
                    self._set_key(False)
                    sending = None
                    t_gap = now + unit
            elif now >= t_gap:
                if dit:
                    dit_mem = True
                if dah:
                    dah_mem = True
                if dit_mem and dah_mem:
                    nxt = "dah" if last == "dit" else "dit"
                    if nxt == "dit":
                        dit_mem = False
                    else:
                        dah_mem = False
                    sending, last = nxt, nxt
                    self._set_key(True)
                    t_end = now + (unit if nxt == "dit" else 3 * unit)
                elif dit_mem:
                    dit_mem = False
                    sending, last = "dit", "dit"
                    self._set_key(True)
                    t_end = now + unit
                elif dah_mem:
                    dah_mem = False
                    sending, last = "dah", "dah"
                    self._set_key(True)
                    t_end = now + 3 * unit

            # decoder: letter gap 3u, word gap 7u
            if self._buf and not self.key_out and now - self._off_at > 3 * unit:
                self._flush_letter()
                word_sent = False
            if (not self._buf and not word_sent and not self.key_out
                    and now - self._off_at > 7 * unit):
                self.hub.push_text(" ")
                self.hub.broadcast({"t": "txt", "ch": " "})
                word_sent = True

            time.sleep(0.001)

    def stop(self):
        self._stop.set()


# ---------------------------------------------------------------- websocket
WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_accept(key):
    return base64.b64encode(
        hashlib.sha1((key + WS_MAGIC).encode()).digest()).decode()


def ws_encode(text):
    raw = text.encode("utf-8")
    hdr = bytes([0x81])
    n = len(raw)
    if n < 126:
        hdr += struct.pack("!B", n)
    elif n < 65536:
        hdr += struct.pack("!BH", 126, n)
    else:
        hdr += struct.pack("!BQ", 127, n)
    return hdr + raw


def ws_decode_frame(sock):
    hdr = _recvn(sock, 2)
    b1, b2 = hdr[0], hdr[1]
    opcode = b1 & 0x0F
    masked = b2 & 0x80
    ln = b2 & 0x7F
    if ln == 126:
        ln = struct.unpack("!H", _recvn(sock, 2))[0]
    elif ln == 127:
        ln = struct.unpack("!Q", _recvn(sock, 8))[0]
    mask = _recvn(sock, 4) if masked else None
    payload = _recvn(sock, ln) if ln else b""
    if masked and payload:
        payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
    return opcode, payload


def _recvn(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("ws closed")
        buf += chunk
    return buf


class WSConn:
    def __init__(self, sock):
        self.sock = sock
        self._lock = threading.Lock()

    def send_text(self, text):
        with self._lock:
            self.sock.sendall(ws_encode(text))

    def send_raw(self, raw):
        with self._lock:
            self.sock.sendall(raw)


# ---------------------------------------------------------------- http
MIME = {".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json",
        ".png": "image/png", ".svg": "image/svg+xml"}


class Handler(BaseHTTPRequestHandler):
    server_version = "IU2VWK-Morse/1.0"

    def log_message(self, *a):
        pass

    # -- websocket --
    def _is_ws(self):
        return (self.headers.get("Upgrade", "").lower() == "websocket"
                and "Sec-WebSocket-Key" in self.headers)

    def _serve_ws(self):
        key = self.headers["Sec-WebSocket-Key"]
        body = (b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\n"
                b"Connection: Upgrade\r\n"
                b"Sec-WebSocket-Accept: " + ws_accept(key).encode() + b"\r\n"
                b"\r\n")
        self.connection.sendall(body)
        conn = WSConn(self.connection)
        hub = self.server.hub
        hub.add(conn)
        try:
            conn.send_text(json.dumps(
                {"t": "hello", "settings": self.server.settings.get(),
                 "text": hub.snapshot_text(),
                 "gpio": self.server.gpio.backend}))
            while True:
                op, payload = ws_decode_frame(self.connection)
                if op == 0x8:
                    break
                if op == 0x9:  # ping -> pong
                    conn.send_raw(b"\x8a\x00")
                    continue
                if op != 0x1:
                    continue
                try:
                    msg = json.loads(payload.decode("utf-8"))
                except ValueError:
                    continue
                if msg.get("t") == "paddle":
                    hub.hold(conn, msg.get("dit"), msg.get("dah"),
                             msg.get("key"))
                elif msg.get("t") == "settings":
                    data = self.server.settings.patch(msg)
                    _apply_screen(self.server, data)
                    hub.broadcast({"t": "settings", "settings": data},
                                  exclude=conn)
        except (ConnectionError, OSError):
            pass
        finally:
            hub.drop(conn)

    # -- http --
    def do_GET(self):
        if self.path == "/ws" and self._is_ws():
            self._serve_ws()
            return
        url = urlparse(self.path)
        if url.path == "/api/settings":
            self._json(self.server.settings.get())
            return
        if url.path in ("/", "/index.html"):
            self._file("index.html")
            return
        name = url.path.lstrip("/").replace("\\", "/")
        if ".." in name or "/" in name or not name:
            self._404()
            return
        self._file(name)

    def do_POST(self):
        if urlparse(self.path).path != "/api/settings":
            self._404()
            return
        try:
            ln = int(self.headers.get("Content-Length", 0))
        except ValueError:
            ln = 0
        try:
            patch = json.loads(self.rfile.read(ln).decode("utf-8") or "{}")
        except ValueError:
            patch = {}
        data = self.server.settings.patch(patch)
        _apply_screen(self.server, data)
        self.server.hub.broadcast({"t": "settings", "settings": data})
        self._json(data)

    def _json(self, obj):
        raw = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _file(self, name):
        path = os.path.join(STATIC_DIR, name)
        if not os.path.isfile(path):
            self._404()
            return
        _, ext = os.path.splitext(name)
        ctype = MIME.get(ext.lower(), "application/octet-stream")
        with open(path, "rb") as f:
            raw = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _404(self):
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"not found")


def _apply_screen(srv, data):
    if getattr(srv, "screen", None):
        srv.screen.set_wpm(data.get("wpm", 20))
    if getattr(srv, "sidetone", None) and "tone" in data:
        srv.sidetone.set_freq(data["tone"])
    if getattr(srv, "sidetone", None) and "volume" in data:
        srv.sidetone.set_volume(data["volume"])


def main():
    ap = argparse.ArgumentParser(description="IU2VWK Morse Simulator")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=80)
    ap.add_argument("--audio-in", action="store_true",
                    help="audio (click) decoder from the microphone, off by default")
    ap.add_argument("--buzzer-mode", default="passive", choices=["active", "passive"],
                    help="active = DC on/off (buzzer with oscillator), "
                         "passive = PWM (drivable piezo)")
    ap.add_argument("--buzz-pins", default="24",
                    help="comma-separated BCM GPIOs of the piezo, e.g. '24' or "
                         "'24,25'. All sound together (default: 24 = pin 18)")
    args = ap.parse_args()
    try:
        buzz_pins = [int(p) for p in args.buzz_pins.replace(";", ",").split(",")
                     if p.strip()]
    except ValueError:
        buzz_pins = [24]
    if not buzz_pins:
        buzz_pins = [24]

    settings = Settings()
    gpio = GPIO(buzz_pins=buzz_pins)
    hub = Hub()
    keyer = Keyer(gpio, settings, hub)
    keyer.start()

    screen = None
    try:
        import display
        screen = display.Screen()
        if screen.hw is not None:
            print("MAX7219 display: %s" % screen.hw.backend, flush=True)
        else:
            print("Display: not detected (no matrix), web UI only", flush=True)
        _apply_screen({"screen": screen}, {"wpm": settings.get()["wpm"]})
        keyer.screen = screen
    except Exception as e:
        print("Display not initialized: %s" % e, flush=True)

    sidetone = None
    decoder = None
    try:
        import audio
        # Sidetone on the GPIO buzzer (zero latency). Active = DC on/off
        # (buzzer with oscillator), passive = PWM (drivable piezo).
        sidetone = audio.GPIOTone(freq=settings.get()["tone"],
                                  mode=args.buzzer_mode, pins=buzz_pins)
        sidetone.set_volume(settings.get()["volume"])
        if sidetone._ok:
            keyer.sidetone = sidetone
            print("Sidetone GPIO buzzer %s (%s, zero latency): ok"
                  % (buzz_pins, args.buzzer_mode), flush=True)
        else:
            sidetone = None
            print("GPIO buzzer not available (RPi.GPIO required)", flush=True)

        def on_key(on):
            hub.broadcast({"t": "key", "on": on, "audio": True})
            if sidetone:
                sidetone.set(on)

        def on_char(code):
            ch = FROM_MORSE.get(code)
            if ch:
                hub.push_text(ch)
                hub.broadcast({"t": "txt", "ch": ch})
                if screen:
                    screen.add_char(ch)

        if args.audio_in:
            decoder = audio.CwAudioDecoder(on_key=on_key, on_char=on_char)
            decoder.start()
    except Exception as e:
        print("Audio not initialized: %s" % e, flush=True)

    # Exercise / course mode: works with the piezo and the display if present
    exercise = Exercise(settings, hub, sidetone=sidetone, screen=screen)
    keyer.exercise = exercise
    exercise.start()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    srv.settings = settings
    srv.gpio = gpio
    srv.hub = hub
    srv.screen = screen
    srv.sidetone = sidetone
    srv.decoder = decoder
    print("IU2VWK Morse Simulator on http://%s:%d (gpio: %s)"
          % (args.host, args.port, gpio.backend), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        keyer.stop()


if __name__ == "__main__":
    main()
