# Iambic A/B + straight keyer + CW decoder.
#
# 1:1 port of the server.py state machine, but as a uasyncio coroutine
# (on the Pi it was a thread). Tick ~1 ms; timing is computed with ticks_ms,
# so loop jitter does NOT accumulate. The sidetone is switched on/off directly
# in _set_key: zero latency.
import time
import uasyncio as asyncio
from morse import FROM_MORSE


class Keyer:
    def __init__(self, paddle, settings, hub, sidetone=None, screen=None,
                 exercise=None, easter=None):
        self.paddle = paddle
        self.settings = settings
        self.hub = hub
        self.sidetone = sidetone
        self.screen = screen
        self.exercise = exercise
        self.easter = easter
        self.key_out = False
        self._unit = 60
        self._dot_run = 0

    # ------------------------------------------------------------ key output
    def _set_key(self, on):
        if on == self.key_out:
            return
        self.key_out = on
        self.hub.broadcast({"t": "key", "on": on,
                            "dit": getattr(self, "_in_dit", False),
                            "dah": getattr(self, "_in_dah", False)})
        busy = ((self.exercise and self.exercise.playing)
                or (self.easter and self.easter.playing))
        if self.sidetone and not busy:
            self.sidetone.set(on)
        now = time.ticks_ms()
        if on:
            self._on_at = now
        else:
            self._decode_element(time.ticks_diff(now, self._on_at), self._unit)
            self._off_at = now

    def _decode_element(self, dur, unit):
        el = "-" if dur >= 2 * unit else "."
        self._buf += el
        # hidden easter egg: 10 dots followed by a dash
        if el == ".":
            self._dot_run += 1
        else:
            if self._dot_run >= 10:
                self._dot_run = 0
                self._buf = ""
                if self.easter:
                    self.easter.fire()
                return
            self._dot_run = 0

    def _flush_letter(self):
        self._dot_run = 0          # the 10-dot run must be within one letter
        if self._buf:
            buf = self._buf
            ch = FROM_MORSE.get(buf, "\u25c7")
            if self.exercise and self.exercise.active:
                # during an exercise the decoded letter is the answer
                self.exercise.feed(ch, buf)
            elif self.exercise and self.exercise.menu:
                # exercise menu: pick the drill with dots / a dash
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
            ex.select(0)
        elif buf and set(buf) == {"."}:
            n = len(buf)
            if 1 <= n <= 9:
                ex.select(n)
            else:
                ex.cancel()
        else:
            # invalid input (e.g. dots + a dash): exit the menu, clear the LCD
            ex.cancel()

    def _check_exercise_trigger(self, buf=None):
        """Start an exercise on SOS (menu) or TEST / TESTn.

        Spaces are ignored, so a slow S O S (with word gaps) still works, and
        SOS keyed with no gaps at all is detected from the raw elements.
        """
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
        # snapshot() avoids allocating a dict every millisecond (GC jitter)
        snap = getattr(self.settings, "snapshot", None) or self.settings.get

        while True:
            try:
                now = time.ticks_ms()
                st = snap()
                unit = 1200 // st["wpm"]          # ms per element (dit)
                self._unit = unit
                mode = st["mode"]
                rev = st["reverse"]

                pd, ph, pk = self.paddle.read()
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
                    await asyncio.sleep_ms(2)
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
                        # end of element: mode A resamples, mode B keeps the memory
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

                # decoder: letter gap 3u, word gap 7u
                if (self._buf and not self.key_out
                        and time.ticks_diff(now, self._off_at) > 3 * unit):
                    self._flush_letter()
                    word_sent = False
                if (not self._buf and not word_sent and not self.key_out
                        and time.ticks_diff(now, self._off_at) > 7 * unit):
                    self.hub.push_text(" ")
                    self.hub.broadcast({"t": "txt", "ch": " "})
                    if self.screen:
                        self.screen.add_char(" ")
                    word_sent = True

                await asyncio.sleep_ms(1)
            except Exception as e:
                # a decoding error must not stop the keyer
                print("keyer error:", e)
                await asyncio.sleep_ms(50)
