# MorseBox exercise mode.
#
# Open the menu with SOS, then pick a drill with N dots and confirm with "..":
#   SOS                  = open the menu
#   . .. ... ...         = choose exercise 1..9 (a single dash = full drill)
#   ..                   = confirm / start
#   --                   = exit the menu
# During a drill:
#   ......  (6 dots)     = STOP
#   ------  (6 dashes)   = SKIP
#
# The device SHOWS the target on the LCD and PLAYS it on the piezo (always
# both, together) at the chosen WPM, then waits for the student to key it back.
# For multi-letter targets the whole word is shown and the letter to key blinks.
# You can also start directly with TEST (full drill) or TEST1..TEST9.
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

# Menu: scrolled on the display so you can read the courses before choosing.
# Menu item 1 is the Reflex game; the courses are shifted by one (2..10).
MENU_LIST = "1 GAME   "
MENU_LIST += "   ".join(["%d %s" % (n + 1, NAMES[n]) for n in range(1, 10)])
MENU_LIST += "   - FULL   "
MENU_HINT = "1-10 ..=ok --=no"
MENU_SCROLL_MS = 320
MENU_TIMEOUT_MS = 20000


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
        self._answer = None
        self._got = False
        self._pos = 0              # current character inside the target
        self._replay = False       # a wrong letter asks to replay the target
        self._scroll_off = 0       # menu: scrolling offset of the course list
        self._scroll_at = 0

    # ---------------------------------------------------------- control
    def enter_menu(self):
        """SOS was keyed: wait for the student to pick an exercise."""
        self.active = False
        self.menu = True
        self.pending = None
        self._menu_at = time.ticks_ms()
        self._scroll_off = 0
        self._scroll_at = time.ticks_ms()
        # clear the decoded text so SOS does not fire again right away
        if hasattr(self.hub, "clear_text"):
            self.hub.clear_text()
        self._menu_show()
        self.hub.broadcast({"t": "ex", "on": False, "menu": True})

    def _menu_show(self):
        if not self.screen or not hasattr(self.screen, "set_exercise"):
            return
        if self.pending is None:
            self._menu_scroll()
        elif self.pending == 0:
            self.screen.set_exercise("- FULL ?", ".. OK  -- NO")
        else:
            # show the menu number + name (2 ALPHABET, 4 KOCH, ...)
            self.screen.set_exercise(
                "%d %s ?" % (self.pending + 1, NAMES.get(self.pending, "EX")),
                ".. OK  -- NO")

    def _menu_scroll(self):
        """One 16-char window of the course list; the task advances it."""
        if not self.screen or not hasattr(self.screen, "set_exercise"):
            return
        text = MENU_LIST
        off = self._scroll_off % len(text)
        window = (text + text)[off:off + 16]
        self.screen.set_exercise(window, MENU_HINT)

    def select(self, n):
        """A drill was picked: ask for confirmation (.. = yes, -- = exit)."""
        self.pending = n
        self._menu_at = time.ticks_ms()
        self._menu_show()

    def confirm(self):
        if self.pending is not None:
            self.start(self.pending)

    def cancel(self):
        if self.pending is not None:
            # "no" on the confirm screen: back to the scrolling course list
            self.pending = None
            self._scroll_off = 0
            self._scroll_at = time.ticks_ms()
            self._menu_show()
        else:
            self.menu = False
            self._clear()

    def start(self, n):
        self.menu = False
        self.pending = None
        self.targets = build(n)
        self.name = NAMES.get(n, "EX")
        self.index = 0
        self.score = 0
        self._answer = None
        self._got = False
        self.active = True
        # clear the decoded text so the trigger does not fire again later
        if hasattr(self.hub, "clear_text"):
            self.hub.clear_text()
        self._broadcast()

    def feed(self, ch, buf):
        """Called by the keyer on every decoded letter while active.

        STOP/SKIP must be a single group of 6+ dots / dashes, so they are not
        confused with repeated short answers (e.g. two wrong 'S').
        """
        if not self.active:
            return
        if buf:
            s = set(buf)
            if s == {"."} and len(buf) >= 6:
                self._answer = "__STOP__"
                self._got = True
                return
            if s == {"-"} and len(buf) >= 6:
                self._answer = "__SKIP__"
                self._got = True
                return
        # per-character progress: key the target one letter at a time
        if self._pos < len(self._target) and ch and \
                ch.upper() == self._target[self._pos].upper():
            self._pos += 1
            if self._pos >= len(self._target):
                self._answer = self._target
                self._got = True
            else:
                self._show()       # move the cursor (one write per letter)
        else:
            self._pos = 0          # wrong letter: start the target over
            self._show()
            self._replay = True    # and replay it so the student hears it again

    # ---------------------------------------------------------- helpers
    def _broadcast(self):
        self.hub.broadcast({"t": "ex", "on": self.active, "name": self.name,
                            "index": self.index, "total": len(self.targets),
                            "score": self.score})

    def _show(self):
        if not self.screen or not hasattr(self.screen, "set_exercise"):
            return
        # line 1: the whole target, line 2: a static cursor under the letter
        # to key next (no blinking, so the I2C is written only when it moves)
        self.screen.set_exercise(self._target, " " * self._pos + "^")

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
    async def _tick(self):
        if not self.active:
            now = time.ticks_ms()
            if self.menu:
                if self.pending is None and time.ticks_diff(
                        now, self._scroll_at) > MENU_SCROLL_MS:
                    self._scroll_at = now
                    self._scroll_off += 1
                    self._menu_scroll()
                if time.ticks_diff(now, self._menu_at) > MENU_TIMEOUT_MS:
                    self.menu = False
                    self._clear()
            await asyncio.sleep_ms(100)
            return
        self._target = self.targets[self.index]
        self._pos = 0
        self._replay = False
        self._answer = None
        self._got = False
        self._show()
        await self._play(self._target)

        while self.active and not self._got:
            if self._replay:
                self._replay = False
                await self._play(self._target)
                continue
            await asyncio.sleep_ms(10)
        if not self.active:
            return

        ans = self._answer
        if ans == "__STOP__":
            self.active = False
            self._finish()
            await asyncio.sleep_ms(3000)
            if not self.menu:      # a new menu may have been opened meanwhile
                self._clear()
            return
        if ans == "__SKIP__":
            self.index += 1
        elif ans and ans.upper() == self._target.upper():
            self.score += 1
            self.index += 1
        # wrong answer: repeat the same target

        if self.index >= len(self.targets):
            self.active = False
            self._finish()
            await asyncio.sleep_ms(3000)
            if not self.menu:
                self._clear()
        else:
            self._broadcast()

    async def run(self):
        while True:
            try:
                await self._tick()
            except Exception as e:
                # never let an exercise error take the whole app down
                print("exercise error:", e)
                self.active = False
                self.menu = False
                self._clear()
                await asyncio.sleep_ms(500)
