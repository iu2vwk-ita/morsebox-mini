import os
import sys
import time
import asyncio

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, PROJECT)

# MicroPython time API on top of CPython's time
time.ticks_ms = lambda: int(time.monotonic() * 1000) & 0x3FFFFFFF
time.ticks_diff = lambda a, b: a - b

import keyer          # noqa: E402
import wsproto        # noqa: E402
import webserver      # noqa: E402
import machine as machine_mod      # noqa: E402
import sidetone as sidetone_mod    # noqa: E402

webserver.STATIC_DIR = os.path.join(PROJECT, "static")
import settings as settings_mod  # noqa: E402
from morse import FROM_MORSE     # noqa: E402


class FakePaddle:
    backend = "test"

    def __init__(self):
        self.dit = self.dah = self.key = False

    def read(self):
        return (self.dit, self.dah, self.key)


class FakeSettings:
    def __init__(self, **kw):
        self.d = {"wpm": 20, "reverse": False, "mode": "iambic-b",
                  "tone": 650, "buzzer": False, "volume": 70}
        self.d.update(kw)

    def get(self):
        return dict(self.d)


class FakeHub:
    def __init__(self):
        self.events = []
        self.history = ""
        self.clients = []

    def add(self, c):
        self.clients.append(c)

    def drop(self, c):
        pass

    def snapshot_text(self):
        return self.history

    def broadcast(self, m, exclude=None):
        self.events.append(m)

    def clear_text(self):
        self.history = ""

    def push_text(self, ch):
        self.history += ch

    def remote(self):
        return (False, False, False)


async def scenario_letter(paddle, hub, settings):
    k = keyer.Keyer(paddle, settings, hub)
    task = asyncio.create_task(k.run())
    await asyncio.sleep(0.02)
    # dit: hold 40 ms (the element still lasts 1 unit = 60 ms)
    paddle.dit = True
    await asyncio.sleep(0.04)
    paddle.dit = False
    await asyncio.sleep(0.10)
    # dah: hold 100 ms (element = 3 units = 180 ms)
    paddle.dah = True
    await asyncio.sleep(0.10)
    paddle.dah = False
    await asyncio.sleep(0.50)
    task.cancel()


async def scenario_tap(paddle, hub, settings):
    k = keyer.Keyer(paddle, settings, hub)
    task = asyncio.create_task(k.run())
    await asyncio.sleep(0.02)
    paddle.dit = True
    await asyncio.sleep(0.04)
    paddle.dit = False
    await asyncio.sleep(0.60)
    task.cancel()


async def scenario_straight(paddle, hub):
    st = FakeSettings(mode="straight")
    k = keyer.Keyer(paddle, st, hub)
    task = asyncio.create_task(k.run())
    await asyncio.sleep(0.02)
    paddle.key = True
    await asyncio.sleep(0.15)
    paddle.key = False
    await asyncio.sleep(0.05)
    task.cancel()


async def main():
    # ---- 1. iambic A keyer: dit + dah = "A" (mode A has no extra memory)
    p, h, s = FakePaddle(), FakeHub(), FakeSettings(mode="iambic-a")
    await scenario_letter(p, h, s)
    assert h.history.strip() == "A", "expected A, got %r" % h.history
    key_events = [e for e in h.events if e.get("t") == "key"]
    assert any(e["on"] for e in key_events), "no key on"
    print("PASS keyer iambic A: dit+dah -> 'A' (%d key events)"
          % len(key_events))

    # ---- 1b. iambic B keyer: a dit tap adds one element (mode B memory)
    pb, hb = FakePaddle(), FakeHub()
    await scenario_tap(pb, hb, FakeSettings(mode="iambic-b"))
    assert hb.history.strip() == "I", "iambic B: expected I, got %r" % hb.history
    print("PASS keyer iambic B: dit tap -> '..' (mode B memory)")

    # ---- 1c. iambic A keyer: a dit tap does NOT add elements
    pa, ha = FakePaddle(), FakeHub()
    await scenario_tap(pa, ha, FakeSettings(mode="iambic-a"))
    assert ha.history.strip() == "E", "iambic A: expected E, got %r" % ha.history
    print("PASS keyer iambic A: dit tap -> '.'")

    # ---- 2. reverse keyer: with reverse, the dit contact sends a dah
    p2, h2 = FakePaddle(), FakeHub()
    s2 = FakeSettings(reverse=True, mode="iambic-a")
    k2 = keyer.Keyer(p2, s2, h2)
    t2 = asyncio.create_task(k2.run())
    await asyncio.sleep(0.02)
    p2.dit = True
    await asyncio.sleep(0.10)
    p2.dit = False
    await asyncio.sleep(0.35)
    t2.cancel()
    assert h2.history.strip() == "T", "reverse: expected T, got %r" % h2.history
    print("PASS keyer reverse: dit contact -> dah -> 'T'")

    # ---- 3. straight mode
    p3, h3 = FakePaddle(), FakeHub()
    await scenario_straight(p3, h3)
    k3_events = [e for e in h3.events if e.get("t") == "key"]
    assert k3_events and k3_events[0]["on"], "straight: no key on"
    assert not k3_events[-1]["on"], "straight: key not released"
    print("PASS keyer straight: correct key on/off")

    # ---- 3b. exercise: trigger TEST/TESTn + answer routing
    class FakeExercise:
        def __init__(self):
            self.active = False
            self.menu = False
            self.pending = None
            self.started = None
            self.playing = False
            self.fed = []

        def start(self, n):
            self.started = n
            self.active = True

        def enter_menu(self):
            self.menu = True
            self.pending = None

        def select(self, n):
            self.pending = n

        def confirm(self):
            if self.pending is not None:
                self.start(self.pending)

        def cancel(self):
            self.pending = None
            self.menu = False

        def feed(self, ch, buf):
            self.fed.append((ch, buf))

    ex = FakeExercise()
    pe, he = FakePaddle(), FakeHub()
    ke = keyer.Keyer(pe, FakeSettings(), he, exercise=ex)
    he.history = "QSO TEST1"
    ke._check_exercise_trigger()
    assert ex.started == 1, ex.started
    ex.started = None
    he.history = "TEST"
    ke._check_exercise_trigger()
    assert ex.started == 0, ex.started
    ex.active = True
    ke._buf = ".-"
    ke._flush_letter()
    assert ex.fed and ex.fed[-1] == ("A", ".-"), ex.fed
    assert he.history == "TEST"          # not pushed to the normal text
    print("PASS exercise: trigger TEST/TESTn + answer routing")

    # SOS enters the menu, N dots select, .. confirms, -- exits
    ex.active = False
    ex.menu = False
    ex.started = None
    he.history = "QSO SOS"
    ke._check_exercise_trigger()
    assert ex.menu is True
    # slow S O S (with word gaps) and raw ...---... must both work
    ex.menu = False
    he.history = "S O S"
    ke._check_exercise_trigger()
    assert ex.menu is True
    ex.menu = False
    ke._check_exercise_trigger("...---...")
    assert ex.menu is True
    ke._menu_select("..")               # select exercise 2
    assert ex.pending == 2, ex.pending
    assert ex.started is None
    ke._menu_select("..")               # confirm
    assert ex.started == 2, ex.started
    ex.started = None
    ex.pending = None
    ke._menu_select("-")                # full drill
    assert ex.pending == 0, ex.pending
    ke._menu_select("--")               # exit
    assert ex.menu is False and ex.pending is None
    print("PASS exercise: SOS menu + select + ..confirm / --exit")

    # ---- 3c. exercise feed: split STOP/SKIP still detected
    import exercise as exmod

    class _S:
        def get(self):
            return {"wpm": 20}

    class _H:
        def broadcast(self, m):
            pass

    exr = exmod.Exercise(_S(), _H())
    exr.start(1)
    exr._target = "A"
    exr.feed("?", "......")              # single group of 6 dots -> STOP
    assert exr._answer == "__STOP__", exr._answer

    exr2 = exmod.Exercise(_S(), _H())
    exr2.start(1)
    exr2._target = "A"
    exr2.feed("?", "------")             # single group of 6 dashes -> SKIP
    assert exr2._answer == "__SKIP__", exr2._answer

    # two wrong 'S' answers must NOT stop the course
    exr6 = exmod.Exercise(_S(), _H())
    exr6.start(1)
    exr6._target = "A"
    exr6.feed("S", "...")
    exr6._got = False
    exr6._answer = None
    exr6.feed("S", "...")
    assert exr6._answer != "__STOP__", exr6._answer

    exr3 = exmod.Exercise(_S(), _H())
    exr3.start(2)
    exr3._target = "5"
    exr3.feed("5", ".....")              # 5 dots is an answer, not STOP
    assert exr3._answer == "5", exr3._answer

    # per-letter progress on a callsign-like target
    exr4 = exmod.Exercise(_S(), _H())
    exr4.start(7)
    exr4._target = "CQ"
    exr4.feed("C", ".-.-.")
    assert exr4._pos == 1 and exr4._got is False
    exr4.feed("Q", "--.-")
    assert exr4._answer == "CQ" and exr4._got
    exr5 = exmod.Exercise(_S(), _H())
    exr5.start(7)
    exr5._target = "CQ"
    exr5.feed("C", ".-.-.")
    exr5.feed("X", "-..-")               # wrong -> restart the target
    assert exr5._pos == 0
    assert exr5._replay is True
    print("PASS exercise feed: split STOP/SKIP + 5-dot answer + per-letter")

    # menu: SOS -> select -> confirm / cancel
    exm = exmod.Exercise(_S(), _H())
    exm.enter_menu()
    assert exm.menu is True and exm.pending is None and exm.active is False
    exm.select(3)
    assert exm.pending == 3 and exm.menu is True
    exm.confirm()
    assert exm.active is True and exm.pending is None and exm.menu is False
    assert exm.name == "KOCH" and len(exm.targets) == 36
    exm2 = exmod.Exercise(_S(), _H())
    exm2.enter_menu()
    exm2.select(5)
    exm2.cancel()
    assert exm2.menu is False and exm2.pending is None and exm2.active is False
    print("PASS exercise: menu/select/confirm/cancel")

    # drill lists
    assert len(exmod.build(0)) == 36      # full A-Z + 0-9
    assert len(exmod.build(1)) == 26      # alphabet
    assert len(exmod.build(2)) == 10      # numbers
    assert len(exmod.build(3)) == 36      # Koch
    assert len(exmod.build(4)) == 20
    assert len(exmod.build(5)) == 20
    assert len(exmod.build(6)) == 20
    assert exmod.build(7)[0] == "I1ABC"
    assert "CQ" in exmod.build(8)
    assert "." in exmod.build(9)
    print("PASS exercise: drill lists (build)")

    # run loop: start, answer correctly, it advances
    async def _ex_run():
        exr7 = exmod.Exercise(_S(), _H())
        exr7.start(1)
        task = asyncio.create_task(exr7.run())
        for _ in range(100):
            if exr7._target:
                break
            await asyncio.sleep(0.01)
        assert exr7._target == "A", exr7._target
        exr7.feed("A", ".-")
        await asyncio.sleep(0.1)
        assert exr7.index == 1 and exr7.score == 1, (exr7.index, exr7.score)
        task.cancel()

    await _ex_run()
    print("PASS exercise: run loop advances on a correct answer")

    # ---- 4. WS accept (RFC 6455 vector)
    acc = wsproto.ws_accept("dGhlIHNhbXBsZSBub25jZQ==")
    assert acc == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=", acc
    print("PASS WebSocket handshake:", acc)

    # ---- 5. WS encode (short + 16-bit)
    assert wsproto.ws_encode("hi") == b"\x81\x02hi"
    long = "x" * 200
    frame = wsproto.ws_encode(long)
    assert frame[0] == 0x81 and frame[1] == 126
    assert frame[2:4] == b"\x00\xc8" and frame[4:] == long.encode()
    print("PASS WebSocket encode short + 16-bit")

    # ---- 6. WS decode masked frame
    class FakeReader:
        def __init__(self, data):
            self.data = data

        async def readexactly(self, n):
            out, self.data = self.data[:n], self.data[n:]
            return out

    payload = b'{"t":"paddle","dit":true}'
    mask = b"\x37\xfa\x21\x3d"
    masked = bytes(c ^ mask[i & 3] for i, c in enumerate(payload))
    frame = bytes([0x81, 0x80 | len(payload)]) + mask + masked
    op, dec = await wsproto.ws_read_frame(FakeReader(frame))
    assert op == 0x1 and dec == payload, (op, dec)
    print("PASS WebSocket decode masked frame")

    # ---- 7. settings clamp (real module)
    s = settings_mod.Settings()
    d = s.patch({"wpm": 999, "tone": 10, "volume": -5, "mode": "bogus"})
    assert d["wpm"] == 60 and d["tone"] == 500 and d["volume"] == 0
    assert d["mode"] == "iambic-b"
    os.remove("settings.json")
    print("PASS settings clamp")

    # ---- 8. morse table
    assert FROM_MORSE[".-"] == "A" and FROM_MORSE["..."] == "S"
    print("PASS morse FROM_MORSE")

    # ---- 8b. sidetone robustness: a PWM that refuses a frequency change
    machine_mod.PWM.fail_freq = False
    machine_mod.PWM.fail_ctor = False
    st = sidetone_mod.Sidetone([25, 26, 27], freq=650)
    assert len(st._pwms) == 3 and st._ok
    st.set_freq(700)
    assert st.freq == 700 and not any(p.deinited for p in st._pwms)
    # freq() fails AND the rebuild fails: keep the old PWM, never crash
    machine_mod.PWM.fail_freq = True
    machine_mod.PWM.fail_ctor = True
    st.set_freq(800)                       # must not raise
    assert st.freq == 700                  # not applied, old note kept
    assert len(st._pwms) == 3 and not any(p.deinited for p in st._pwms)
    st.set(True)
    st.set(False)                          # must not raise on a stuck PWM
    # freq() fails but the rebuild works: the new note is applied
    machine_mod.PWM.fail_ctor = False
    st.set_freq(850)
    assert st.freq == 850 and not any(p.deinited for p in st._pwms)
    machine_mod.PWM.fail_freq = False
    print("PASS sidetone robustness (freq fallback)")

    # ---- 9. web server: parsing, routes, WS handshake
    class FakeWriter:
        def __init__(self):
            self.data = b""
            self.closed = False

        def write(self, b):
            self.data += b

        async def drain(self):
            pass

        def close(self):
            self.closed = True

    class FakeReqReader:
        def __init__(self, data):
            self.data = data

        async def readline(self):
            i = self.data.find(b"\n")
            if i < 0:
                out, self.data = self.data, b""
                return out
            out, self.data = self.data[:i + 1], self.data[i + 1:]
            return out

        async def readexactly(self, n):
            out, self.data = self.data[:n], self.data[n:]
            return out

    class FakePaddleBackend:
        backend = "esp32"

    srv = webserver.WebServer(s, FakeHub(), FakePaddleBackend())

    w = FakeWriter()
    await srv._serve_http("GET", "/index.html", b"", w)
    assert w.data.startswith(b"HTTP/1.1 200") and b"<html" in w.data.lower()
    print("PASS web: GET /index.html")

    w = FakeWriter()
    await srv._serve_http("GET", "/app.js", b"", w)
    assert w.data.startswith(b"HTTP/1.1 200") and b"javascript" in w.data
    print("PASS web: GET /app.js")

    w = FakeWriter()
    await srv._serve_http("GET", "/api/settings", b"", w)
    assert b"application/json" in w.data and b"iambic-b" in w.data
    print("PASS web: GET /api/settings")

    w = FakeWriter()
    await srv._serve_http("GET", "/../config.py", b"", w)
    assert b"404" in w.data
    print("PASS web: path traversal -> 404")

    r = FakeReqReader(b"GET /ws HTTP/1.1\r\nHost: x\r\n"
                      b"Upgrade: websocket\r\n"
                      b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n")
    method, path, headers, body = await srv._read_request(r)
    assert method == "GET" and path == "/ws"
    assert headers["upgrade"] == "websocket" and body == b""
    print("PASS web: WS request parsing")

    w = FakeWriter()
    r = FakeReqReader(bytes([0x88, 0x00]))   # unmasked close frame
    await srv._serve_ws(r, w, "dGhlIHNhbXBsZSBub25jZQ==")
    assert b"101 Switching Protocols" in w.data
    assert b"s3pPLMBiTxaQ9kYGzzhZRbK+xOo=" in w.data
    print("PASS web: 101 handshake + Sec-WebSocket-Accept")

    # ---- 11. clear: wipe hub text + physical screen, notify the other clients
    calls = []
    hub2 = FakeHub()
    hub2.history = "ABC"
    srv2 = webserver.WebServer(s, hub2, FakePaddleBackend(),
                               on_clear=lambda: calls.append(1))
    payload = b'{"t":"clear"}'
    mask = b"\x01\x02\x03\x04"
    masked = bytes(c ^ mask[i & 3] for i, c in enumerate(payload))
    frame = bytes([0x81, 0x80 | len(payload)]) + mask + masked
    w = FakeWriter()
    await srv2._serve_ws(FakeReqReader(frame), w, "dGhlIHNhbXBsZSBub25jZQ==")
    assert calls == [1], calls
    assert hub2.snapshot_text() == ""
    assert any(e.get("t") == "clear" for e in hub2.events)
    print("PASS clear: screen + hub text wiped, peers notified")

    print("\nALL TESTS PASSED")


asyncio.run(main())
