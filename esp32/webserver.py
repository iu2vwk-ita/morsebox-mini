# HTTP + WebSocket web server on native MicroPython sockets (uasyncio).
#
# Routes identical to the Raspberry Pi version:
#   GET  /                  -> static/index.html
#   GET  /style.css /app.js -> files from static/
#   GET  /api/settings      -> settings JSON
#   POST /api/settings      -> patch + broadcast
#   GET  /ws (Upgrade)      -> WebSocket
import json
import uasyncio as asyncio
from config import HTTP_PORT
from hub import Client
from wsproto import ws_accept, ws_encode, ws_read_frame

STATIC_DIR = "static"

MIME = {".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json",
        ".png": "image/png",
        ".svg": "image/svg+xml"}


class WebServer:
    def __init__(self, settings, hub, paddle, on_settings=None, on_clear=None):
        self.settings = settings
        self.hub = hub
        self.paddle = paddle
        self.on_settings = on_settings
        self.on_clear = on_clear

    async def start(self):
        await asyncio.start_server(self._handle, "0.0.0.0", HTTP_PORT)

    # ------------------------------------------------------------ dispatch
    async def _handle(self, reader, writer):
        try:
            req = await self._read_request(reader)
            if req is None:
                return
            method, path, headers, body = req
            if (path == "/ws"
                    and headers.get("upgrade", "").lower() == "websocket"
                    and "sec-websocket-key" in headers):
                await self._serve_ws(reader, writer,
                                     headers["sec-websocket-key"])
                return
            await self._serve_http(method, path, body, writer)
        except (OSError, ValueError):
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass
            try:
                await writer.wait_closed()
            except Exception:
                pass

    # ------------------------------------------------------------ HTTP parsing
    async def _read_request(self, reader):
        line = await reader.readline()
        if not line:
            return None
        parts = line.decode().split()
        if len(parts) < 2:
            return None
        method, path = parts[0], parts[1]
        headers = {}
        while True:
            hline = await reader.readline()
            if not hline or hline == b"\r\n" or hline == b"\n":
                break
            try:
                k, v = hline.decode().split(":", 1)
                headers[k.strip().lower()] = v.strip()
            except ValueError:
                pass
        body = b""
        if method == "POST":
            try:
                ln = int(headers.get("content-length", 0))
            except ValueError:
                ln = 0
            if ln:
                body = await reader.readexactly(ln)
        return method, path, headers, body

    # ------------------------------------------------------------ HTTP routes
    async def _serve_http(self, method, path, body, writer):
        p = path.split("?", 1)[0]
        if method == "GET":
            if p == "/api/settings":
                await self._json(writer, self.settings.get())
                return
            if p in ("/", "/index.html"):
                await self._file(writer, "index.html")
                return
            name = p.lstrip("/")
            if ".." in name or "/" in name or not name:
                await self._not_found(writer)
                return
            await self._file(writer, name)
        elif method == "POST":
            if p != "/api/settings":
                await self._not_found(writer)
                return
            try:
                patch = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                patch = {}
            try:
                data = self.settings.patch(patch)
                if self.on_settings:
                    self.on_settings(data)
            except Exception:
                data = self.settings.get()
            self.hub.broadcast({"t": "settings", "settings": data})
            await self._json(writer, data)
        else:
            await self._not_found(writer)

    async def _file(self, writer, name):
        try:
            with open(STATIC_DIR + "/" + name, "rb") as f:
                raw = f.read()
        except OSError:
            await self._not_found(writer)
            return
        ext = name[name.rfind("."):].lower() if "." in name else ""
        ctype = MIME.get(ext, "application/octet-stream")
        writer.write(("HTTP/1.1 200 OK\r\nContent-Type: %s\r\n"
                      "Content-Length: %d\r\nCache-Control: no-store\r\n"
                      "Connection: close\r\n\r\n" % (ctype, len(raw))).encode())
        writer.write(raw)
        await writer.drain()

    async def _json(self, writer, obj):
        raw = json.dumps(obj).encode()
        writer.write(("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                      "Content-Length: %d\r\nConnection: close\r\n\r\n"
                      % len(raw)).encode())
        writer.write(raw)
        await writer.drain()

    async def _not_found(self, writer):
        raw = b"not found"
        writer.write(("HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n"
                      "Content-Length: %d\r\nConnection: close\r\n\r\n"
                      % len(raw)).encode())
        writer.write(raw)
        await writer.drain()

    # ------------------------------------------------------------ WebSocket
    async def _serve_ws(self, reader, writer, key):
        accept = ws_accept(key)
        writer.write(b"HTTP/1.1 101 Switching Protocols\r\n"
                     b"Upgrade: websocket\r\n"
                     b"Connection: Upgrade\r\n"
                     b"Sec-WebSocket-Accept: " + accept.encode() + b"\r\n\r\n")
        await writer.drain()

        client = Client(writer)
        self.hub.add(client)
        writer_task = asyncio.create_task(self._ws_writer(client))
        try:
            client.send(json.dumps({"t": "hello",
                                    "settings": self.settings.get(),
                                    "text": self.hub.snapshot_text(),
                                    "gpio": self.paddle.backend}))
            while True:
                op, payload = await ws_read_frame(reader)
                if op == 0x8:                       # close
                    break
                if op == 0x9:                       # ping -> pong
                    client.send_raw(b"\x8a\x00")
                    continue
                if op != 0x1:                       # text frames only
                    continue
                try:
                    msg = json.loads(payload.decode("utf-8"))
                except ValueError:
                    continue
                if msg.get("t") == "paddle":
                    self.hub.hold(client, msg.get("dit"), msg.get("dah"),
                                  msg.get("key"))
                elif msg.get("t") == "settings":
                    # a bad setting (e.g. a PWM that refuses a frequency) must
                    # never tear down the WebSocket: catch it and keep going
                    try:
                        data = self.settings.patch(msg)
                        if self.on_settings:
                            self.on_settings(data)
                        # do not echo back to the sender: the sender already
                        # shows its own value and the echo fights the slider
                        self.hub.broadcast({"t": "settings", "settings": data},
                                           exclude=client)
                    except Exception:
                        pass
                elif msg.get("t") == "clear":
                    # 'Clear' on the web UI: wipe the text and the physical
                    # screen too, on every connected client
                    try:
                        self.hub.clear_text()
                        if self.on_clear:
                            self.on_clear()
                        self.hub.broadcast({"t": "clear"}, exclude=client)
                    except Exception:
                        pass
        except (OSError, EOFError):
            pass
        except Exception:
            pass
        finally:
            client.closed = True
            try:
                writer_task.cancel()
            except Exception:
                pass
            self.hub.drop(client)

    async def _ws_writer(self, client):
        while not client.closed:
            if client.queue:
                items = client.queue
                client.queue = []
                try:
                    for item in items:
                        if isinstance(item, bytes):
                            client.writer.write(item)
                        else:
                            client.writer.write(ws_encode(item))
                    await client.writer.drain()
                except OSError:
                    client.closed = True
                    break
            await asyncio.sleep_ms(15)
