# Iambic A/B + straight keyer + CW decoder.
#
# 1:1 port of the server.py state machine, but as a uasyncio coroutine
# (on the Pi it was a thread). Tick ~1 ms; timing is computed with ticks_ms,
# so loop jitter does NOT accumulate. The sidetone is switched on/off directly
# in _set_key: zero latency.
import time
import uasyncio as asyncio
from config import MENU_WPM
from morse import FROM_MORSE


class Keyer:
    def __init__(self, paddle, settings, hub, sidetone=None, screen=None,
                 exercise=None, easter=None, reflex=None):
        self.paddle = paddle
        self.settings = settings
        self.hub = hub
        self.sidetone = sidetone
        self.screen = screen
        self.exercise = exercise
        self.easter = easter
        self.reflex = reflex
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
            elif self.reflex and self.reflex.active:
                # during the Reflex game the decoded letter is the answer
                self.reflex.feed(ch, buf)
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
            ex.select(0)              # full drill
        elif buf and set(buf) == {"."}:
            n = len(buf)
            if n == 1:
                # menu item 1: the Reflex game (not a drill)
                ex.cancel()
                if self.reflex:
                    self.reflex.start()
            elif 2 <= n <= 10:
                ex.select(n - 1)      # menu number -> drill number
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
        txt = self.hub.snapshot_text().replace(" ", "").upper()
        if self.reflex and txt.endswith("GAME"):
            self.reflex.start()
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
        prev_dit = prev_dah = False
        queue = []                 # single mode: pending taps
        self._pad_dit = self._pad_dah = False
        # snapshot() avoids allocating a dict every millisecond (GC jitter)
        snap = getattr(self.settings, "snapshot", None) or self.settings.get

        while True:
            try:
                now = time.ticks_ms()
                st = snap()
                unit = 1200 // st["wpm"]          # ms per element (dit)
                if self.exercise and self.exercise.menu:
                    # while choosing a program the keyer runs slowly (MENU_WPM)
                    unit = 1200 // MENU_WPM
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
                elif mode == "single":
                    # Beginner mode: one tap = exactly one element, no memory
                    # and no automatic repeat. Taps are queued in the order the
                    # paddles are pressed, so nothing is lost.
                    if dit and not prev_dit and len(queue) < 8:
                        queue.append("dit")
                    if dah and not prev_dah and len(queue) < 8:
                        queue.append("dah")
                    if sending is not None:
                        if time.ticks_diff(now, t_end) >= 0:
                            self._set_key(False)
                            sending = None
                            t_gap = now + unit
                    elif queue and time.ticks_diff(now, t_gap) >= 0:
                        nxt = queue.pop(0)
                        sending, last = nxt, nxt
                        self._set_key(True)
                        t_end = now + (unit if nxt == "dit" else 3 * unit)
                else:
                    # Memory: while in the gap any closed paddle is remembered;
                    # while an element is playing only a NEW press counts (a
                    # rising edge). The old code re-latched the paddle that was
                    # generating the current element, so a normal hold added an
                    # extra element (e.g. .- came out as .-.-).
                    if sending is None:
                        # Release grace: the paddle that just sent an element
                        # must stay closed for at least half a gap before it
                        # counts as "keep going". A small release overshoot
                        # (a few ms past the element) no longer adds an extra
                        # element, which is what broke dot-before-dash words.
                        grace = time.ticks_diff(now, t_end) < unit // 2
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
                        if time.ticks_diff(now, t_end) >= 0:
                            # Never latch the paddle that just sent this
                            # element: a few ms of release overshoot must not
                            # add an extra element. The gap phase re-latches it
                            # only if it is genuinely held (see grace below).
                            if last == "dit":
                                dit_mem = False
                            else:
                                dah_mem = False
                            if mode == "iambic-a":
                                # mode A also forgets a press already released
                                if not dit:
                                    dit_mem = False
                                if not dah:
                                    dah_mem = False
                            self._set_key(False)
                            sending = None
                            t_gap = now + unit
                    elif time.ticks_diff(now, t_gap) >= 0:
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
