# Minimal WebSocket (RFC 6455) - 1:1 port of the Pi server.py logic.
import binascii
import hashlib
import struct

WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_accept(key):
    sha = hashlib.sha1((key + WS_MAGIC).encode()).digest()
    return binascii.b2a_base64(sha).strip().decode()


def ws_encode(text):
    raw = text.encode("utf-8")
    n = len(raw)
    hdr = bytearray([0x81])
    if n < 126:
        hdr.append(n)
    elif n < 65536:
        hdr.append(126)
        hdr += struct.pack(">H", n)
    else:
        hdr.append(127)
        hdr += struct.pack(">Q", n)
    return bytes(hdr) + raw


async def ws_read_frame(reader):
    """Read one frame from the client. Returns (opcode, payload)."""
    b1 = (await reader.readexactly(1))[0]
    b2 = (await reader.readexactly(1))[0]
    opcode = b1 & 0x0F
    masked = b2 & 0x80
    ln = b2 & 0x7F
    if ln == 126:
        ln = struct.unpack(">H", await reader.readexactly(2))[0]
    elif ln == 127:
        ln = struct.unpack(">Q", await reader.readexactly(8))[0]
    mask = await reader.readexactly(4) if masked else None
    payload = await reader.readexactly(ln) if ln else b""
    if mask and payload:
        payload = bytes(c ^ mask[i & 3] for i, c in enumerate(payload))
    return opcode, payload
