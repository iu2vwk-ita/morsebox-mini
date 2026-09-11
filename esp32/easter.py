# Hidden easter egg (not documented anywhere).
#
# Key 10 dots followed by a dash: a short 2-line message scrolls on the display
# explaining the box, and a little tune (73) is played on the piezo.
import uasyncio as asyncio
from morse import MORSE

LINE1 = "IU2VWK MORSE BOX - il tuo allenatore CW   "
LINE2 = "SOS: corsi   1 punto: gioco   73 de IU2VWK   "
TUNE = "73"
COLS = 16
STEP_MS = 200


def _window(text, i, width=COLS):
    """A scrolling 16-char window of `text` (wraps around)."""
    if not text:
        return " " * width
    o = i % len(text)
    return (text + text)[o:o + width]


class EasterEgg:
    def __init__(self, settings, sidetone=None, screen=None):
        self.settings = settings
        self.sidetone = sidetone
        self.screen = screen
        self.playing = False
        self._go = False

    def fire(self):
        self._go = True

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
    def _set_window(self, i):
        if self.screen and hasattr(self.screen, "set_banner"):
            self.screen.set_banner(_window(LINE1, i), _window(LINE2, i))

    def _clear(self):
        if self.screen and hasattr(self.screen, "clear_banner"):
            self.screen.clear_banner()

    async def _play_tune(self):
        unit = max(20, 1200 // int(self.settings.get()["wpm"]))
        for ch in TUNE:
            code = MORSE.get(ch)
            if not code:
                continue
            for el in code:
                self.sidetone.set(True)
                await asyncio.sleep_ms(unit if el == "." else 3 * unit)
                self.sidetone.set(False)
                await asyncio.sleep_ms(unit)
            await asyncio.sleep_ms(2 * unit)

    async def _show_and_play(self):
        self.playing = True
        try:
            self._set_window(0)
            if self.sidetone:
                await self._play_tune()
            # scroll both lines for one full pass
            n = max(len(LINE1), len(LINE2)) + COLS
            for i in range(n):
                self._set_window(i)
                await asyncio.sleep_ms(STEP_MS)
        finally:
            if self.sidetone:
                self.sidetone.set(False)
            self.playing = False
        await asyncio.sleep_ms(600)
        self._clear()
