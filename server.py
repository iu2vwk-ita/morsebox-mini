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
from reflex import Reflex
from easter import EasterEgg

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")

DEFAULTS = {"wpm": 20, "reverse": False, "mode": "iambic-b",
            "tone": 650, "buzzer": False, "volume": 70,
            "buzzer_mode": "passive"}

DIT_PIN, DAH_PIN, KEY_PIN, BUZZ_PIN = 17, 27, 22, 24
HOLD_TIMEOUT = 2.5  # s: forget remote paddles that stop reporting

# While choosing a program in the SOS menu (1-10 dots) the keyer runs slowly at
# this speed. Once the drill starts it uses the normal WPM setting.
MENU_WPM = 10

# ---------------------------------------------------------------- settings
def as_bool(v, default=False):
    """Strict boolean: 'false' must NOT become True (bool('false') == True)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return default


class Settings:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = dict(DEFAULTS)
        self._last_save = 0.0
        self._dirty = False
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                self._data.update(json.load(f))
        except (OSError, ValueError):
            pass
        self._clamp()
        # flush debounced saves in the background (avoids SD wear on a drag)
        threading.Thread(target=self._saver, daemon=True).start()

    def _clamp(self):
        # per-field fallback: one bad value must not wipe the others
        d = self._data
        d["wpm"] = self._int(d, "wpm", 20, 5, 60)
        d["tone"] = self._int(d, "tone", 650, 500, 1000)
        d["volume"] = self._int(d, "volume", 70, 0, 100)
        d["reverse"] = as_bool(d.get("reverse", False))
        d["buzzer"] = as_bool(d.get("buzzer", False))
        if d.get("mode") not in ("iambic-a", "iambic-b", "straight", "single"):
            d["mode"] = "iambic-b"
        if d.get("buzzer_mode") not in ("active", "passive"):
            d["buzzer_mode"] = "passive"

    @staticmethod
    def _int(d, key, default, lo, hi):
        try:
            return max(lo, min(hi, int(d.get(key, default))))
        except (TypeError, ValueError):
            return default

    def get(self):
        with self._lock:
            return dict(self._data)

    def snapshot(self):
        """Read-only view with NO copy: used by the 1 ms keyer loop."""
        return self._data

    def patch(self, p):
        with self._lock:
            for k in DEFAULTS:
                if k in p:
                    self._data[k] = p[k]
            self._clamp()
            self._dirty = True
            data = dict(self._data)
        self.flush()
        return data

    def flush(self):
        """Write at most once per second; the background thread guarantees the
        last change is eventually persisted."""
        with self._lock:
            if not self._dirty:
                return
            now = time.monotonic()
            if now - self._last_save < 1.0:
                return
            self._last_save = now
            self._dirty = False
            data = dict(self._data)
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            with self._lock:
                self._dirty = True

    def _saver(self):
        while True:
            time.sleep(0.5)
            try:
                self.flush()
            except Exception:
                pass


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
            for cid in list(self.holds):
                v = self.holds[cid]
                if now - v["ts"] < HOLD_TIMEOUT:
                    d = d or v["dit"]
                    h = h or v["dah"]
                    k = k or v["key"]
                else:
                    del self.holds[cid]      # prune stale holds
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

    def __init__(self, gpio, settings, hub, exercise=None, reflex=None,
                 easter=None):
        super().__init__(daemon=True)
        self.gpio = gpio
        self.settings = settings
        self.hub = hub
        self.exercise = exercise
        self.reflex = reflex
        self.easter = easter
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
        busy = ((self.exercise and self.exercise.playing)
                or (self.reflex and self.reflex.playing)
                or (self.easter and self.easter.playing))
        if self.sidetone and not busy:
            self.sidetone.set(on)
        now = time.monotonic()
        if on:
            self._on_at = now
        else:
            self._decode_element(now - self._on_at, self._unit)
            self._off_at = now

    def _decode_element(self, dur, unit):
        self._buf += "-" if dur >= 2 * unit else "."

    def _flush_letter(self):
        if self._buf:
            buf = self._buf
            ch = FROM_MORSE.get(buf, "◇")
            if self.exercise and self.exercise.active:
                # during an exercise the decoded letter is the answer
                self.exercise.feed(ch, buf)
            elif self.reflex and self.reflex.active:
                # during the Reflex game the decoded letter is the answer
                self.reflex.feed(ch, buf)
            elif self.easter and self.easter.playing:
                # 6 dots stop the easter-egg message early
                if buf and set(buf) == {"."} and len(buf) >= 6:
                    self.easter.stop()
            elif self.exercise and self.exercise.menu:
                self._menu_select(buf)
            elif self.exercise and buf == "...---...":
                # SOS keyed with no gaps: open the menu, do not print a symbol
                self.exercise.enter_menu()
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
            ex.select(0)              # full drill
        elif buf and set(buf) == {"."}:
            n = len(buf)
            if n == 1:
                # menu item 1: the Reflex game (not a drill)
                ex.cancel()
                if self.reflex:
                    self.reflex.start_game()
            elif 2 <= n <= 10:
                ex.select(n - 1)      # menu number -> drill number
            else:
                ex.cancel()
        else:
            ex.cancel()

    def _check_exercise_trigger(self, buf=None):
        """Start an exercise on SOS (menu) or TEST / TESTn."""
        txt = self.hub.snapshot_text().replace(" ", "").upper()
        if self.reflex and txt.endswith("GAME"):
            self.reflex.start_game()
            return
        if not self.exercise:
            return
        if buf == "...---...":
            self.exercise.enter_menu()
            return
        if txt.endswith("SOS"):
            self.exercise.enter_menu()
            return
        for n in range(9, 0, -1):
            if txt.endswith("TEST%d" % n):
                self.exercise.start_drill(n)
                return
        if txt.endswith("TEST"):
            self.exercise.start_drill(0)

    def run(self):
        dit_mem = dah_mem = False
        last = "dah"
        sending = None
        t_end = t_gap = 0.0
        self._buf = ""
        self._on_at = 0.0
        self._off_at = 0.0
        word_sent = True
        p_dit = p_dah = p_key = False
        prev_dit = prev_dah = False
        queue = []                 # single mode: pending taps
        self._pad_dit = self._pad_dah = False
        snap = getattr(self.settings, "snapshot", None) or self.settings.get
        while not self._stop.is_set():
            now = time.monotonic()
            st = snap()
            unit = 1.2 / st["wpm"]
            if self.exercise and self.exercise.menu:
                # while choosing a program the keyer runs slowly (MENU_WPM)
                unit = 1.2 / MENU_WPM
            elif self.reflex and self.reflex.active:
                # Reflex game: RX and TX share the same speed
                unit = 1.2 / max(1, self.reflex.wpm)
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
            elif mode == "single":
                # Beginner mode: one tap = exactly one element, no memory and
                # no automatic repeat. Taps are queued in press order.
                if dit and not prev_dit and len(queue) < 8:
                    queue.append("dit")
                if dah and not prev_dah and len(queue) < 8:
                    queue.append("dah")
                if sending is not None:
                    if now >= t_end:
                        self._set_key(False)
                        sending = None
                        t_gap = now + unit
                elif queue and now >= t_gap:
                    nxt = queue.pop(0)
                    sending, last = nxt, nxt
                    self._set_key(True)
                    t_end = now + (unit if nxt == "dit" else 3 * unit)
            else:
                # Memory: while in the gap any closed paddle is remembered;
                # while an element is playing only a NEW press counts (rising
                # edge). The old code re-latched the paddle generating the
                # current element, so a normal hold added an extra element
                # (e.g. .- came out as .-.-).
                if sending is None:
                    # Release grace: a small release overshoot past the element
                    # must not add an extra element (see esp32/keyer.py).
                    grace = now - t_end < unit / 2
                    if dit and not (last == "dit" and grace):
                        dit_mem = True
                    if dah and not (last == "dah" and grace):
                        dah_mem = True
                else:
                    if dit and not prev_dit:
                        dit_mem = True
                    if dah and not prev_dah:
                        dah_mem = True

                if sending is not None:
                    if now >= t_end:
                        # never latch the paddle that just sent this element
                        if last == "dit":
                            dit_mem = False
                        else:
                            dah_mem = False
                        if mode == "iambic-a":
                            if not dit:
                                dit_mem = False
                            if not dah:
                                dah_mem = False
                        self._set_key(False)
                        sending = None
                        t_gap = now + unit
                elif now >= t_gap:
                    if dit_mem and dah_mem:
                        nxt = "dah" if last == "dit" else "dit"
                    elif dit_mem:
                        nxt = "dit"
                    elif dah_mem:
                        nxt = "dah"
                    else:
                        nxt = None
                    if nxt:
                        if nxt == "dit":
                            dit_mem = False
                        else:
                            dah_mem = False
                        sending, last = nxt, nxt
                        self._set_key(True)
                        t_end = now + (unit if nxt == "dit" else 3 * unit)
            prev_dit, prev_dah = dit, dah

            # decoder: letter gap 3u, word gap 7u
            if self._buf and not self.key_out and now - self._off_at > 3 * unit:
                self._flush_letter()
                word_sent = False
            if (not self._buf and not word_sent and not self.key_out
                    and now - self._off_at > 7 * unit):
                self.hub.push_text(" ")
                self.hub.broadcast({"t": "txt", "ch": " "})
                if self.screen:
                    self.screen.add_char(" ")
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
                    # a bad setting must never tear down the WebSocket
                    try:
                        data = self.server.settings.patch(msg)
                        _apply_screen(self.server, data)
                        hub.broadcast({"t": "settings", "settings": data},
                                      exclude=conn)
                    except Exception:
                        pass
                elif msg.get("t") == "clear":
                    # 'Clear' on the web UI: wipe the text and the physical
                    # screen too, on every connected client
                    try:
                        hub.clear_text()
                        scr = getattr(self.server, "screen", None)
                        if scr is not None and hasattr(scr, "clear_text"):
                            scr.clear_text()
                        hub.broadcast({"t": "clear"}, exclude=conn)
                    except Exception:
                        pass
        except (ConnectionError, OSError):
            pass
        except Exception:
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
        try:
            data = self.server.settings.patch(patch)
            _apply_screen(self.server, data)
        except Exception:
            data = self.server.settings.get()
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
    if getattr(srv, "sidetone", None) and "buzzer_mode" in data:
        if hasattr(srv.sidetone, "set_mode"):
            srv.sidetone.set_mode(data["buzzer_mode"])
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

    # Reflex game (menu item 1) + hidden easter egg (10 dots + a dash)
    reflex = Reflex(settings, hub, sidetone=sidetone, screen=screen)
    keyer.reflex = reflex
    reflex.start()

    easter = EasterEgg(settings, sidetone=sidetone, screen=screen)
    keyer.easter = easter
    easter.start()

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
