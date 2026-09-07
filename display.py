#!/usr/bin/env python3
"""Display a matrice di punti MAX7219 (8x8, in catena) per il Morse Simulator.

- Driver SPI software (bit-bang) con RPi.GPIO/gpiozero: nessuna dipendenza.
- Fuori dal Pi (o senza matrice) passa in modalita' "ascii": stampa i frame
  su stdout, cosi' puoi verificare font e layout anche su Windows.
- Il thread mostra una riga scorrevole: "WPM xx" + ultimo testo decodificato.

Wiring (BCM): DIN=GPIO10, CLK=GPIO11, CS=GPIO8, VCC=5V, GND=GND.
Moduli in catena: DIN del successivo nella DOUT del precedente.
"""
import sys
import threading
import time

DIN, CLK, CS = 10, 11, 8       # BCM (pin 19, 23, 24)
MODULES = 4                     # 4x 8x8 => 32 colonne x 8 righe
INTENSITY = 8                   # 0..15

# Font 5x7, orientato per righe (7 byte, bit0 = colonna piu' a sinistra, bit4 = destra).
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

COLUMNS = MODULES * 8


def glyph(ch):
    ch = ch.upper()
    return F.get(ch, F[" "])


class Raw7249:
    """SPI software verso uno o piu' moduli MAX7219 in catena."""

    def __init__(self, modules=MODULES, intensity=INTENSITY):
        self.modules = modules
        self.g = self._open()
        if self.g is None:
            self.backend = "ascii"
        else:
            self.backend = "max7219"
            self._init(intensity)

    def _open(self):
        try:
            import RPi.GPIO as G
            G.setmode(G.BCM)
            for p in (DIN, CLK, CS):
                G.setup(p, G.OUT)
            G.output(DIN, 0), G.output(CLK, 0), G.output(CS, 1)
            self._G = G
            return "gpio"
        except Exception:
            try:
                from gpiozero import OutputDevice
                self._din = OutputDevice(DIN)
                self._clk = OutputDevice(CLK)
                self._cs = OutputDevice(CS, active_high=False)
                return "gpiozero"
            except Exception:
                return None

    def _bit(self, v):
        G = getattr(self, "_G", None)
        if G is not None:
            G.output(DIN, 1 if v else 0)
            G.output(CLK, 1)
            G.output(CLK, 0)
        else:
            self._din.value = 1 if v else 0
            self._clk.on()
            self._clk.off()

    def _latch(self):
        G = getattr(self, "_G", None)
        if G is not None:
            G.output(CS, 0)
            G.output(CS, 1)
        else:
            self._cs.on()  # active_high=False -> accende il latch
            self._cs.off()

    def _write_cmd(self, reg, val):
        # 16 bit: [reg (8) | data (8)], MSB first, un modulo alla volta
        frame = ((reg & 0x0F) << 8) | (val & 0xFF)
        for i in range(15, -1, -1):
            self._bit((frame >> i) & 1)

    def _send(self, reg, values):
        # values: lista di un valore per modulo (catena: primo = ultimo)
        for val in reversed(values):
            self._write_cmd(reg, val)
        self._latch()

    def _init(self, intensity):
        for reg, val in ((0x0C, 0x01), (0x0F, 0x00),   # normal, no test
                         (0x09, 0x00),                  # no decode
                         (0x0B, 0x07),                  # scan 8 righe
                         (0x0A, intensity),
                         (0x0C, 0x01)):                 # on
            self._send(reg, [val] * self.modules)

    def clear(self):
        for d in range(8):
            self._send(0x01 + d, [0] * self.modules)

    def write_rows(self, rows):
        # rows: lista di 8 interi (una riga per modulo? no: 8 righe totali),
        # ogni intero = bit per colonna (bit0 = modulo? gestito da Screen)
        raise NotImplementedError

    def render(self, frame):
        """frame: lista di COLUMNS interi, ognuno = 8 bit per riga (bit0=alto).
        Scrive riga per riga sui moduli."""
        self.clear()
        for r in range(8):
            rowvals = []
            for m in range(self.modules):
                byte = 0
                for j in range(8):
                    col = m * 8 + j
                    if col < len(frame) and (frame[col] >> r) & 1:
                        byte |= 1 << (7 - j)   # bit7 = colonna sinistra del modulo
                rowvals.append(byte)
            self._send(0x01 + r, rowvals)


class Screen:
    """Thread: testo scorrevole (WPM + decodifica) sulla matrice."""

    def __init__(self, modules=MODULES, speed=8, live=True):
        self.hw = Raw7249(modules) if live else None
        if self.hw is not None and self.hw.backend == "ascii":
            self.hw = None  # niente matrice: solo preview, nessun thread
        self.wpm = "20"
        self.decode = ""
        self._lock = threading.Lock()
        self._text = self._build()
        self._off = 0
        self._tick = 0
        if self.hw is not None:
            self._t = threading.Thread(target=self._loop, daemon=True)
            self._t.start()

    def _build(self):
        return "WPM " + self.wpm + "     " + self.decode[-24:]

    def set_wpm(self, w):
        with self._lock:
            self.wpm = str(w)
            self._text = self._build()

    def add_char(self, ch):
        with self._lock:
            if ch == " ":
                self.decode += " "
            elif ch and len(ch) == 1:
                self.decode += ch.upper()
            self.decode = self.decode[-24:]
            self._text = self._build()

    def _frame_text(self):
        # colonne per un carattere (5) + 1 spazio = 6
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

    def _loop(self):
        while True:
            time.sleep(0.12)
            self._tick += 1
            if self._tick % 3 == 0:
                self._off = (self._off + 1) % (len(self._text) * 6 + 8)
            self.hw.render(self._frame_text())

    def dump(self, text=None, off=0):
        """Rendering ASCII per test senza hardware."""
        if text is not None:
            with self._lock:
                self._text = text
                self.decode = text
        f = self._frame_text.__wrapped__ if False else None
        cols = [0] * (COLUMNS + 20)
        x = -off
        for ch in (text or self._text).upper():
            gl = glyph(ch)
            for r, rowbits in enumerate(gl):
                for c in range(5):
                    if rowbits & (1 << c):
                        pos = x + c
                        if 0 <= pos < len(cols):
                            cols[pos] |= 1 << r
            x += 6
        cols = cols[:COLUMNS]
        lines = []
        for r in range(8):
            line = "".join("#" if (cols[c] >> r) & 1 else " " for c in range(COLUMNS))
            lines.append(line)
        return "\n".join(lines)


def main():
    s = Screen(live=False)      # ascii preview, nessun GPIO
    for off in (0, 3):
        print("=== offset %d ===" % off)
        print(s.dump("WPM 20  CQ IHW", off))
        print()


if __name__ == "__main__":
    main()
