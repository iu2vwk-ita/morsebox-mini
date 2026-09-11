# MAX7219 8x8 display (chained) on ESP32 hardware SPI - optional.
#
# Enable it with DISPLAY_ENABLED = True in config.py.
# Wiring (VSPI): SCK=GPIO18, MOSI=GPIO23, CS=GPIO4, VCC=5V, GND=GND.
# Chained modules: the next module's DIN goes to the previous one's DOUT.
import uasyncio as asyncio
from machine import Pin, SPI
from config import (DISPLAY_SCK, DISPLAY_MOSI, DISPLAY_CS, DISPLAY_MODULES,
                    BOOT_MESSAGE, BOOT_TITLE, BOOT_HELP)

MODULES = DISPLAY_MODULES
COLUMNS = MODULES * 8
INTENSITY = 8

# 5x7 font, row oriented (7 bytes, bit0 = leftmost column).
F = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "A": (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "B": (0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E),
    "C": (0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E),
    "D": (0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E),
    "E": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F),
    "F": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10),
    "G": (0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F),
    "H": (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "I": (0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "J": (0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C),
    "K": (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11),
    "L": (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F),
    "M": (0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11),
    "N": (0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11),
    "O": (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "P": (0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10),
    "Q": (0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D),
    "R": (0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11),
    "S": (0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E),
    "T": (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    "U": (0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "V": (0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04),
    "W": (0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11),
    "X": (0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11),
    "Y": (0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04),
    "Z": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F),
    "0": (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E),
    "1": (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "2": (0x0E, 0x11, 0x01, 0x02, 0x04, 0x10, 0x1F),
    "3": (0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E),
    "4": (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02),
    "5": (0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E),
    "6": (0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E),
    "7": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08),
    "8": (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E),
    "9": (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C),
    ".": (0, 0, 0, 0, 0, 0x0C, 0x0C),
    ",": (0, 0, 0, 0, 0x0C, 0x04, 0x08),
    "-": (0, 0, 0, 0x1F, 0, 0, 0),
    "/": (0x01, 0x02, 0x02, 0x04, 0x08, 0x08, 0x10),
    "?": (0x0E, 0x11, 0x01, 0x02, 0x04, 0, 0x04),
    ":": (0, 0x0C, 0x0C, 0, 0x0C, 0x0C, 0),
    "=": (0, 0, 0x1F, 0, 0x1F, 0, 0),
    "+": (0, 0x04, 0x04, 0x1F, 0x04, 0x04, 0),
    "(": (0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02),
    ")": (0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08),
    "'": (0x04, 0x04, 0, 0, 0, 0, 0),
    '"': (0x0A, 0x0A, 0, 0, 0, 0, 0),
    "!": (0x04, 0x04, 0x04, 0x04, 0, 0x04, 0),
    "&": (0x0C, 0x12, 0x14, 0x08, 0x15, 0x12, 0x0D),
    "_": (0, 0, 0, 0, 0, 0, 0x1F),
}


def glyph(ch):
    return F.get(ch.upper(), F[" "])


class Max7219:
    """MAX7219 driver on hardware VSPI."""

    def __init__(self, modules=MODULES, intensity=INTENSITY):
        self.modules = modules
        self.spi = SPI(2, baudrate=1000000, polarity=0, phase=0,
                       sck=Pin(DISPLAY_SCK), mosi=Pin(DISPLAY_MOSI))
        self.cs = Pin(DISPLAY_CS, Pin.OUT, value=1)
        self._init(intensity)

    def _send(self, reg, values):
        # chain: the first module received is the last in the chain
        self.cs(0)
        for val in reversed(values):
            self.spi.write(bytes([reg & 0x0F, val & 0xFF]))
        self.cs(1)

    def _init(self, intensity):
        for reg, val in ((0x0C, 0x01), (0x0F, 0x00), (0x09, 0x00),
                         (0x0B, 0x07), (0x0A, intensity), (0x0C, 0x01)):
            self._send(reg, [val] * self.modules)

    def clear(self):
        for d in range(8):
            self._send(0x01 + d, [0] * self.modules)

    def render(self, frame):
        for r in range(8):
            rowvals = []
            for m in range(self.modules):
                byte = 0
                for j in range(8):
                    col = m * 8 + j
                    if col < len(frame) and (frame[col] >> r) & 1:
                        byte |= 1 << (7 - j)
                rowvals.append(byte)
            self._send(0x01 + r, rowvals)


class Screen:
    """Scrolling text (WPM + last decoded chars) on the matrix."""

    def __init__(self, modules=MODULES):
        self.hw = Max7219(modules)
        self.wpm = "20"
        self.decode = ""
        self._text = self._build()
        self._off = 0
        self._tick = 0

    def _build(self):
        return "WPM " + self.wpm + "     " + self.decode[-24:]

    def set_wpm(self, w):
        self.wpm = str(w)
        self._text = self._build()

    def add_char(self, ch):
        if ch == " ":
            self.decode += " "
        elif ch and len(ch) == 1:
            self.decode += ch.upper()
        self.decode = self.decode[-24:]
        self._text = self._build()

    def set_exercise(self, line1, line2=""):
        self._text = (line1 + "   " + line2).upper()
        self._off = 0

    def clear_exercise(self):
        self._text = self._build()

    def set_banner(self, line1, line2=""):
        self._text = (line1 + "   " + line2).upper()
        self._off = 0

    def clear_banner(self):
        self._text = self._build()

    def _frame_text(self):
        cols = [0] * (COLUMNS + 20)
        x = -self._off
        for ch in (self._text + "  " * 20).upper():
            gl = glyph(ch)
            for r, rowbits in enumerate(gl):
                for c in range(5):
                    if rowbits & (1 << c):
                        pos = x + c
                        if 0 <= pos < len(cols):
                            cols[pos] |= 1 << r
            x += 6
        return cols[:COLUMNS]

    async def _boot_scroll(self, msg):
        """Scroll the boot message once, then return to the normal screen."""
        self._text = BOOT_TITLE + "     " + msg + "     "
        end = len(self._text) * 6 + 8
        for off in range(0, end, 1):
            self._off = off
            try:
                self.hw.render(self._frame_text())
            except Exception:
                pass
            await asyncio.sleep_ms(60)
        self._off = 0
        self._text = self._build()

    async def run(self):
        if BOOT_MESSAGE:
            try:
                await self._boot_scroll(BOOT_MESSAGE)
            except Exception:
                pass
        if BOOT_HELP:
            try:
                await self._boot_scroll(BOOT_HELP)
            except Exception:
                pass
        while True:
            await asyncio.sleep_ms(120)
            self._tick += 1
            if self._tick % 3 == 0:
                self._off = (self._off + 1) % (len(self._text) * 6 + 8)
            try:
                self.hw.render(self._frame_text())
            except Exception:
                pass
