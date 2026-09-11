# Hardware PWM multi-piezo sidetone - zero latency (no audio pipeline).
#
# All pins sound together: when the key goes down the duty jumps straight to
# the active value, when it goes up it returns to 0. No buffer, no audio thread.
from machine import Pin, PWM
from config import BUZZER_MODE


class Sidetone:
    def __init__(self, pins, freq=650, mode=BUZZER_MODE):
        self.mode = mode
        self.freq = int(freq)
        self.volume = 0.7
        self._on = False
        self._pins = list(pins)
        self._pwms = []
        self._ok = False
        for p in self._pins:
            pwm = self._make_pwm(p, self.freq)
            if pwm is not None:
                self._pwms.append(pwm)
        self._ok = bool(self._pwms)

    @staticmethod
    def _make_pwm(pin, freq):
        try:
            try:
                return PWM(Pin(pin), freq=freq, duty_u16=0)
            except TypeError:
                # older firmware: no duty_u16 in the constructor
                pwm = PWM(Pin(pin))
                pwm.freq(freq)
                pwm.duty(0)
                return pwm
        except Exception:
            return None

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _set_duty(pwm, d):
        try:
            pwm.duty_u16(d)
        except AttributeError:
            pwm.duty(d >> 6)   # 16 bit -> 10 bit (0..1023)

    def _apply(self):
        if not self._pwms:
            return
        if self.mode == "active":
            # buzzer with built-in oscillator: DC on/off (max duty = on)
            d = 65535 if (self._on and self.volume > 0.01) else 0
        else:
            # passive piezo: 50% square wave * volume
            d = int(32768 * self.volume) if self._on else 0
        for pwm in self._pwms:
            self._set_duty(pwm, d)

    # ------------------------------------------------------------ API
    def set(self, on):
        self._on = bool(on)
        self._apply()

    def set_freq(self, f):
        f = int(f)
        if f == self.freq:
            return
        ok = False
        for i, pwm in enumerate(self._pwms):
            try:
                pwm.freq(f)
                ok = True
                continue
            except Exception:
                pass
            # fallback: rebuild this PWM at the new frequency
            try:
                pwm.deinit()
            except Exception:
                pass
            new = self._make_pwm(self._pins[i], f)
            if new is not None:
                self._pwms[i] = new
                ok = True
        # only remember the new frequency if we actually applied it, otherwise
        # a failed change would leave the sidetone stuck on the old note
        if ok:
            self.freq = f
        self._apply()

    def set_volume(self, v):
        self.volume = max(0.0, min(1.0, v / 100.0))
        self._apply()
