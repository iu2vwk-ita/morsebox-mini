# Paddle / straight key inputs: internal pull-up, active low.
from machine import Pin
from config import DIT_PIN, DAH_PIN, KEY_PIN


class Paddle:
    backend = "esp32"

    def __init__(self):
        self._dit = Pin(DIT_PIN, Pin.IN, Pin.PULL_UP)
        self._dah = Pin(DAH_PIN, Pin.IN, Pin.PULL_UP)
        self._key = Pin(KEY_PIN, Pin.IN, Pin.PULL_UP)

    def read(self):
        """(dit, dah, straight) True = contact closed to GND."""
        return (not self._dit.value(), not self._dah.value(),
                not self._key.value())
