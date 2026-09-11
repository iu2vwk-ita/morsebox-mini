# LCD1602 con backpack I2C (PCF8574/PCF8574T) — 16x2 caratteri.
#
# Collegamento: VCC->5V (VIN), GND->GND, SDA->GPIO21, SCL->GPIO22.
# Riga 1: "WPM xx"   Riga 2: testo Morse decodificato.
#
# Il refresh I2C avviene in una coroutine separata, quindi NON introduce
# latenza nel keyer (add_char/set_wpm aggiornano solo il buffer).
import time
import uasyncio as asyncio
from machine import I2C, Pin
from config import (LCD_I2C_ID, LCD_SDA, LCD_SCL, LCD_ADDR,
                    LCD_COLS, LCD_ROWS)

# bit del PCF8574 sul backpack classico FC-113
_RS = 0x01
_E = 0x04
_BL = 0x08


class I2cLcd:
    def __init__(self, i2c, addr=0x27, cols=16, rows=2):
        self.i2c = i2c
        self.addr = addr
        self.cols = cols
        self.rows = rows
        self.backlight = _BL
        time.sleep_ms(50)
        self._init()

    # ---------------------------------------------------------- low level
    def _raw(self, b):
        self.i2c.writeto(self.addr, bytes([b | self.backlight]))

    def _pulse(self, b):
        self._raw(b | _E)
        time.sleep_us(60)
        self._raw(b & 0xFB)
        time.sleep_us(60)

    def _nibble(self, nibble, rs):
        b = ((nibble & 0x0F) << 4) | (_RS if rs else 0x00)
        self._pulse(b)

    def _byte(self, value, rs):
        self._nibble((value >> 4) & 0x0F, rs)
        self._nibble(value & 0x0F, rs)

    def command(self, cmd):
        self._byte(cmd, 0)

    def char(self, ch):
        self._byte(ord(ch), 1)

    def _init(self):
        # sequenza di reset HD44780 in 4 bit
        for _ in range(3):
            self._nibble(0x03, 0)
            time.sleep_ms(5)
        self._nibble(0x02, 0)
        time.sleep_ms(1)
        self.command(0x28)   # 4 bit, 2 righe, font 5x8
        self.command(0x0C)   # display on, cursore off
        self.command(0x06)   # incremento automatico
        self.clear()

    # ---------------------------------------------------------- api
    def clear(self):
        self.command(0x01)
        time.sleep_ms(2)

    def move_to(self, col, row):
        base = 0x00 if row == 0 else 0x40
        self.command(0x80 | ((base + col) & 0x7F))

    def putstr(self, s):
        for ch in s:
            self.char(ch)


_MODE_LABEL = {"iambic-a": "IAMB A",
               "iambic-b": "IAMB B",
               "straight": "STRAIGHT"}


class Screen:
    """Interfaccia usata dal keyer: set_wpm / set_mode / add_char / run."""

    def __init__(self):
        i2c = I2C(LCD_I2C_ID, scl=Pin(LCD_SCL), sda=Pin(LCD_SDA),
                  freq=100000)
        self.lcd = I2cLcd(i2c, addr=LCD_ADDR, cols=LCD_COLS, rows=LCD_ROWS)
        self.wpm = 20
        self.mode = "iambic-b"
        self.decode = ""
        self._dirty = True
        self._refresh()

    @staticmethod
    def _pad(s, n):
        s = s[:n]
        return s + " " * (n - len(s))

    def _line1(self):
        left = "WPM %d" % self.wpm
        right = _MODE_LABEL.get(self.mode, "IAMB B")
        n = LCD_COLS - len(left) - len(right)
        if n < 1:
            right = right[:max(0, LCD_COLS - len(left) - 1)]
            n = LCD_COLS - len(left) - len(right)
        return left + " " * n + right

    def _refresh(self):
        line1 = self._pad(self._line1(), LCD_COLS)
        line2 = self._pad(self.decode, LCD_COLS)
        self.lcd.move_to(0, 0)
        self.lcd.putstr(line1)
        if LCD_ROWS > 1:
            self.lcd.move_to(0, 1)
            self.lcd.putstr(line2)

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
        self.decode = self.decode[-(LCD_COLS - 1):]
        self._dirty = True

    async def run(self):
        while True:
            if self._dirty:
                self._dirty = False
                try:
                    self._refresh()
                except Exception:
                    pass
            await asyncio.sleep_ms(200)
