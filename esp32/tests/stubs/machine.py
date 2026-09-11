# Minimal MicroPython `machine` stub for host-side tests.
# The PWM class can be told to fail, to exercise the sidetone fallbacks.


class Pin:
    def __init__(self, pin, *args, **kwargs):
        self.pin = pin
        self._value = 0

    def value(self, v=None):
        if v is None:
            return self._value
        self._value = v


class PWM:
    fail_freq = False     # freq() raises
    fail_ctor = False     # constructor raises (no free channel)

    def __init__(self, pin, freq=1000, duty_u16=0):
        if PWM.fail_ctor:
            raise OSError("no PWM channel")
        self.pin = pin
        self._freq = freq
        self._duty = duty_u16
        self.deinited = False

    def freq(self, f=None):
        if f is None:
            return self._freq
        if PWM.fail_freq:
            raise ValueError("frequency not available")
        self._freq = f
        return f

    def duty_u16(self, d=None):
        if d is None:
            return self._duty
        self._duty = d

    def duty(self, d=None):
        if d is None:
            return self._duty
        self._duty = d

    def deinit(self):
        self.deinited = True


class I2C:
    def __init__(self, *args, **kwargs):
        pass


class SPI:
    def __init__(self, *args, **kwargs):
        pass


def freq(*args):
    pass


class WDT:
    def __init__(self, *args, **kwargs):
        pass

    def feed(self):
        pass
