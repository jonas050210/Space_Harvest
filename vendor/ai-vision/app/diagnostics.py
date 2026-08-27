"""System diagnostics: professional setup check (``python main.py --check``).

Every check reports PASS / WARN / FAIL / UNAVAILABLE with a readable
problem, reason and fix. Checks are honest: a GPU check on a machine
without CUDA reports UNAVAILABLE, never FAIL. Only real, locally
verifiable information is used.
"""

from __future__ import annotations

import importlib
import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from typing import Callable

from app.utils.logging_setup import get_logger

log = get_logger("diagnostics")


@dataclass
class CheckResult:
    name: str
    status: str  # PASS | WARN | FAIL | UNAVAILABLE
    detail: str = ""
    fix: str = ""


@dataclass
class DiagnosticReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(c.status == "FAIL" for c in self.checks)

    def render(self) -> str:
        lines = ["=== AI VISION LAB — SYSTEM CHECK ==="]
        for check in self.checks:
            lines.append(f"[{check.status:>11}] {check.name}")
            if check.detail:
                lines.append(f"           {check.detail}")
            if check.fix:
                lines.append(f"           Fix: {check.fix}")
        counts = ", ".join(
            f"{status}={sum(1 for c in self.checks if c.status == status)}"
            for status in ("PASS", "WARN", "FAIL", "UNAVAILABLE")
        )
        lines.append(f"--- {counts} ---")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Individual checks (pure functions, no side effects beyond reads)
# ---------------------------------------------------------------------------
def check_python() -> CheckResult:
    version = sys.version_info
    detail = f"Python {platform.python_version()} ({sys.executable})"
    if version >= (3, 11):
        return CheckResult("PYTHON", "PASS", detail)
    return CheckResult(
        "PYTHON", "FAIL", detail,
        "Install Python 3.11 or newer from python.org/downloads",
    )


def check_dependencies() -> CheckResult:
    from app.utils.protobuf_compat import apply_protobuf_compat

    apply_protobuf_compat()
    missing: list[str] = []
    for module, package in (
        ("cv2", "opencv-python-headless"),
        ("PySide6", "PySide6"),
        ("mediapipe", "mediapipe"),
        ("numpy", "numpy"),
    ):
        try:
            importlib.import_module(module)
        except Exception as exc:  # noqa: BLE001 — protobuf mismatch is not ImportError
            missing.append(f"{package} ({exc.__class__.__name__})")
    if not missing:
        return CheckResult("DEPENDENCIES", "PASS", "all imports resolved")
    return CheckResult(
        "DEPENDENCIES", "FAIL", f"missing: {', '.join(missing)}",
        "Run: python setup.py   or   pip install -r requirements.txt"
        '   (MediaPipe needs protobuf>=4.25.3,<5)',
    )


def check_write_access() -> CheckResult:
    from app.utils.paths import data_dir

    try:
        directory = data_dir()
        probe = directory / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return CheckResult(
            "WRITE ACCESS", "PASS", f"data directory writable: {directory}"
        )
    except OSError as exc:
        return CheckResult(
            "WRITE ACCESS", "FAIL", str(exc),
            "Run the app from a user-writable folder (not Program Files).",
        )


def check_model_files() -> CheckResult:
    from app.vision.model_manager import MODEL_REGISTRY
    from app.utils.paths import models_dir

    directory = models_dir()
    present = []
    missing = []
    for name, (filename, _url, minimum) in MODEL_REGISTRY.items():
        path = directory / filename
        if path.is_file() and path.stat().st_size >= minimum:
            present.append(filename)
        else:
            missing.append(filename)
    if not missing:
        return CheckResult(
            "MODEL FILES", "PASS", f"{len(present)} models present"
        )
    return CheckResult(
        "MODEL FILES", "WARN", f"missing: {', '.join(missing)}",
        "Run: python scripts/download_models.py (needs internet once)",
    )


def check_camera() -> CheckResult:
    try:
        import cv2
    except ImportError:
        return CheckResult("CAMERA", "UNAVAILABLE", "opencv not installed")
    capture = cv2.VideoCapture(0)
    try:
        if not capture.isOpened():
            return CheckResult(
                "CAMERA", "FAIL", "no camera found at index 0",
                "Connect a webcam and check camera permissions.",
            )
        ok, frame = capture.read()
        if not ok or frame is None:
            return CheckResult(
                "CAMERA", "FAIL", "camera opened but delivered no frame",
                "Close other apps using the camera and retry.",
            )
        h, w = frame.shape[:2]
        return CheckResult("CAMERA", "PASS", f"frame {w}x{h} readable")
    finally:
        capture.release()


def _probe_mediapipe_delegate(builder) -> tuple[str, str]:
    """Load a pipeline via ``builder`` and report the real delegate state.

    Returns (state, message) with state in {"gpu", "cpu", "error"}.
    Pure with respect to its argument — unit-tested with a fake builder.
    """
    pipeline = None
    try:
        pipeline = builder()
        errors = pipeline.load_all()
        if errors:
            return "error", f"models failed to load: {list(errors)[:2]}"
        face_module = pipeline.module("face_mesh")
        message = face_module.status_message or "gpu"
        if message == "gpu":
            return "gpu", "GPU delegate active"
        return "cpu", f"GPU delegate unavailable ({message})"
    except Exception as exc:  # noqa: BLE001 — diagnostics must not crash
        return "error", str(exc)[:120]
    finally:
        if pipeline is not None:
            try:
                pipeline.close()
            except Exception:  # noqa: BLE001 — teardown must not crash
                pass


def check_gpu() -> CheckResult:
    """GPU presence + VRAM + MediaPipe GPU delegate support (honest).

    The check name is always "GPU" (the 9-check contract); the delegate
    state is folded into the detail line so UI badge lookups and tests
    stay stable on machines with and without a GPU.
    """
    gpu_present = False
    detail = ""
    vram = ""
    try:
        import subprocess

        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,"
             "memory.free,driver_version",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if output.returncode == 0 and output.stdout.strip():
            gpu_present = True
            fields = [part.strip() for part in output.stdout.strip().split(",")]
            name = fields[0] if fields else "?"
            driver = fields[4] if len(fields) > 4 else "?"
            vram = " · ".join(
                f"{label} {fields[index]}"
                for label, index in (
                    ("total", 1), ("used", 2), ("free", 3)
                )
                if len(fields) > index and fields[index]
            )
            detail = f"{name} · driver {driver}"
            if vram:
                detail += f" · {vram}"
        else:
            detail = "nvidia-smi reported no GPU"
    except (OSError, subprocess.SubprocessError, ValueError):
        detail = "nvidia-smi not available"

    if not gpu_present:
        return CheckResult(
            "GPU", "UNAVAILABLE", detail,
            "CPU mode is fully supported; a GPU is optional.",
        )

    # GPU exists: probe the MediaPipe delegate (may fall back to CPU).
    def _build():
        from app.session.session import GazeSession
        from app.utils.paths import models_dir
        from app.vision.pipeline import build_default_pipeline_with_models

        return build_default_pipeline_with_models(
            models_dir=models_dir(), session=GazeSession(), use_gpu=True
        )

    state, message = _probe_mediapipe_delegate(_build)
    if state == "gpu":
        return CheckResult("GPU", "PASS", f"{detail} · {message}")
    if state == "cpu":
        return CheckResult(
            "GPU", "WARN", f"{detail} · {message}",
            "CPU fallback is active and stable; GPU acceleration depends "
            "on the MediaPipe build.",
        )
    return CheckResult(
        "GPU", "WARN", f"{detail} · {message}",
        "Run scripts/download_models.py",
    )


def _http_json(url: str, timeout: float = 2.0):
    import json
    import urllib.request

    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def check_ollama() -> CheckResult:
    try:
        data = _http_json("http://localhost:11434/api/version", timeout=2.0)
        version = data.get("version", "?")
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            "OLLAMA", "UNAVAILABLE", f"server not reachable ({exc})",
            "Install from ollama.com and run: ollama serve",
        )
    try:
        data = _http_json("http://localhost:11434/api/tags", timeout=2.0)
        models = [m.get("name", "?") for m in data.get("models", [])]
    except Exception:  # noqa: BLE001
        models = []
    if models:
        return CheckResult(
            "OLLAMA", "PASS",
            f"version {version} · models: {', '.join(models[:3])}",
        )
    return CheckResult(
        "OLLAMA", "WARN", "server running but no models installed",
        "Run: ollama pull llama3 (or another model)",
    )


def check_sdwebui() -> CheckResult:
    try:
        data = _http_json("http://127.0.0.1:7860/sdapi/v1/sd-models",
                          timeout=2.0)
        models = [m.get("title", "?") for m in data if isinstance(m, dict)]
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            "SD WEBUI", "UNAVAILABLE", f"not reachable ({exc})",
            "Start AUTOMATIC1111/Forge/SD.Next locally (default port 7860) "
            "— optional.",
        )
    if models:
        return CheckResult(
            "SD WEBUI", "PASS", f"{len(models)} model(s) installed",
        )
    return CheckResult(
        "SD WEBUI", "WARN", "reachable but no models installed",
        "Download a checkpoint into the WebUI models folder.",
    )


def check_storage() -> CheckResult:
    try:
        usage = shutil.disk_usage(os.getcwd())
        free_gb = usage.free / (1024 ** 3)
    except OSError as exc:
        return CheckResult("STORAGE", "FAIL", str(exc))
    if free_gb < 1.0:
        return CheckResult(
            "STORAGE", "FAIL", f"only {free_gb:.1f} GB free",
            "Free disk space; generated images are stored locally.",
        )
    return CheckResult("STORAGE", "PASS", f"{free_gb:.1f} GB free")


_CHECKS: list[tuple[str, Callable[[], CheckResult]]] = [
    ("PYTHON", check_python),
    ("DEPENDENCIES", check_dependencies),
    ("WRITE ACCESS", check_write_access),
    ("MODEL FILES", check_model_files),
    ("CAMERA", check_camera),
    ("GPU", check_gpu),
    ("OLLAMA", check_ollama),
    ("SD WEBUI", check_sdwebui),
    ("STORAGE", check_storage),
]


def run_diagnostics() -> DiagnosticReport:
    """Execute all checks and build the report."""
    report = DiagnosticReport()
    for name, check in _CHECKS:
        try:
            report.checks.append(check())
        except Exception as exc:  # noqa: BLE001 — diagnostics must not crash
            log.exception("Diagnostic check %s failed", name)
            report.checks.append(
                CheckResult(name, "FAIL", f"check crashed: {exc}")
            )
    return report
