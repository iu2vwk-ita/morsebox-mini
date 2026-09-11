# SSD1306 128x64 I2C OLED screen - same interface as lcd1602.Screen.
#
# 16 columns x 8 rows of 8x8 text. Used automatically when an OLED is found;
# otherwise the firmware falls back to the LCD1602 / MAX7219.
import uasyncio as asyncio
from machine import I2C, Pin
from config import (OLED_I2C_ID, OLED_SDA, OLED_SCL, OLED_ADDR,
                    OLED_WIDTH, OLED_HEIGHT, BOOT_MESSAGE, BOOT_TITLE,
                    BOOT_HELP, BOOT_SPEED_MS)
import ssd1306

CHAR_W = 8
CHAR_H = 8
COLS = OLED_WIDTH // CHAR_W      # 16
ROWS = OLED_HEIGHT // CHAR_H     # 8

_MODE_LABEL = {"iambic-a": "IAMB A", "iambic-b": "IAMB B",
               "straight": "STRAIGHT", "single": "SINGLE"}


class Screen:
    """Interface used by the keyer: set_wpm / set_mode / add_char / run."""

    def __init__(self, i2c=None):
        if i2c is None:
            i2c = I2C(OLED_I2C_ID, scl=Pin(OLED_SCL), sda=Pin(OLED_SDA),
                      freq=400000)
        addr = self._find(i2c)
        self.oled = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=addr)
        self.wpm = 20
        self.mode = "iambic-b"
        self.decode = ""
        self.exercise = None
        self.banner = None
        self._dirty = True
        self._refresh()

    @staticmethod
    def _find(i2c):
        # SSD1306 lives at 0x3C/0x3D. Do NOT probe 0x27/0x3F: those are the
        # LCD1602 backpack addresses, we would drive the wrong chip.
        found = i2c.scan()
        for a in (OLED_ADDR, 0x3C, 0x3D):
            if a in (0x3C, 0x3D) and a in found:
                return a
        raise OSError("no OLED found")

    # ------------------------------------------------------------ drawing
    def _text(self, s, row, col=0):
        if 0 <= row < ROWS:
            self.oled.text(s[:COLS - col], col * CHAR_W, row * CHAR_H, 1)

    @staticmethod
    def _wrap(text, width):
        lines = []
        cur = ""
        for ch in text:
            cur += ch
            if len(cur) >= width:
                lines.append(cur)
                cur = ""
        if cur:
            lines.append(cur)
        return lines

    def _refresh(self):
        o = self.oled
        o.fill(0)
        if self.banner:
            lines = (self._wrap(self.banner[0], COLS)
                     + self._wrap(self.banner[1], COLS))
            start = max(0, (ROWS - len(lines)) // 2)
            for i, ln in enumerate(lines[:ROWS]):
                self._text(ln, start + i)
        elif self.exercise:
            target, cursor = self.exercise
            lines = self._wrap(target, COLS)
            for i, ln in enumerate(lines[:ROWS - 2]):
                self._text(ln, i)
            self._text(cursor[:COLS], min(len(lines), ROWS - 2))
        else:
            self._text("WPM %d %s" % (self.wpm,
                                      _MODE_LABEL.get(self.mode, "")), 0)
            lines = self._wrap(self.decode, COLS)[-(ROWS - 2):]
            for i, ln in enumerate(lines):
                self._text(ln, 2 + i)
        o.show()

    # ------------------------------------------------------------ API
    def set_wpm(self, w):
        try:
            self.wpm = int(w)
        except (TypeError, ValueError):
            return
        self._dirty = True

    def set_mode(self, mode):
        if mode:
            self.mode = mode
            self._dirty = True

    def add_char(self, ch):
        if ch == " ":
            self.decode += " "
        elif ch and len(ch) == 1:
            self.decode += ch.upper()
        self.decode = self.decode[-(COLS * (ROWS - 2)):]
        self._dirty = True

    def clear_text(self):
        """Wipe the decoded text (web UI 'Clear' button)."""
        self.decode = ""
        self._dirty = True

    def set_exercise(self, line1, line2=""):
        new = (line1, line2)
        if self.exercise != new:      # only redraw when the text changes
            self.exercise = new
            self._dirty = True

    def clear_exercise(self):
        self.exercise = None
        self._dirty = True

    def set_banner(self, line1, line2=""):
        self.banner = (line1, line2)
        self._dirty = True

    def clear_banner(self):
        self.banner = None
        self._dirty = True

    # ------------------------------------------------------------ boot / task
    async def _boot_scroll(self, msg):
        buf = "  " + msg + "  "
        for i in range(max(1, len(buf) - COLS + 1)):
            self.oled.fill(0)
            self.oled.text(buf[i:i + COLS], 0, (OLED_HEIGHT - CHAR_H) // 2, 1)
            self.oled.show()
            await asyncio.sleep_ms(BOOT_SPEED_MS)
        self._dirty = True

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
        self._dirty = True
        while True:
            if self._dirty:
                self._dirty = False
                try:
                    self._refresh()
                except Exception:
                    pass
            await asyncio.sleep_ms(50)
