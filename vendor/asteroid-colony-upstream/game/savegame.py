# JSON save and load support.
import json, os, time
from . import config

SAVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "saves")

def ensure_dir():
    if not os.path.isdir(SAVE_DIR):
        os.makedirs(SAVE_DIR)

def list_saves():
    ensure_dir()
    files = []
    for f in os.listdir(SAVE_DIR):
        if f.endswith(".json"):
            files.append(f)
    files.sort(key=lambda x: os.path.getmtime(os.path.join(SAVE_DIR, x)), reverse=True)
    return files

def save_slot(name, state_dict):
    ensure_dir()
    path = os.path.join(SAVE_DIR, f"{name}.json")
    data = {
        "timestamp": time.time(),
        "name": name,
        "state": state_dict,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path

def load_slot(name):
    path = os.path.join(SAVE_DIR, f"{name}.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("state", {})
