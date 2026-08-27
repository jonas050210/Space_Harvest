# JSON settings with OneDrive-friendly project-local storage.
import json, os
from . import config, i18n

SETFILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")
DEFAULTS = {
    "language": "en",
    "difficulty": config.DEFAULT_DIFFICULTY,
    "music_on": True,
    "volume": 0.8,
    "last_save": None,
    "window_size": [1280, 720],
}

def load():
    if os.path.isfile(SETFILE):
        try:
            with open(SETFILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in DEFAULTS.items():
                    data.setdefault(k, v)
                return data
        except Exception:
            pass
    return DEFAULTS.copy()

def save(data):
    with open(SETFILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
