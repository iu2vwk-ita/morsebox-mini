# CW-School / MorseBox exercise mode.
#
# Start by keying TEST (full drill) or TEST1..TEST9. The device SHOWS the
# target on the LCD and PLAYS it on the piezo (always both, together), then
# waits for the student to key it back.
#
# Controls (keyed, not valid characters):
#   ......  (6 dots)   = STOP
#   ------  (6 dashes) = SKIP
import random
import time
import uasyncio as asyncio
from morse import MORSE

# Koch learning order (letters + digits)
KOCH = list("KMRSUAPTLOWINJEFYV0G5Q9ZH38B427C1D6X")
CALLSIGNS = ["I1ABC", "IU2VWK", "IK2XYZ", "DL1ABC", "K1ABC",
             "F5XYZ", "EA5ABC", "G3XYZ", "JA1ABC", "VE3ABC"]
ABBREV = ["CQ", "DE", "QTH", "QSL", "QRZ", "RST", "73", "88",
          "OM", "YL", "FB", "PSE", "TNX", "GL", "GB"]
PUNCT = [".", ",", "?", "/", "=", "+", "AR", "SK", "BT"]

NAMES = {0: "FULL", 1: "ALPHABET", 2: "NUMBERS", 3: "KOCH",
         4: "LETTERS", 5: "DIGITS", 6: "MIXED", 7: "CALLSIGNS",
         8: "ABBREV", 9: "PUNCT"}

STOP_SEQ = "......"
SKIP_SEQ = "------"


def build(n):
    """Return the list of targets for exercise n (0..9)."""
    if n == 1:
        return list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    if n == 2:
        return list("0123456789")
    if n == 3:
        return list(KOCH)
    if n == 4:
        return [random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(20)]
    if n == 5:
        return [random.choice("0123456789") for _ in range(20)]
    if n == 6:
        return [random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
                for _ in range(20)]
    if n == 7:
        return list(CALLSIGNS)
    if n == 8:
        return list(ABBREV)
    if n == 9:
        return list(PUNCT)
    # 0 = full drill: A-Z then 0-9
    return list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


class Exercise:
    """Runs the exercise state machine as an asyncio task."""

    def __init__(self, settings, hub, sidetone=None, screen=None):
        self.settings = settings
        self.hub = hub
        self.sidetone = sidetone
        self.screen = screen
        self.active = False
        self.menu = False
        self.pending = None
        self.playing = False
        self.name = ""
        self.targets = []
        self.index = 0
        self.score = 0
        self._target = ""
        self._typed = ""
        self._answer = None
        self._got = False
        self._pos = 0              # current character inside the target
        self._blink = True         # blink phase for the character to key
        self._run_char = None      # last run of dots/dashes (for STOP/SKIP)
        self._run_len = 0
        self._run_at = 0

    # ---------------------------------------------------------- control
    def enter_menu(self):
        """SOS was keyed: wait for the student to pick an exercise."""
        self.active = False
        self.menu = True
        self.pending = None
        self._menu_at = time.ticks_ms()
        self._menu_show()
        self.hub.broadcast({"t": "ex", "on": False, "menu": True})

    def _menu_show(self):
        if not self.screen or not hasattr(self.screen, "set_exercise"):
            return
        if self.pending is None:
            # clear, explicit prompt: how many dots?
            self.screen.set_exercise("MENU", "DOTS 1-9 ?")
        else:
            label = "FULL" if self.pending == 0 else "EX %d" % self.pending
            self.screen.set_exercise(label + " ?", ".. OK  -- NO")

    def select(self, n):
        """A drill was picked: ask for confirmation (.. = yes, -- = exit)."""
        self.pending = n
        self._menu_at = time.ticks_ms()
        self._menu_show()

    def confirm(self):
        if self.pending is not None:
            self.start(self.pending)

    def cancel(self):
        self.pending = None
        self.menu = False
        self._clear()

    def start(self, n):
        self.menu = False
        self.pending = None
        self.targets = build(n)
        self.name = NAMES.get(n, "EX")
        self.index = 0
        self.score = 0
        self._typed = ""
        self._answer = None
        self._got = False
        self.active = True
        self._broadcast()

    def feed(self, ch, buf):
        """Called by the keyer on every decoded letter while active.

        STOP/SKIP are counted as a RUN of dots/dashes, so they still work when
        the decoder splits 6 elements into two groups (e.g. '...' + '...').
        """
        if not self.active:
            return
        now = time.ticks_ms()
        c = None
        if buf:
            s = set(buf)
            if s == {"."}:
                c = "."
            elif s == {"-"}:
                c = "-"
        if c:
            if self._run_char == c and time.ticks_diff(now, self._run_at) < 1500:
                self._run_len += len(buf)
            else:
                self._run_char, self._run_len = c, len(buf)
            self._run_at = now
            if c == "." and self._run_len >= 6:
                self._answer = "__STOP__"
                self._got = True
                return
            if c == "-" and self._run_len >= 6:
                self._answer = "__SKIP__"
                self._got = True
                return
        else:
            self._run_char = None
            self._run_len = 0
        # per-character progress: key the target one letter at a time
        if self._pos < len(self._target) and ch and \
                ch.upper() == self._target[self._pos].upper():
            self._pos += 1
            self._blink = True
            if self._pos >= len(self._target):
                self._answer = self._target
                self._got = True
        else:
            self._pos = 0          # wrong letter: start the target over

    # ---------------------------------------------------------- helpers
    def _broadcast(self):
        self.hub.broadcast({"t": "ex", "on": self.active, "name": self.name,
                            "index": self.index, "total": len(self.targets),
                            "score": self.score})

    def _show(self):
        if not self.screen or not hasattr(self.screen, "set_exercise"):
            return
        total = len(self.targets)
        line1 = "%s %d/%d" % (self.name, self.index + 1, total)
        # show the whole target; the character to key blinks between the
        # letter and an underscore
        if self._pos < len(self._target):
            if self._blink:
                line2 = self._target
            else:
                line2 = (self._target[:self._pos] + "_" +
                         self._target[self._pos + 1:])
        else:
            line2 = self._target
        self.screen.set_exercise(line1, line2)

    async def _play(self, text):
        if not self.sidetone:
            return
        self.playing = True
        try:
            unit = max(20, 1200 // int(self.settings.get()["wpm"]))
            for ch in text.upper():
                code = MORSE.get(ch)
                if not code:
                    continue
                for el in code:
                    self.sidetone.set(True)
                    await asyncio.sleep_ms(unit if el == "." else 3 * unit)
                    self.sidetone.set(False)
                    await asyncio.sleep_ms(unit)
                await asyncio.sleep_ms(2 * unit)   # letter gap
            await asyncio.sleep_ms(2 * unit)
        finally:
            self.sidetone.set(False)
            self.playing = False

    def _finish(self):
        if self.screen and hasattr(self.screen, "set_exercise"):
            total = len(self.targets)
            self.screen.set_exercise("DONE %d/%d" % (self.score, total),
                                     self.name)
        self._broadcast()

    def _clear(self):
        if self.screen and hasattr(self.screen, "clear_exercise"):
            self.screen.clear_exercise()

    # ---------------------------------------------------------- task
    async def run(self):
        while True:
            if not self.active:
                if self.menu and time.ticks_diff(
                        time.ticks_ms(), self._menu_at) > 8000:
                    self.menu = False
                    self._clear()
                await asyncio.sleep_ms(100)
                continue
            self._target = self.targets[self.index]
            self._typed = ""
            self._pos = 0
            self._blink = True
            self._answer = None
            self._got = False
            self._show()
            await self._play(self._target)

            last_blink = time.ticks_ms()
            while self.active and not self._got:
                if time.ticks_diff(time.ticks_ms(), last_blink) > 350:
                    last_blink = time.ticks_ms()
                    self._blink = not self._blink
                    self._show()
                await asyncio.sleep_ms(20)
            if not self.active:
                continue

            ans = self._answer
            if ans == "__STOP__":
                self.active = False
                self._finish()
                await asyncio.sleep_ms(3000)
                self._clear()
                continue
            if ans == "__SKIP__":
                self.index += 1
                self._run_char = None
                self._run_len = 0
            elif ans and ans.upper() == self._target.upper():
                self.score += 1
                self.index += 1
                self._run_char = None
                self._run_len = 0
            # wrong answer: repeat the same target (keep the dot/dash run so a
            # STOP/SKIP split across two groups still accumulates)

            if self.index >= len(self.targets):
                self.active = False
                self._finish()
                await asyncio.sleep_ms(3000)
                self._clear()
            else:
                self._broadcast()
