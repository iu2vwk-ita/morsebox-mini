# MorseBox exercise mode (Raspberry Pi version).
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
# The device SHOWS the target on the matrix and PLAYS it on the piezo (always
# both, together) at the chosen WPM, then waits for the student to key it back.
# For multi-letter targets the whole word is shown and the letter to key blinks.
# You can also start directly with TEST (full drill) or TEST1..TEST9.
import random
import threading
import time
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


class Exercise(threading.Thread):
    """Runs the exercise state machine in its own thread."""

    def __init__(self, settings, hub, sidetone=None, screen=None):
        super().__init__(daemon=True)
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
        self._pos = 0
        self._replay = False
        self._menu_at = 0
        self._stop = threading.Event()

    # ---------------------------------------------------------- control
    def enter_menu(self):
        """SOS was keyed: wait for the student to pick an exercise."""
        self.active = False
        self.menu = True
        self.pending = None
        self._menu_at = time.monotonic()
        if hasattr(self.hub, "clear_text"):
            self.hub.clear_text()
        self._menu_show()
        self.hub.broadcast({"t": "ex", "on": False, "menu": True})

    def _menu_show(self):
        if not self.screen or not hasattr(self.screen, "set_exercise"):
            return
        if self.pending is None:
            self.screen.set_exercise("MENU", "DOTS 1-9 ?")
        else:
            label = "FULL" if self.pending == 0 else "EX %d" % self.pending
            self.screen.set_exercise(label + " ?", ".. OK  -- NO")

    def select(self, n):
        """A drill was picked: ask for confirmation (.. = yes, -- = exit)."""
        self.pending = n
        self._menu_at = time.monotonic()
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
        self._answer = None
        self._got = False
        self.active = True
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
                self._show()
        else:
            self._pos = 0
            self._show()
            self._replay = True

    # ---------------------------------------------------------- helpers
    def _broadcast(self):
        self.hub.broadcast({"t": "ex", "on": self.active, "name": self.name,
                            "index": self.index, "total": len(self.targets),
                            "score": self.score})

    def _show(self):
        if not self.screen or not hasattr(self.screen, "set_exercise"):
            return
        self.screen.set_exercise(self._target, " " * self._pos + "^")

    def _play(self, text):
        if not self.sidetone:
            return
        self.playing = True
        try:
            unit = max(0.02, 1.2 / int(self.settings.get()["wpm"]))
            for ch in text.upper():
                code = MORSE.get(ch)
                if not code:
                    continue
                for el in code:
                    self.sidetone.set(True)
                    time.sleep(unit if el == "." else 3 * unit)
                    self.sidetone.set(False)
                    time.sleep(unit)
                time.sleep(2 * unit)   # letter gap
            time.sleep(2 * unit)
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

    # ---------------------------------------------------------- thread
    def _tick(self):
        if not self.active:
            if self.menu and time.monotonic() - self._menu_at > 8:
                self.menu = False
                self._clear()
            time.sleep(0.1)
            return
        self._target = self.targets[self.index]
        self._pos = 0
        self._replay = False
        self._answer = None
        self._got = False
        self._show()
        self._play(self._target)

        while self.active and not self._got and not self._stop.is_set():
            if self._replay:
                self._replay = False
                self._play(self._target)
                continue
            time.sleep(0.01)
        if not self.active:
            return

        ans = self._answer
        if ans == "__STOP__":
            self.active = False
            self._finish()
            time.sleep(3)
            self._clear()
            return
        if ans == "__SKIP__":
            self.index += 1
        elif ans and ans.upper() == self._target.upper():
            self.score += 1
            self.index += 1

        if self.index >= len(self.targets):
            self.active = False
            self._finish()
            time.sleep(3)
            self._clear()
        else:
            self._broadcast()

    def run(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                print("exercise error:", e)
                self.active = False
                self.menu = False
                self._clear()
                time.sleep(0.5)

    def stop(self):
        self._stop.set()
