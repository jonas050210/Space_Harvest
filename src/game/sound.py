# Sound design framework.
# Economy-focused audio feedback.
from ursina import *
import os

AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "audio")

def ensure_dir():
    if not os.path.isdir(AUDIO_DIR):
        os.makedirs(AUDIO_DIR)

class SoundEngine:
    """Simple sound engine for mining, lasers, machines, and nebulae."""
    def __init__(self):
        ensure_dir()
        # Ursina uses Panda3D audio; real sound files would be loaded here.
        # This demo provides placeholders while keeping the audio architecture ready.
        self.sounds = {
            "mining": "audio/mining.ogg",
            "laser": "audio/laser.ogg",
            "machine_start": "audio/machine_start.ogg",
            "ambient_space": "audio/ambient_space.ogg",
        }
        self.volume = 0.8
        self.muted = False

    def play(self, key, loop=False):
        if self.muted:
            return
        path = self.sounds.get(key)
        if path and os.path.isfile(path):
            # Ursina audio implementation placeholder for real files.
            print(f"[Sound] Spielt: {key} (loop={loop})")
        else:
            print(f"[Sound] Ready for: {key} (file: {path})")

    def set_volume(self, vol):
        self.volume = max(0.0, min(1.0, vol))
        print(f"[Sound] Volume: {int(self.volume * 100)}%")

    def toggle_mute(self):
        self.muted = not self.muted
        print(f"[Sound] {'Stumm' if self.muted else 'Aktiv'}")
