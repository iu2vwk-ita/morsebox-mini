# Hidden easter egg (not documented anywhere).
#
# Key 10 dots in a row and the message shows on the display and is played on
# the piezo in Morse.
import uasyncio as asyncio
from morse import MORSE

LINE1 = "KAPPAROGGERO"
LINE2 = "POSITIVO"
TEXT = LINE1 + " " + LINE2


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
                await self._show_and_play()
            await asyncio.sleep_ms(50)

    async def _show_and_play(self):
        if self.screen and hasattr(self.screen, "set_banner"):
            self.screen.set_banner(LINE1, LINE2)
        self.playing = True
        try:
            if self.sidetone:
                unit = max(20, 1200 // int(self.settings.get()["wpm"]))
                for ch in TEXT:
                    code = MORSE.get(ch)
                    if not code:
                        continue
                    for el in code:
                        self.sidetone.set(True)
                        await asyncio.sleep_ms(unit if el == "." else 3 * unit)
                        self.sidetone.set(False)
                        await asyncio.sleep_ms(unit)
                    await asyncio.sleep_ms(2 * unit)
        finally:
            if self.sidetone:
                self.sidetone.set(False)
            self.playing = False
        await asyncio.sleep_ms(3000)
        if self.screen and hasattr(self.screen, "clear_banner"):
            self.screen.clear_banner()
