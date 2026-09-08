#!/usr/bin/env python3
"""Audio per il Morse Simulator — decoder a CLICK + sidetone via ALSA.

Il tasto/paddle produce dei CLICK (impulsi) sul microfono, non un tono:
rileviamo ogni click, alterniamo key giu'/su' e ricaviamo dit/dah e testo.
Solo stdlib + arecord/aplay. Device: plughw:3,0 (scheda USB).
"""
import math
import subprocess
import threading
import time

RATE = 48000
DEVICE = "plughw:CARD=Headphones,DEV=0"  # jack audio interno del Pi (bcm2835)
FORMAT = "S16_LE"


class GPIOTone:
    """Sidetone PWM su GPIO: ISTANTANEO (come il Timer1 PWM dell'Arduino di
    Gianluca). Nessuna pipeline audio software, nessuna latenza percepibile.
    Collegare un buzzer passivo: + -> GPIO24 (pin 18), - -> GND (pin 20)."""

    def __init__(self, pin=24, freq=650, mode="active", pins=None):
        # pins: lista BCM extra, es. pins=[24, 25] o "24,25". Resta
        # compatibile con pin=24 singolo. Tutti i pin suonano insieme.
        if pins is None:
            pins = pin
        if isinstance(pins, str):
            pins = [int(p) for p in pins.replace(";", ",").split(",") if p.strip()]
        elif isinstance(pins, int):
            pins = [pins]
        self.pins = list(pins) or [24]
        self.pin = self.pins[0]
        self.freq = freq
        self.mode = mode  # "active" = DC on/off (buzzer con oscillatore), "passive" = PWM
        self._volume = 0.7
        self._on = False
        self._G = None
        self._pwms = []
        self._pwm = None  # primo PWM, tenuto per compatibilita'
        self._ok = False
        try:
            import RPi.GPIO as G
            G.setmode(G.BCM)
            for p in self.pins:
                G.setup(p, G.OUT, initial=G.HIGH if mode == "active" else G.LOW)
            self._G = G
            if mode == "passive":
                for p in self.pins:
                    pwm = G.PWM(p, freq)
                    pwm.start(0)
                    self._pwms.append(pwm)
                self._pwm = self._pwms[0] if self._pwms else None
            self._ok = True
        except Exception:
            self._ok = False

    def set(self, on):
        self._on = bool(on)
        self._apply()

    def set_freq(self, f):
        self.freq = f
        for pwm in self._pwms:
            try:
                pwm.ChangeFrequency(int(f))
            except Exception:
                pass

    def set_volume(self, v):
        self._volume = max(0.0, min(1.0, v / 100.0))
        self._apply()

    def _apply(self):
        if not self._ok:
            return
        if self.mode == "active":
            # buzzer attivo Low-Level-Trigger: LOW = suona (modulo DAOKAI)
            try:
                self._G.output(self.pins, self._G.LOW if (
                    self._on and self._volume > 0.01) else self._G.HIGH)
            except Exception:
                pass
            return
        if not self._pwms:
            return
        duty = 50.0 * self._volume if self._on else 0.0
        for pwm in self._pwms:
            try:
                pwm.ChangeDutyCycle(duty)
            except Exception:
                pass


def pcm16(samples):
    return b"".join(int(max(-1.0, min(1.0, s)) * 32767).to_bytes(
        2, "little", signed=True) for s in samples)


class Sidetone:
    """Seno via ALSA (DAC/jack/USB) verso altoparlante + AUX. Versione B.

    NON sostituisce il piezo GPIO (zero latenza per chi manipola):
    e' un monitor ambiente con ~30-80 ms di ritardo. Inviluppo anti-click.
    Stessa API di GPIOTone: set/set_freq/set_volume/start/stop."""

    def __init__(self, freq=650, rate=RATE, device=DEVICE, ramp_ms=4.0):
        self.freq = freq
        self.rate = rate
        self.device = device
        self._ramp = max(0.5, float(ramp_ms)) / 1000.0  # s, default 4 ms
        self._on = False
        self.volume = 0.7  # 0..1
        self._gain = 0.0  # inviluppo 0..1, solo il thread _loop lo tocca
        self._lock = threading.Lock()
        self._proc = None
        self._ok = False

    def start(self):
        try:
            self._proc = subprocess.Popen(
                ["aplay", "-q", "-D", self.device, "-f", FORMAT,
                 "-r", str(self.rate), "-c", "1"],
                stdin=subprocess.PIPE)
            self._ok = True
            self._t = threading.Thread(target=self._loop, daemon=True)
            self._t.start()
        except OSError:
            self._ok = False

    def set(self, on):
        with self._lock:
            self._on = bool(on)

    def set_freq(self, f):
        with self._lock:
            self.freq = f

    def set_volume(self, v):
        with self._lock:
            self.volume = max(0.0, min(1.0, v / 100.0))

    def stop(self):
        proc, self._proc = self._proc, None
        try:
            if proc and proc.poll() is None:
                proc.stdin.close()
                proc.terminate()
        except (OSError, BrokenPipeError):
            pass

    def _loop(self):
        block = 128  # 2.7 ms: latenza minima
        period = block / self.rate
        step = 1.0 / (self.rate * self._ramp)  # incr. inviluppo per campione
        i = 0
        # pre-riempi il buffer iniziale di aplay (evita underrun in avvio)
        try:
            silence = pcm16([0.0] * block)
            for _ in range(10):
                self._proc.stdin.write(silence)
            self._proc.stdin.flush()
        except (OSError, BrokenPipeError):
            return
        deadline = time.monotonic()
        while self._proc and self._proc.poll() is None:
            with self._lock:
                on, freq, vol = self._on, self.freq, self.volume
            target = 1.0 if (on and vol > 0.01) else 0.0
            # rampa per-campione verso target: niente stacchi = niente click
            chunk = []
            g = self._gain
            for k in range(block):
                if g < target:
                    g = min(target, g + step)
                elif g > target:
                    g = max(target, g - step)
                if g <= 0.0001:
                    chunk.append(0.0)
                else:
                    chunk.append(0.95 * vol * g
                                 * math.sin(2 * math.pi * freq * (i + k) / self.rate))
            self._gain = g
            i += block
            try:
                self._proc.stdin.write(pcm16(chunk))
                self._proc.stdin.flush()
            except (OSError, BrokenPipeError):
                break
            # schedulazione a deadline: assorbe il jitter senza riempire il buffer
            deadline += period
            wait = deadline - time.monotonic()
            if wait > 0:
                time.sleep(wait)
