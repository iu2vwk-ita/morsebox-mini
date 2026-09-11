#!/usr/bin/env python3
"""Audio for the Morse Simulator - CLICK decoder + sidetone via ALSA.

The key/paddle produces CLICKs (pulses) on the microphone, not a tone:
we detect every click, toggle key down/up and derive dit/dah and text.
Stdlib only + arecord/aplay. Device: plughw:3,0 (USB sound card).
"""
import math
import subprocess
import threading
import time

RATE = 48000
DEVICE = "plughw:CARD=Headphones,DEV=0"  # Pi internal audio jack (bcm2835)
FORMAT = "S16_LE"


class GPIOTone:
    """PWM sidetone on the GPIO: INSTANT (like Gianluca's Arduino Timer1 PWM).
    No software audio pipeline, no perceivable latency.
    Wire a passive buzzer: + -> GPIO24 (pin 18), - -> GND (pin 20)."""

    def __init__(self, pin=24, freq=650, mode="active", pins=None):
        # pins: extra BCM list, e.g. pins=[24, 25] or "24,25". Still
        # compatible with a single pin=24. All pins sound together.
        if pins is None:
            pins = pin
        if isinstance(pins, str):
            pins = [int(p) for p in pins.replace(";", ",").split(",") if p.strip()]
        elif isinstance(pins, int):
            pins = [pins]
        self.pins = list(pins) or [24]
        self.pin = self.pins[0]
        self.freq = freq
        self.mode = mode  # "active" = DC on/off (buzzer with oscillator), "passive" = PWM
        self._volume = 0.7
        self._on = False
        self._G = None
        self._pwms = []
        self._pwm = None  # first PWM, kept for compatibility
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
        f = int(f)
        ok = not self._pwms        # active mode: nothing to reprogram
        for pwm in self._pwms:
            try:
                pwm.ChangeFrequency(f)
                ok = True
            except Exception:
                pass
        # only remember the new note if it was actually applied, otherwise a
        # failed change would leave the sidetone stuck on the old one
        if ok:
            self.freq = f
        self._apply()

    def set_volume(self, v):
        self._volume = max(0.0, min(1.0, v / 100.0))
        self._apply()

    def _apply(self):
        if not self._ok:
            return
        if self.mode == "active":
            # active Low-Level-Trigger buzzer: LOW = sounds (DAOKAI module)
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
    """Clean note to the speaker (aplay). One thread feeds aplay continuously."""

    def __init__(self, freq=650, rate=RATE, device=DEVICE):
        self.freq = freq
        self.rate = rate
        self.device = device
        self._on = False
        self.volume = 0.7  # 0..1
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

    def _loop(self):
        block = 128  # 2.7 ms: minimum latency
        period = block / self.rate
        i = 0
        # pre-fill the initial aplay buffer (avoids startup underrun)
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
            if on:
                chunk = [0.95 * vol * math.sin(2 * math.pi * freq * (i + k) / self.rate)
                         for k in range(block)]
            else:
                chunk = [0.0] * block
            i += block
            try:
                self._proc.stdin.write(pcm16(chunk))
                self._proc.stdin.flush()
            except (OSError, BrokenPipeError):
                break
            # deadline scheduling: absorbs jitter without filling the buffer
            deadline += period
            wait = deadline - time.monotonic()
            if wait > 0:
                time.sleep(wait)


class CwAudioDecoder(threading.Thread):
    """Detects key clicks and decodes them into dit/dah + text."""

    def __init__(self, rate=RATE, device=DEVICE, on_key=None, on_char=None):
        super().__init__(daemon=True)
        self.rate = rate
        self.device = device
        self.on_key = on_key
        self.on_char = on_char
        self.block = 256  # 5.3 ms at 48 kHz: good timing resolution
        self._stop = threading.Event()

    def start_stream(self):
        try:
            self._proc = subprocess.Popen(
                ["arecord", "-q", "-D", self.device, "-f", FORMAT,
                 "-r", str(self.rate), "-c", "1"],
                stdout=subprocess.PIPE)
            return True
        except OSError:
            return False

    def run(self):
        if not self.start_stream():
            return
        step = 2
        key = False
        t_down = 0.0
        cooldown = 0.0
        ambient = 0.001
        thr = 0.25
        self._unit = 0.06  # ~20 wpm initial
        self._marks = []
        self._buf = ""
        self._off_at = 0.0
        n = self.block
        while not self._stop.is_set():
            raw = self._proc.stdout.read(n * step)
            if len(raw) < n * step:
                break
            mx = 0.0
            for i in range(0, len(raw), 2):
                a = abs(int.from_bytes(raw[i:i + 2], "little", signed=True) / 32768.0)
                if a > mx:
                    mx = a
            now = time.monotonic()
            # adapt the threshold to the background noise
            if mx < thr:
                ambient = 0.95 * ambient + 0.05 * mx
                thr = max(0.2, ambient * 6)
            if mx > thr and now > cooldown:
                cooldown = now + 0.025  # one click = one event
                key = not key
                if key:
                    t_down = now
                    if self.on_key:
                        self.on_key(True)
                else:
                    dur = now - t_down
                    self._off_at = now
                    self._marks.append(dur)
                    if len(self._marks) > 30:
                        self._marks.pop(0)
                    if self._marks:
                        self._unit = max(0.02, min(0.3,
                            sorted(self._marks)[len(self._marks) // 2]))
                    self._buf += "-" if dur >= 2 * self._unit else "."
                    if self.on_key:
                        self.on_key(False)
            # letter gap: 3 units with the key up
            if self._buf and not key and now - self._off_at > 3 * self._unit:
                if self.on_char:
                    self.on_char(self._buf)
                self._buf = ""
            time.sleep(0.001)

    def stop(self):
        self._stop.set()
