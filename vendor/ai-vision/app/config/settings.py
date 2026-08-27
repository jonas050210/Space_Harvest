"""Settings model with validation and JSON persistence.

Settings are stored as JSON in the project ``data`` directory. Loading is
tolerant: missing file -> defaults; unknown keys are ignored; invalid
values fall back to defaults with a log warning. Saving is atomic
(write to temp file, then replace), so a crash cannot corrupt the file.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from app.utils.logging_setup import get_logger

log = get_logger("config.settings")

_RESOLUTION_RE = re.compile(r"^\d{2,5}x\d{2,5}$")

#: Allowed gaze smoothing presets.
_GAZE_SMOOTHING_VALUES = {"low", "medium", "high"}

#: Vision performance modes: frame interval + input scale for the heavy
#: object/hand models. QUALITY = every frame at full resolution;
#: BALANCED = every 2nd frame; PERFORMANCE = every 4th frame at half
#: resolution. Face/eye/gaze always run every frame (they are the core).
VISION_MODES: dict[str, dict[str, int | float]] = {
    "quality": {"object_interval": 1, "object_scale": 1.0,
                "hand_interval": 1, "hand_scale": 1.0,
                "pose_interval": 1, "pose_scale": 1.0},
    "balanced": {"object_interval": 2, "object_scale": 1.0,
                 "hand_interval": 2, "hand_scale": 1.0,
                 "pose_interval": 1, "pose_scale": 1.0},
    "performance": {"object_interval": 4, "object_scale": 0.5,
                    "hand_interval": 4, "hand_scale": 0.5,
                    "pose_interval": 2, "pose_scale": 0.6},
}

#: Settings groups (Phase 13A): every key belongs to exactly one group.
#: Used for documentation, tests and the SYSTEM page's reset feature.
SETTINGS_GROUPS: dict[str, str] = {
    # GENERAL — application-wide behaviour
    "dark_theme": "GENERAL",
    "debug_mode": "GENERAL",
    "ai_enabled": "GENERAL",
    "image_generation_enabled": "GENERAL",
    "offline_mode": "GENERAL",
    "vision_auto_summary": "GENERAL",
    "auto_analyze_generated": "GENERAL",
    "voice_enabled": "GENERAL",
    "gesture_actions": "GENERAL",
    "first_run_done": "GENERAL",
    # WINDOW — size/position/last page memory
    "window_width": "GENERAL",
    "window_height": "GENERAL",
    "window_x": "GENERAL",
    "window_y": "GENERAL",
    "last_page": "GENERAL",
    "vision_panel": "GENERAL",
    # CAMERA
    "camera_index": "CAMERA",
    "resolution": "CAMERA",
    "fps_target": "CAMERA",
    # VISION — modules and thresholds
    "face_detection": "VISION",
    "face_mesh": "VISION",
    "min_detection_confidence": "VISION",
    "eye_tracking": "VISION",
    "blink_detection": "VISION",
    "head_pose": "VISION",
    "gaze_estimation": "VISION",
    "gaze_smoothing": "VISION",
    "gaze_cursor": "VISION",
    "gaze_cursor_size": "VISION",
    "gaze_trail": "VISION",
    "gaze_trail_length": "VISION",
    "min_gaze_confidence": "VISION",
    "show_eye_overlay": "VISION",
    "object_detection": "VISION",
    "object_tracking": "VISION",
    "object_confidence_threshold": "VISION",
    "max_objects": "VISION",
    "show_object_overlay": "VISION",
    "hand_tracking": "VISION",
    "max_hands": "VISION",
    "show_hand_overlay": "VISION",
    "gesture_recognition": "VISION",
    "gesture_confidence_threshold": "VISION",
    "person_tracking": "VISION",
    "body_tracking": "VISION",
    "show_body_skeleton": "VISION",
    "show_body_joints": "VISION",
    "movement_tracking": "VISION",
    "show_landmark_points": "VISION",
    "show_mesh_lines": "VISION",
    "show_gaze_heatmap": "VISION",
    "overlay_preset": "VISION",
    # AI
    "llm_provider": "AI",
    "llm_model": "AI",
    "llm_temperature": "AI",
    "llm_timeout": "AI",
    "llm_base_url": "AI",
    # IMAGE GENERATION
    "image_provider": "IMAGE GENERATION",
    "image_model": "IMAGE GENERATION",
    "image_width": "IMAGE GENERATION",
    "image_height": "IMAGE GENERATION",
    "image_steps": "IMAGE GENERATION",
    "image_cfg": "IMAGE GENERATION",
    "image_seed": "IMAGE GENERATION",
    "image_negative_prompt": "IMAGE GENERATION",
    "image_preset": "IMAGE GENERATION",
    "image_prompt_polish": "IMAGE GENERATION",
    "image_base_url": "IMAGE GENERATION",
    "sdwebui_base_url": "IMAGE GENERATION",
    "comfyui_base_url": "IMAGE GENERATION",
    # PRIVACY
    "face_reference_enabled": "PRIVACY",
    # PERFORMANCE
    "vision_mode": "PERFORMANCE",
    "vision_delegate": "PERFORMANCE",
    # ADVANCED — validated, rarely changed
    "extensions_enabled": "ADVANCED",
}

#: All groups in display order.
SETTINGS_GROUP_ORDER: tuple[str, ...] = (
    "GENERAL", "CAMERA", "VISION", "AI", "IMAGE GENERATION",
    "PRIVACY", "PERFORMANCE", "ADVANCED",
)


#: Defaults for every supported setting (used on first start and as fallback).
DEFAULTS: dict[str, Any] = {
    "camera_index": 0,
    "resolution": "1280x720",
    "fps_target": 30,
    "face_detection": True,
    "face_mesh": True,
    "dark_theme": True,
    "debug_mode": False,
    "show_landmark_points": True,
    "show_mesh_lines": False,
    "min_detection_confidence": 0.5,
    # Phase 2
    "eye_tracking": True,
    "blink_detection": True,
    "head_pose": True,
    "gaze_estimation": True,
    "gaze_smoothing": "medium",
    "gaze_cursor": True,
    "gaze_cursor_size": 12,
    "gaze_trail": True,
    "gaze_trail_length": 12,
    "min_gaze_confidence": 0.35,
    "show_eye_overlay": True,
    # Phase 3
    "object_detection": True,
    "object_tracking": True,
    "object_confidence_threshold": 0.5,
    "max_objects": 20,
    "show_object_overlay": True,
    "hand_tracking": True,
    "max_hands": 2,
    "show_hand_overlay": True,
    "gesture_recognition": True,
    "gesture_confidence_threshold": 0.5,
    "person_tracking": True,
    "vision_panel": True,
    # Phase 4 — AI vision + image generation
    "ai_enabled": True,
    "llm_provider": "ollama",
    "llm_model": "",
    "llm_temperature": 0.3,
    "llm_timeout": 30,
    "llm_base_url": "http://localhost:11434",
    "vision_auto_summary": False,
    "image_generation_enabled": True,
    "image_provider": "mock",
    "image_model": "",
    "image_width": 512,
    "image_height": 512,
    "image_base_url": "http://localhost:11434/v1",
    "offline_mode": False,
    # Phase 5 — performance modes, GPU, image generation expansion
    "vision_mode": "balanced",
    "vision_delegate": "cpu",
    "image_steps": 20,
    "image_cfg": 7.0,
    "image_seed": -1,
    "image_negative_prompt": "",
    "image_preset": "none",
    "image_prompt_polish": False,
    "sdwebui_base_url": "http://127.0.0.1:7860",
    "comfyui_base_url": "http://127.0.0.1:8188",
    "extensions_enabled": False,
    # Phase 6 — live body vision, image analysis, feedback
    "body_tracking": True,
    "show_body_skeleton": True,
    "show_body_joints": True,
    "movement_tracking": True,
    "auto_analyze_generated": True,
    "face_reference_enabled": False,
    # Phase 10 — overlay presets (MINIMAL/BODY/FACE/OBJECTS/FULL/CUSTOM)
    "overlay_preset": "custom",
    # Phase 11 — first-run experience
    "first_run_done": False,
    # Phase 17 — voice (capability-gated system TTS)
    "voice_enabled": False,
    # Phase 26 — analytics wave (gaze heatmap overlay + gesture actions)
    "show_gaze_heatmap": False,
    "gesture_actions": False,
    # Phase 25 — window state memory (size/position/last page; 0 = not
    # saved yet). Restored on start, saved on close.
    "window_width": 0,
    "window_height": 0,
    "window_x": 0,
    "window_y": 0,
    "last_page": "",
}


@dataclass
class Settings:
    """Typed view of the persisted configuration."""

    camera_index: int = 0
    resolution: str = "1280x720"
    fps_target: int = 30
    face_detection: bool = True
    face_mesh: bool = True
    dark_theme: bool = True
    debug_mode: bool = False
    show_landmark_points: bool = True
    show_mesh_lines: bool = False
    min_detection_confidence: float = 0.5
    # Phase 2
    eye_tracking: bool = True
    blink_detection: bool = True
    head_pose: bool = True
    gaze_estimation: bool = True
    gaze_smoothing: str = "medium"
    gaze_cursor: bool = True
    gaze_cursor_size: int = 12
    gaze_trail: bool = True
    gaze_trail_length: int = 12
    min_gaze_confidence: float = 0.35
    show_eye_overlay: bool = True
    # Phase 3
    object_detection: bool = True
    object_tracking: bool = True
    object_confidence_threshold: float = 0.5
    max_objects: int = 20
    show_object_overlay: bool = True
    hand_tracking: bool = True
    max_hands: int = 2
    show_hand_overlay: bool = True
    gesture_recognition: bool = True
    gesture_confidence_threshold: float = 0.5
    person_tracking: bool = True
    vision_panel: bool = True
    # Phase 4 — AI vision + image generation
    ai_enabled: bool = True
    llm_provider: str = "ollama"
    llm_model: str = ""
    llm_temperature: float = 0.3
    llm_timeout: int = 30
    llm_base_url: str = "http://localhost:11434"
    vision_auto_summary: bool = False
    image_generation_enabled: bool = True
    image_provider: str = "mock"
    image_model: str = ""
    image_width: int = 512
    image_height: int = 512
    image_base_url: str = "http://localhost:11434/v1"
    offline_mode: bool = False
    # Phase 5 — performance modes, GPU, image generation expansion
    vision_mode: str = "balanced"
    vision_delegate: str = "cpu"
    image_steps: int = 20
    image_cfg: float = 7.0
    image_seed: int = -1
    image_negative_prompt: str = ""
    image_preset: str = "none"
    image_prompt_polish: bool = False
    sdwebui_base_url: str = "http://127.0.0.1:7860"
    comfyui_base_url: str = "http://127.0.0.1:8188"
    extensions_enabled: bool = False
    # Phase 6
    body_tracking: bool = True
    show_body_skeleton: bool = True
    show_body_joints: bool = True
    movement_tracking: bool = True
    auto_analyze_generated: bool = True
    face_reference_enabled: bool = False
    overlay_preset: str = "custom"
    first_run_done: bool = False
    voice_enabled: bool = False
    show_gaze_heatmap: bool = False
    gesture_actions: bool = False
    window_width: int = 0
    window_height: int = 0
    window_x: int = 0
    window_y: int = 0
    last_page: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Settings":
        """Build a Settings object, validating every value against DEFAULTS."""
        clean: dict[str, Any] = {}
        for field in fields(cls):
            value = raw.get(field.name, DEFAULTS[field.name])
            valid, cleaned = _validate(field.name, value, field.type)
            if not valid:
                log.warning(
                    "Invalid setting '%s'=%r — falling back to default %r",
                    field.name,
                    value,
                    DEFAULTS[field.name],
                )
                clean[field.name] = DEFAULTS[field.name]
            else:
                clean[field.name] = cleaned
        return cls(**clean)


def _validate(name: str, value: Any, expected: type) -> tuple[bool, Any]:
    """Validate a single setting; returns (ok, cleaned_value)."""
    if name == "resolution":
        if not isinstance(value, str) or not _RESOLUTION_RE.match(value):
            return False, value
        width, height = (int(part) for part in value.split("x"))
        if width < 160 or height < 120:
            return False, value
        return True, value
    if name == "camera_index":
        return (isinstance(value, int) and not isinstance(value, bool) and value >= 0), value
    if name == "fps_target":
        return (isinstance(value, int) and not isinstance(value, bool) and 5 <= value <= 240), value
    if name == "gaze_smoothing":
        if not isinstance(value, str) or value.lower() not in _GAZE_SMOOTHING_VALUES:
            return False, value
        return True, value.lower()
    if name == "gaze_cursor_size":
        return (isinstance(value, int) and not isinstance(value, bool) and 6 <= value <= 30), value
    if name == "gaze_trail_length":
        return (isinstance(value, int) and not isinstance(value, bool) and 3 <= value <= 60), value
    if name == "min_gaze_confidence":
        ok = (isinstance(value, (int, float)) and not isinstance(value, bool)
              and 0.0 <= value <= 1.0)
        return ok, float(value) if ok else value
    if name == "min_detection_confidence":
        ok = (isinstance(value, (int, float)) and not isinstance(value, bool)
              and 0.0 <= value <= 1.0)
        return ok, float(value) if ok else value
    if name == "object_confidence_threshold":
        ok = (isinstance(value, (int, float)) and not isinstance(value, bool)
              and 0.0 <= value <= 1.0)
        return ok, float(value) if ok else value
    if name == "gesture_confidence_threshold":
        ok = (isinstance(value, (int, float)) and not isinstance(value, bool)
              and 0.0 <= value <= 1.0)
        return ok, float(value) if ok else value
    if name == "max_objects":
        return (isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 50), value
    if name == "max_hands":
        return (isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 4), value
    if name == "llm_provider":
        if not isinstance(value, str) or value not in {"ollama", "openai_compatible", "mock"}:
            return False, value
        return True, value
    if name == "image_provider":
        if not isinstance(value, str) or value not in {
            "mock", "sdwebui", "local", "external", "comfyui",
        }:
            return False, value
        return True, value
    if name == "vision_mode":
        if not isinstance(value, str) or value not in {"quality", "balanced", "performance"}:
            return False, value
        return True, value
    if name == "vision_delegate":
        if not isinstance(value, str) or value not in {"cpu", "gpu"}:
            return False, value
        return True, value
    if name == "image_preset":
        if not isinstance(value, str):
            return False, value
        return True, value  # validated against the preset registry in the UI layer
    if name == "overlay_preset":
        if not isinstance(value, str) or value not in {
            "custom", "minimal", "body", "face", "objects", "full",
        }:
            return False, value
        return True, value
    if name == "image_steps":
        return (isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 150), value
    if name == "image_cfg":
        ok = (isinstance(value, (int, float)) and not isinstance(value, bool)
              and 1.0 <= value <= 30.0)
        return ok, float(value) if ok else value
    if name == "image_seed":
        return (isinstance(value, int) and not isinstance(value, bool) and -1 <= value <= 2_147_483_647), value
    if name == "image_negative_prompt":
        if not isinstance(value, str) or len(value) > 2000:
            return False, value
        return True, value
    if name == "llm_temperature":
        ok = (isinstance(value, (int, float)) and not isinstance(value, bool)
              and 0.0 <= value <= 2.0)
        return ok, float(value) if ok else value
    if name == "llm_timeout":
        return (isinstance(value, int) and not isinstance(value, bool) and 5 <= value <= 300), value
    if name in ("image_width", "image_height"):
        return (isinstance(value, int) and not isinstance(value, bool) and value in {256, 512, 768, 1024}), value
    if name in ("llm_base_url", "image_base_url", "sdwebui_base_url",
                "comfyui_base_url"):
        if not isinstance(value, str) or not value.strip():
            return False, value
        return True, value.strip()
    # PEP 563: with postponed annotations, field.type may be the *string*
    # 'bool'/'str' rather than the class — handle both forms.
    if expected is bool or (isinstance(expected, str) and expected == "bool"):
        return isinstance(value, bool), value
    if expected is int or (isinstance(expected, str) and expected == "int"):
        # Integer fields without a custom validator (window_width,
        # window_x, …) must reject floats/strings/bools — a float width
        # would break resize() later.
        return (isinstance(value, int) and not isinstance(value, bool)), value
    if expected is str or (isinstance(expected, str) and expected == "str"):
        # String fields without a custom validator (llm_model,
        # image_model, last_page, …) must reject non-strings — an int
        # model name would crash later (e.g. `model.split(":")`).
        return (isinstance(value, str),
                value.strip() if isinstance(value, str) else value)
    return True, value


class SettingsService:
    """Loads, validates, updates and persists application settings."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._settings = Settings()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def settings(self) -> Settings:
        return self._settings

    def load(self) -> Settings:
        """Read settings from disk (missing/corrupt file -> defaults)."""
        if not self._path.exists():
            log.info("No settings file found at %s — using defaults", self._path)
            self._settings = Settings()
            return self._settings
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not read settings file %s: %s — using defaults", self._path, exc)
            self._settings = Settings()
            return self._settings
        if not isinstance(raw, dict):
            log.warning("Settings file %s does not contain an object — using defaults", self._path)
            self._settings = Settings()
            return self._settings
        self._settings = Settings.from_dict(raw)
        log.info("Settings loaded from %s", self._path)
        return self._settings

    def save(self, settings: Settings | None = None) -> None:
        """Persist settings atomically."""
        data = self._settings if settings is None else settings
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data.to_dict(), indent=2)
        fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent, prefix=".settings-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_path, self._path)
        except OSError as exc:
            log.error("Could not save settings to %s: %s", self._path, exc)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return
        log.debug("Settings saved to %s", self._path)

    def update(self, **values: Any) -> Settings:
        """Validate + apply updates, then persist. Unknown keys are ignored."""
        known = {field.name for field in fields(Settings)}
        clean: dict[str, Any] = {}
        for key, value in values.items():
            if key not in known:
                log.warning("Ignoring unknown setting '%s'", key)
                continue
            default = getattr(self._settings, key)
            ok, cleaned = _validate(key, value, type(default))
            if not ok:
                log.warning(
                    "Rejected invalid value for '%s': %r (kept %r)", key, value, default
                )
                continue
            clean[key] = cleaned
        for key, value in clean.items():
            setattr(self._settings, key, value)
        self.save()
        return self._settings

    def get(self, key: str, default: Any = None) -> Any:
        """Read a single setting value."""
        return getattr(self._settings, key, default)

    def reset(self) -> Settings:
        """Restore every setting to its documented default and persist.

        All values pass validation by construction (defaults are the
        reference). Used by the SYSTEM page's RESET ALL SETTINGS action.
        """
        self._settings = Settings()
        self.save()
        log.info("Settings reset to defaults")
        return self._settings
