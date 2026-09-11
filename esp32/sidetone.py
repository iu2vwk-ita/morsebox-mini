# Sidetone PWM hardware multi-piezo — latenza zero (nessuna pipeline audio).
#
# Tutti i pin suonano insieme: quando il key va giu' il duty passa subito al
# valore attivo, quando va su torna a 0. Nessun buffer, nessun thread audio.
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
                    # firmware piu' vecchi: niente duty_u16 nel costruttore
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
            # buzzer con oscillatore: DC on/off (duty massimo = acceso)
            d = 65535 if (self._on and self.volume > 0.01) else 0
        else:
            # piezo passivo: onda quadra 50% * volume
            d = int(32768 * self.volume) if self._on else 0
        for pwm in self._pwms:
            self._set_duty(pwm, d)

    # ------------------------------------------------------------ API
    def set(self, on):
        self._on = bool(on)
        self._apply()

    def set_freq(self, f):
        self.freq = int(f)
        for pwm in self._pwms:
            try:
                pwm.freq(self.freq)
            except Exception:
                pass

    def set_volume(self, v):
        self.volume = max(0.0, min(1.0, v / 100.0))
        self._apply()
