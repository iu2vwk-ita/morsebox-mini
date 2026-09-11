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
        self._pwms = []
        self._ok = False
        for p in pins:
            try:
                try:
                    pwm = PWM(Pin(p), freq=self.freq, duty_u16=0)
                except TypeError:
                    # older firmware: no duty_u16 in the constructor
                    pwm = PWM(Pin(p))
                    pwm.freq(self.freq)
                    pwm.duty(0)
                self._pwms.append(pwm)
            except Exception:
                pass
        self._ok = bool(self._pwms)

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
        self.freq = f
        for pwm in self._pwms:
            try:
                pwm.freq(f)
            except Exception:
                # some firmware builds only expose init() for changes
                try:
                    pwm.init(freq=f)
                except Exception:
                    pass
        # changing the frequency can reset the duty: re-apply the current state
        self._apply()

    def set_volume(self, v):
        self.volume = max(0.0, min(1.0, v / 100.0))
        self._apply()
