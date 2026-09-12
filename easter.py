# Hidden easter egg (Raspberry Pi version, not documented anywhere).
#
# Key 10 dots followed by a dash: a sequence of screens scrolls through the
# display and each screen is transmitted in Morse at TUNE_WPM, so the sound
# says exactly what you see. Key 6 dots to stop early.
import threading
import time
from morse import MORSE

# Each entry is one screen: (line1, line2). Keep lines <= 16 chars.
SCREENS = [
    ("IU2VWK", "MORSE BOX"),
    ("IL TUO", "ALLENATORE CW"),
    ("BATTI SOS", "PER I CORSI"),
    ("1 PUNTO", "PER IL GIOCO"),
    ("GAME", "REFLEX 40 CHARS"),
    ("6 PUNTI", "STOP OVUNQUE"),
    ("WEB UI", "10.42.0.1"),
    ("WIFI", "IU2VWK-MORSE"),
    ("PASSWORD", "MORSE1234"),
    ("73 DE", "IU2VWK ANGELO"),
]
TUNE_WPM = 20        # sound speed for the easter egg
GAP_S = 0.8          # pause between screens


class EasterEgg(threading.Thread):
    def __init__(self, settings, sidetone=None, screen=None):
        super().__init__(daemon=True)
        self.settings = settings
        self.sidetone = sidetone
        self.screen = screen
        self.playing = False
        self._go = False
        self._stop = False
        self._stop_evt = threading.Event()

    def fire(self):
        self._go = True

    def stop(self):
        """Key 6 dots to cut the message short."""
        self._stop = True

    # ------------------------------------------------------------ helpers
    def _set_screen(self, line1, line2):
        if self.screen and hasattr(self.screen, "set_banner"):
            self.screen.set_banner(line1, line2)

    def _clear(self):
        if self.screen and hasattr(self.screen, "clear_banner"):
            self.screen.clear_banner()

    def _play_text(self, text):
        unit = max(0.02, 1.2 / TUNE_WPM)
        for ch in text.upper():
            if self._stop:
                return
            code = MORSE.get(ch)
            if not code:
                continue
            for el in code:
                if self._stop:
                    return
                self.sidetone.set(True)
                time.sleep(unit if el == "." else 3 * unit)
                self.sidetone.set(False)
                time.sleep(unit)
            time.sleep(2 * unit)

    def _show_and_play(self):
        self._stop = False
        self.playing = True
        try:
            for line1, line2 in SCREENS:
                if self._stop:
                    break
                self._set_screen(line1, line2)
                if self.sidetone:
                    # the sound says exactly what is on the screen
                    self._play_text(line1 + " " + line2)
                else:
                    time.sleep(1.5)
                time.sleep(GAP_S)
        finally:
            if self.sidetone:
                self.sidetone.set(False)
            self.playing = False
        time.sleep(0.6)
        self._clear()

    def run(self):
        while not self._stop_evt.is_set():
            if self._go:
                self._go = False
                try:
                    self._show_and_play()
                except Exception as e:
                    # never let the egg take the whole app down
                    print("easter error:", e)
                    self.playing = False
                    if self.sidetone:
                        try:
                            self.sidetone.set(False)
                        except Exception:
                            pass
            time.sleep(0.05)
