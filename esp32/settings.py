# Impostazioni persistenti su settings.json — stessa semantica del Pi.
import json
from config import DEFAULTS, SETTINGS_FILE


class Settings:
    def __init__(self):
        self._data = dict(DEFAULTS)
        try:
            with open(SETTINGS_FILE) as f:
                self._data.update(json.load(f))
        except (OSError, ValueError):
            pass
        self._clamp()

    def _clamp(self):
        d = self._data
        try:
            d["wpm"] = max(5, min(60, int(d.get("wpm", 20))))
            d["tone"] = max(400, min(4000, int(d.get("tone", 650))))
            d["volume"] = max(0, min(100, int(d.get("volume", 70))))
        except (TypeError, ValueError):
            d.update(DEFAULTS)
            return
        d["reverse"] = bool(d.get("reverse", False))
        d["buzzer"] = bool(d.get("buzzer", False))
        if d.get("mode") not in ("iambic-a", "iambic-b", "straight"):
            d["mode"] = "iambic-b"

    def get(self):
        return dict(self._data)

    def patch(self, p):
        for k in DEFAULTS:
            if k in p:
                self._data[k] = p[k]
        self._clamp()
        data = dict(self._data)
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(data, f)
        except OSError:
            pass
        return data
