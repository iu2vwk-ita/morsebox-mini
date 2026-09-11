# Keyer iambico A/B + straight + decoder CW.
#
# Port 1:1 della macchina a stati di server.py, ma come coroutine uasyncio
# (sul Pi era un thread). Tick ~1 ms; i tempi sono calcolati con ticks_ms,
# quindi il jitter del loop NON accumula. Il sidetone viene acceso/spento
# direttamente in _set_key: latenza zero.
import time
import uasyncio as asyncio
from morse import FROM_MORSE


class Keyer:
    def __init__(self, paddle, settings, hub, sidetone=None, screen=None):
        self.paddle = paddle
        self.settings = settings
        self.hub = hub
        self.sidetone = sidetone
        self.screen = screen
        self.key_out = False
        self._unit = 60

    # ------------------------------------------------------------ key output
    def _set_key(self, on):
        if on == self.key_out:
            return
        self.key_out = on
        self.hub.broadcast({"t": "key", "on": on,
                            "dit": getattr(self, "_in_dit", False),
                            "dah": getattr(self, "_in_dah", False)})
        if self.sidetone:
            self.sidetone.set(on)
        now = time.ticks_ms()
        if on:
            self._on_at = now
        else:
            self._decode_element(time.ticks_diff(now, self._on_at), self._unit)
            self._off_at = now

    def _decode_element(self, dur, unit):
        self._buf += "-" if dur >= 2 * unit else "."

    def _flush_letter(self):
        if self._buf:
            ch = FROM_MORSE.get(self._buf, "\u25c7")
            self.hub.push_text(ch)
            self.hub.broadcast({"t": "txt", "ch": ch})
            if self.screen:
                self.screen.add_char(ch)
            self._buf = ""

    # ------------------------------------------------------------ loop
    async def run(self):
        dit_mem = dah_mem = False
        last = "dah"
        sending = None
        t_end = t_gap = 0
        self._buf = ""
        self._on_at = 0
        self._off_at = 0
        word_sent = True
        p_dit = p_dah = p_key = False
        self._pad_dit = self._pad_dah = False

        while True:
            now = time.ticks_ms()
            st = self.settings.get()
            unit = 1200 // st["wpm"]          # ms per elemento (dit)
            self._unit = unit
            mode = st["mode"]
            rev = st["reverse"]

            pd, ph, pk = self.paddle.read()
            rd, rh, rk = self.hub.remote()
            # reverse: scambia DIT/DAH su ENTRAMBI gli ingressi (GPIO e touch)
            raw_dit = pd or rd
            raw_dah = ph or rh
            dit = raw_dah if rev else raw_dit
            dah = raw_dit if rev else raw_dah
            skey = pk or rk
            self._in_dit, self._in_dah = dit, dah
            if (dit, dah) != (self._pad_dit, self._pad_dah):
                self._pad_dit, self._pad_dah = dit, dah
                self.hub.broadcast({"t": "pad", "dit": dit, "dah": dah})

            # debounce 5 ms
            if (dit, dah, skey) != (p_dit, p_dah, p_key):
                p_dit, p_dah, p_key = dit, dah, skey
                await asyncio.sleep_ms(5)
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
                if time.ticks_diff(now, t_end) >= 0:
                    # fine elemento: in modo A ricampiona, in B tiene le memorie
                    if mode == "iambic-a":
                        dit_mem, dah_mem = dit, dah
                    self._set_key(False)
                    sending = None
                    t_gap = now + unit
            elif time.ticks_diff(now, t_gap) >= 0:
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

            # decoder: pausa lettera 3u, pausa parola 7u
            if (self._buf and not self.key_out
                    and time.ticks_diff(now, self._off_at) > 3 * unit):
                self._flush_letter()
                word_sent = False
            if (not self._buf and not word_sent and not self.key_out
                    and time.ticks_diff(now, self._off_at) > 7 * unit):
                self.hub.push_text(" ")
                self.hub.broadcast({"t": "txt", "ch": " "})
                word_sent = True

            await asyncio.sleep_ms(1)
