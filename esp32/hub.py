# Hub: WebSocket client registry, remote holds, text history.
#
# Everything runs in the single uasyncio event loop: no locks, no threads.
# broadcast() NEVER blocks the keyer: it queues the JSON string per client and
# each client's writer drains it. Slow client = full queue = dropped.
import json
import time
from config import HOLD_TIMEOUT_MS

QUEUE_MAX = 64


class Client:
    def __init__(self, writer):
        self.writer = writer
        self.queue = []
        self.closed = False

    def send(self, msg):
        if self.closed:
            return
        if len(self.queue) < QUEUE_MAX:
            self.queue.append(msg)
        else:
            # client too slow: drop it, the keyer must keep running
            self.closed = True

    def send_raw(self, raw):
        if not self.closed and len(self.queue) < QUEUE_MAX:
            self.queue.append(raw)


class Hub:
    def __init__(self):
        self.clients = []
        self.holds = {}          # id(client) -> {dit,dah,key,ts}
        self.history = ""

    # ---------------------------------------------------------- clients
    def add(self, client):
        self.clients.append(client)

    def drop(self, client):
        client.closed = True
        try:
            self.clients.remove(client)
        except ValueError:
            pass
        self.holds.pop(id(client), None)

    # ---------------------------------------------------------- remote paddles
    def hold(self, client, dit, dah, key):
        self.holds[id(client)] = {"dit": bool(dit), "dah": bool(dah),
                                  "key": bool(key), "ts": time.ticks_ms()}

    def remote(self):
        now = time.ticks_ms()
        d = h = k = False
        for cid in list(self.holds):
            v = self.holds[cid]
            if time.ticks_diff(now, v["ts"]) < HOLD_TIMEOUT_MS:
                d = d or v["dit"]
                h = h or v["dah"]
                k = k or v["key"]
            else:
                del self.holds[cid]
        return d, h, k

    # ---------------------------------------------------------- text
    def push_text(self, ch):
        self.history = (self.history + ch)[-120:]

    def snapshot_text(self):
        return self.history

    def clear_text(self):
        self.history = ""

    # ---------------------------------------------------------- broadcast
    def broadcast(self, msg, exclude=None):
        raw = json.dumps(msg)
        for c in self.clients:
            if c is exclude:
                continue
            c.send(raw)
