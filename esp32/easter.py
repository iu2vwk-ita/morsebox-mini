# Hidden easter egg (not documented anywhere).
#
# Key 10 dots followed by a dash: a sequence of screens scrolls through the
# display and each screen is transmitted in Morse at TUNE_WPM, so the sound
# says exactly what you see. Key 6 dots to stop early.
import uasyncio as asyncio
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
GAP_MS = 800         # pause between screens


class EasterEgg:
    def __init__(self, settings, sidetone=None, screen=None):
        self.settings = settings
        self.sidetone = sidetone
        self.screen = screen
        self.playing = False
        self._go = False
        self._stop = False

    def fire(self):
        self._go = True

    def stop(self):
        """Key 6 dots to cut the message short."""
        self._stop = True

    async def run(self):
        while True:
            if self._go:
                self._go = False
                try:
                    await self._show_and_play()
                except Exception as e:
                    # never let the egg take the whole app down
                    print("easter error:", e)
                    self.playing = False
                    if self.sidetone:
                        try:
                            self.sidetone.set(False)
                        except Exception:
                            pass
            await asyncio.sleep_ms(50)

    # ------------------------------------------------------------ helpers
    def _set_screen(self, line1, line2):
        if self.screen and hasattr(self.screen, "set_banner"):
            self.screen.set_banner(line1, line2)

    def _clear(self):
        if self.screen and hasattr(self.screen, "clear_banner"):
            self.screen.clear_banner()

    async def _play_text(self, text):
        unit = max(20, 1200 // TUNE_WPM)
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
                await asyncio.sleep_ms(unit if el == "." else 3 * unit)
                self.sidetone.set(False)
                await asyncio.sleep_ms(unit)
            await asyncio.sleep_ms(2 * unit)

    async def _show_and_play(self):
        self._stop = False
        self.playing = True
        try:
            for line1, line2 in SCREENS:
                if self._stop:
                    break
                self._set_screen(line1, line2)
                if self.sidetone:
                    # the sound says exactly what is on the screen
                    await self._play_text(line1 + " " + line2)
                else:
                    await asyncio.sleep_ms(1500)
                await asyncio.sleep_ms(GAP_MS)
        finally:
            if self.sidetone:
                self.sidetone.set(False)
            self.playing = False
        await asyncio.sleep_ms(600)
        self._clear()
