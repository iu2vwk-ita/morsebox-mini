# Self-test ON-DEVICE (gira sull'ESP32 con MicroPython).
#
# Esegui con:   mpremote run tests/selftest_device.py
# IMPORTANTE: disabilita prima l'autostart (rinomina main.py in main.py.bak e
# resetta), altrimenti main.py occupa la REPL e la porta 80.
#
# Verifica senza fili GPIO: AP, IP, GPIO, PWM, HTTP, WebSocket, keyer+decoder
# (guidato dai paddle remoti, lo stesso percorso del touch e della tastiera).
import gc
import json
import time
import uasyncio as asyncio

import config
from wifi_ap import start_ap
from settings import Settings
from hub import Hub
from gpio import Paddle
from sidetone import Sidetone
from keyer import Keyer
from webserver import WebServer

PASS = []
FAIL = []


def check(name, cond, extra=""):
    if cond:
        PASS.append(name)
        print("PASS  %-28s %s" % (name, extra))
    else:
        FAIL.append(name)
        print("FAIL  %-28s %s" % (name, extra))


def ws_client_frame(text):
    raw = text.encode()
    mask = b"\x12\x34\x56\x78"
    payload = bytes(c ^ mask[i & 3] for i, c in enumerate(raw))
    n = len(raw)
    hdr = bytearray([0x81])
    if n < 126:
        hdr.append(0x80 | n)
    else:
        hdr.append(0x80 | 126)
        hdr.append(n >> 8)
        hdr.append(n & 0xFF)
    return bytes(hdr) + mask + payload


async def ws_read(reader):
    b1 = (await reader.readexactly(1))[0]
    b2 = (await reader.readexactly(1))[0]
    n = b2 & 0x7F
    if n == 126:
        n = ((await reader.readexactly(1))[0] << 8) | \
            (await reader.readexactly(1))[0]
    elif n == 127:
        n = 0
        for _ in range(8):
            n = (n << 8) | (await reader.readexactly(1))[0]
    payload = await reader.readexactly(n) if n else b""
    return b1 & 0x0F, payload


async def http_get(host, path, method="GET", body=b""):
    reader, writer = await asyncio.open_connection(host, config.HTTP_PORT)
    req = ("%s %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n"
           % (method, path, host)).encode()
    if body:
        req += ("Content-Length: %d\r\n" % len(body)).encode()
    writer.write(req + b"\r\n" + body)
    await writer.drain()
    data = b""
    while True:
        chunk = await reader.read(256)
        if not chunk:
            break
        data += chunk
        if len(data) > 30000:
            break
    writer.close()
    return data


def pwm_duty(pwm):
    try:
        return pwm.duty_u16()
    except Exception:
        try:
            return pwm.duty()
        except Exception:
            return -1


async def run_test(host):
    # ---------------------------------------------------------- rete
    ap = start_ap()
    check("AP attivo", ap.active())
    check("AP IP", ap.ifconfig()[0] == config.AP_IP, ap.ifconfig()[0])
    print("      ifconfig:", ap.ifconfig())
    print("      RAM libera: %d byte" % gc.mem_free())

    # ---------------------------------------------------------- GPIO
    settings = Settings()
    hub = Hub()
    paddle = Paddle()
    r = paddle.read()
    check("GPIO letti (a riposo)", r == (False, False, False), str(r))

    # ---------------------------------------------------------- PWM
    st = Sidetone(config.BUZZ_PINS, freq=settings.get()["tone"])
    check("PWM istanziato", st._ok, "pin %s" % (config.BUZZ_PINS,))
    if st._ok:
        st.set(True)
        time.sleep_ms(20)
        on = pwm_duty(st._pwms[0])
        st.set(False)
        time.sleep_ms(20)
        off = pwm_duty(st._pwms[0])
        check("PWM on/off", on > 0 and off == 0, "on=%s off=%s" % (on, off))
        try:
            f = st._pwms[0].freq()
            check("PWM frequenza", abs(f - settings.get()["tone"]) <= 1,
                  "%s Hz" % f)
        except Exception as e:
            check("PWM frequenza", False, str(e))

    # ---------------------------------------------------------- avvio stack
    settings.patch({"mode": "iambic-a", "wpm": 20})   # A: niente elemento extra
    keyer = Keyer(paddle, settings, hub, sidetone=st)
    server = WebServer(settings, hub, paddle)
    asyncio.create_task(keyer.run())
    asyncio.create_task(server.start())
    await asyncio.sleep_ms(500)

    # ---------------------------------------------------------- HTTP
    r = await http_get(host, "/")
    check("HTTP / -> 200 html",
          r.startswith(b"HTTP/1.1 200") and b"<html" in r.lower())
    r = await http_get(host, "/style.css")
    check("HTTP /style.css", r.startswith(b"HTTP/1.1 200"))
    r = await http_get(host, "/app.js")
    check("HTTP /app.js", r.startswith(b"HTTP/1.1 200"))
    r = await http_get(host, "/api/settings")
    check("HTTP /api/settings", b"iambic-a" in r)
    r = await http_get(host, "/nope")
    check("HTTP 404", b"404" in r)

    # ---------------------------------------------------------- WebSocket
    reader, writer = await asyncio.open_connection(host, config.HTTP_PORT)
    key = "dGhlIHNhbXBsZSBub25jZQ=="
    writer.write(("GET /ws HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
                  "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                  "Sec-WebSocket-Version: 13\r\n\r\n" % (host, key)).encode())
    await writer.drain()
    head = b""
    while b"\r\n\r\n" not in head and len(head) < 4096:
        head += await reader.readexactly(1)
    check("WS 101", b"101 Switching Protocols" in head)

    frames = []

    async def collect():
        try:
            while True:
                op, payload = await ws_read(reader)
                if op == 0x8:
                    break
                frames.append(payload)
        except Exception:
            pass

    ct = asyncio.create_task(collect())
    await asyncio.sleep_ms(150)
    check("WS hello ricevuto",
          any(b"hello" in f for f in frames))

    async def paddle(dit, dah, key, ms):
        writer.write(ws_client_frame(json.dumps(
            {"t": "paddle", "dit": dit, "dah": dah, "key": key})))
        await writer.drain()
        await asyncio.sleep_ms(ms)

    # dit poi dah -> in iambic A = "A"
    await paddle(True, False, False, 40)
    await paddle(False, False, False, 150)
    await paddle(False, True, False, 100)
    await paddle(False, False, False, 500)
    await asyncio.sleep_ms(200)
    ct.cancel()

    txt = ""
    keys = 0
    for f in frames:
        try:
            m = json.loads(f)
        except ValueError:
            continue
        if m.get("t") == "txt":
            txt += m.get("ch", "")
        elif m.get("t") == "key":
            keys += 1
    check("WS eventi key", keys >= 4, "%d eventi" % keys)
    check("keyer decodifica A", txt.strip() == "A", repr(txt))
    writer.close()

    # ---------------------------------------------------------- esito
    print("\n==================== RISULTATO ====================")
    print("PASS: %d   FAIL: %d" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FALLITI:", ", ".join(FAIL))
    print("===================================================")


async def main():
    try:
        await run_test("127.0.0.1")
    except Exception as e:
        import sys
        sys.print_exception(e)
        print("SELF-TEST INTERROTTO:", e)


asyncio.run(main())
