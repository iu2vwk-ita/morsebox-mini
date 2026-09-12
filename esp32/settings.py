# Persistent settings on settings.json - same semantics as the Pi version.
import json
import time
from config import DEFAULTS, SETTINGS_FILE, TONE_MIN, TONE_MAX


def as_bool(v, default=False):
    """Strict boolean: 'false' must NOT become True (bool('false') == True)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return default


class Settings:
    def __init__(self):
        self._data = dict(DEFAULTS)
        self._last_save = 0
        self._dirty = False
        try:
            with open(SETTINGS_FILE) as f:
                self._data.update(json.load(f))
        except (OSError, ValueError):
            pass
        self._clamp()

    def _clamp(self):
        # per-field fallback: one bad value must not wipe the others
        d = self._data
        d["wpm"] = self._int(d, "wpm", 20, 5, 60)
        d["tone"] = self._int(d, "tone", 650, TONE_MIN, TONE_MAX)
        d["volume"] = self._int(d, "volume", 70, 0, 100)
        d["reverse"] = as_bool(d.get("reverse", False))
        d["buzzer"] = as_bool(d.get("buzzer", False))
        if d.get("mode") not in ("iambic-a", "iambic-b", "straight", "single"):
            d["mode"] = "iambic-b"
        if d.get("buzzer_mode") not in ("active", "passive"):
            d["buzzer_mode"] = "passive"

    @staticmethod
    def _int(d, key, default, lo, hi):
        try:
            return max(lo, min(hi, int(d.get(key, default))))
        except (TypeError, ValueError):
            return default

    def get(self):
        return dict(self._data)

    def snapshot(self):
        """Read-only view with NO copy: used by the 1 ms keyer loop."""
        return self._data

    def patch(self, p):
        for k in DEFAULTS:
            if k in p:
                self._data[k] = p[k]
        self._clamp()
        self._dirty = True
        self.flush()
        return dict(self._data)

    def flush(self):
        """Write to flash at most once per second (a slider drag sends many
        updates; flash writes block the event loop and wear the memory).
        A periodic call (watchdog task) guarantees the last change is saved."""
        if not self._dirty:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_save) <= 1000:
            return
        self._last_save = now
        self._dirty = False
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self._data, f)
        except OSError:
            self._dirty = True
