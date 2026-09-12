# Reflex Trainer - game (Raspberry Pi version).
#
# The box plays a random character at the current speed; you key it back before
# the timer runs out. Correct = +1 point and the speed goes UP; wrong or too
# slow = -2 WPM. A game is ROUNDS characters. RX (playback) and TX (your keying)
# always share the same speed, because the keyer follows reflex.wpm.
#
# Start it with SOS -> 1 dot (or key GAME). Stop with 6 dots, skip with 6 dashes.
import random
import threading
import time
from morse import MORSE

START_WPM = 12
MIN_WPM = 10
MAX_WPM = 40
STEP_UP = 1          # +1 WPM per correct answer
STEP_DOWN = 2        # -2 WPM per mistake / timeout
ROUNDS = 40          # a game is 40 characters
LIVES = 0            # 0 = no life limit (always play all ROUNDS)
ANSWER_S = 3.0       # time to answer (the "timer")
BAR = 8              # countdown bar length on the display

# Mixed set: letters + numbers + common punctuation/prosigns.
CHARS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,?/=+")


class Reflex(threading.Thread):
    def __init__(self, settings, hub, sidetone=None, screen=None):
        super().__init__(daemon=True)
        self.settings = settings
        self.hub = hub
        self.sidetone = sidetone
        self.screen = screen
        self.active = False
        self.playing = False
        self.score = 0
        self.round = 0
        self.lives = 0
        self.wpm = START_WPM
        self._target = ""
        self._got = False
        self._ok = False
        self._skip = False
        self._deadline = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # ---------------------------------------------------------- control
    def start(self):
        self.active = True
        self.playing = False
        self.score = 0
        self.round = 0
        self.lives = LIVES
        self.wpm = START_WPM
        self._got = False
        self._ok = False
        self._skip = False
        if hasattr(self.hub, "clear_text"):
            self.hub.clear_text()
        self.hub.broadcast({"t": "ex", "on": True, "name": "REFLEX",
                            "index": 0, "total": 0, "score": 0})

    def stop(self):
        self.active = False
        self.playing = False
        if self.screen and hasattr(self.screen, "clear_exercise"):
            try:
                self.screen.clear_exercise()
            except Exception:
                pass

    def feed(self, ch, buf):
        """Called by the keyer when a letter is decoded."""
        if not self.active or self.playing:
            return
        if buf:
            s = set(buf)
            if s == {"."} and len(buf) >= 6:
                self.stop()              # 6 dots = STOP, like the exercises
                return
            if s == {"-"} and len(buf) >= 6:
                with self._lock:
                    self._skip = True    # 6 dashes = SKIP this character
                    self._got = True
                return
        with self._lock:
            self._ok = bool(ch) and ch.upper() == self._target
            self._got = True

    # ---------------------------------------------------------- display
    def _show(self, line2):
        if not self.screen or not hasattr(self.screen, "set_exercise"):
            return
        self.screen.set_exercise(
            "S%d W%d %d/%d" % (self.score, self.wpm, self.round, ROUNDS), line2)

    @staticmethod
    def _barstr(frac):
        n = int(frac * BAR + 0.5)
        n = max(0, min(BAR, n))
        return "#" * n + "-" * (BAR - n)

    # ---------------------------------------------------------- playback
    def _play(self, ch):
        if not self.sidetone:
            return
        self.playing = True
        try:
            unit = max(0.02, 1.2 / self.wpm)
            for el in MORSE.get(ch, ""):
                self.sidetone.set(True)
                time.sleep(unit if el == "." else 3 * unit)
                self.sidetone.set(False)
                time.sleep(unit)
            time.sleep(2 * unit)
        finally:
            self.sidetone.set(False)
            self.playing = False

    # ---------------------------------------------------------- one round
    def _round(self):
        self.round += 1
        self._target = random.choice(CHARS)
        with self._lock:
            self._got = False
            self._ok = False
        self._show("%s  %s" % (self._target, self._barstr(1.0)))
        self._play(self._target)
        if not self.active:
            return
        self._deadline = time.monotonic() + ANSWER_S
        while self.active:
            with self._lock:
                got = self._got
            if got:
                break
            left = self._deadline - time.monotonic()
            if left <= 0:
                break
            self._show("%s  %s" % (self._target, self._barstr(left / ANSWER_S)))
            time.sleep(0.1)
        if not self.active:
            return
        with self._lock:
            got, ok, skip = self._got, self._ok, self._skip
            self._skip = False
        if skip:
            self._show("SKIP " + self._target)
        elif got and ok:
            self.score += 1
            self.wpm = min(MAX_WPM, self.wpm + STEP_UP)
            self._show("OK!  " + self._target)
        else:
            if LIVES:
                self.lives -= 1
            self.wpm = max(MIN_WPM, self.wpm - STEP_DOWN)
            self._show("ERR  " + self._target)
        time.sleep(0.7)

    def run(self):
        while not self._stop.is_set():
            try:
                if not self.active:
                    time.sleep(0.1)
                    continue
                self._round()
                if self.round >= ROUNDS or (LIVES and self.lives <= 0):
                    self.active = False
                    self._show("DONE %d/%d" % (self.score, ROUNDS))
                    time.sleep(3)
                    if self.screen and hasattr(self.screen,
                                               "clear_exercise"):
                        self.screen.clear_exercise()
            except Exception as e:
                # never let a game error take the whole app down
                print("reflex error:", e)
                self.active = False
                self.playing = False
                if self.screen and hasattr(self.screen, "clear_exercise"):
                    self.screen.clear_exercise()
                time.sleep(0.5)
