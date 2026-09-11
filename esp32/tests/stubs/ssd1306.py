# Minimal SSD1306 stub for host-side tests: records what was drawn.


class SSD1306_I2C:
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.width = width
        self.height = height
        self.addr = addr
        self.texts = []

    def fill(self, c):
        self.texts = []

    def text(self, s, x, y, c=1):
        self.texts.append((s, x, y))

    def show(self):
        pass
