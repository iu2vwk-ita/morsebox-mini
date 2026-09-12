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
            try:
                pwm.duty(d >> 6)   # 16 bit -> 10 bit (0..1023)
            except Exception:
                pass
        except Exception:
            # a dead/deinited PWM must never crash the caller
            pass

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
            try:
                self._set_duty(pwm, d)
            except Exception:
                pass

    # ------------------------------------------------------------ API
    def set(self, on):
        self._on = bool(on)
        self._apply()

    def set_freq(self, f):
        try:
            self._set_freq(f)
        except Exception:
            # never let a tone change take down the caller (web server)
            pass

    def _set_freq(self, f):
        f = int(f)
        if f == self.freq:
            return
        applied = 0
        for i, pwm in enumerate(self._pwms):
            try:
                pwm.freq(f)
                applied += 1
                continue
            except Exception:
                pass
            # fallback: build the replacement FIRST, only then release the old
            # one. If the rebuild fails we keep the old PWM (still working at
            # the previous frequency) instead of leaving a dead object here.
            new = self._make_pwm(self._pins[i], f)
            if new is None:
                continue
            try:
                pwm.deinit()
            except Exception:
                pass
            self._pwms[i] = new
            applied += 1
        # only remember the new frequency if at least one pin accepted it
        if applied:
            self.freq = f
        self._apply()

    def set_mode(self, mode):
        """'passive' (piezo, PWM tone) or 'active' (buzzer with its own tone)."""
        if mode in ("active", "passive") and mode != self.mode:
            self.mode = mode
            self._apply()

    def set_volume(self, v):
        self.volume = max(0.0, min(1.0, v / 100.0))
        self._apply()
