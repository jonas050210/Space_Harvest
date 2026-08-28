"""Procedural mixer — hum + alert tones. Never fatal if the device is missing."""

from __future__ import annotations

import os
from typing import Any


def setup_game_audio(directory: str = os.path.join("logs", "audio")) -> dict[str, Any] | None:
    """Synthesise WAVs and return an Ursina Audio dict, or None on failure."""
    try:
        from ursina import Audio

        from src.utils.procedural import (
            make_alert_wav,
            make_build_wav,
            make_click_wav,
            make_hum_wav,
            make_window_chime_wav,
        )
    except Exception as exc:
        print(f"[audio] disabled ({exc})")
        return None

    try:
        os.makedirs(directory, exist_ok=True)
        audio: dict[str, Any] = {
            "hum": Audio(make_hum_wav(os.path.join(directory, "hum.wav")), loop=True, autoplay=True),
        }
        makers = {
            "flare": lambda path: make_alert_wav("flare", path),
            "hull": lambda path: make_alert_wav("hull", path),
            "shortage": lambda path: make_alert_wav("shortage", path),
            "contract": lambda path: make_alert_wav("contract", path),
            "build": make_build_wav,
            "window": make_window_chime_wav,
            "click": make_click_wav,
        }
        for kind, maker in makers.items():
            audio[kind] = Audio(maker(os.path.join(directory, f"{kind}.wav")), autoplay=False)
        print("[audio] procedural hum and alert tones ready")
        return audio
    except Exception as exc:
        print(f"[audio] disabled ({exc})")
        return None
