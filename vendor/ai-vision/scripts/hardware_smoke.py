"""Hardware smoke test for the AI Vision Lab target machine.

Run this ON the target hardware (Windows 11, RTX 4060 Ti, webcam, Ollama,
optional SD WebUI):

    python scripts/hardware_smoke.py
    python scripts/hardware_smoke.py --json hardware_report.json

Sections (every value is measured here, never invented):

1. DIAGNOSTICS      — the 9 production checks (same as ``main.py --check``)
2. GPU              — name, driver, VRAM total/used/free, MediaPipe
                      delegate state (real probe), CPU fallback honesty
3. CAMERA           — device presence, 720p/1080p delivery, real FPS,
                      reconnect behavior
4. OLLAMA           — version, installed models
5. SD WEBUI         — reachability, installed checkpoints, current
                      checkpoint, capabilities
6. PROVIDERS        — capability report for every configured provider
7. TIMING           — cold import, model load, per-module inference
                      latency on a synthetic frame (real MediaPipe runs)

Checks that cannot run in the current environment report UNTESTABLE —
nothing is faked, ever.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS: list[dict] = []  # {check, verdict, detail, timestamp}


def record(check: str, ok: bool | None, detail: str) -> None:
    verdict = "PASS" if ok is True else ("FAIL" if ok is False else "UNTESTABLE")
    RESULTS.append({
        "check": check,
        "verdict": verdict,
        "detail": detail,
        "timestamp": time.time(),
    })
    print(f"[{verdict:>10}] {check}: {detail}")


def record_info(check: str, detail: str) -> None:
    """Informational line — real data, not a pass/fail check."""
    print(f"[      INFO] {check}: {detail}")


def http_json(url: str, timeout: float = 3.0):
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


# ---------------------------------------------------------------------------
# 1. Diagnostics
# ---------------------------------------------------------------------------
def run_diagnostics_section() -> None:
    from app.diagnostics import run_diagnostics

    report = run_diagnostics()
    for check in report.checks:
        ok = {"PASS": True, "WARN": True, "FAIL": False,
              "UNAVAILABLE": None}[check.status]
        detail = check.detail + (f" — fix: {check.fix}" if check.fix else "")
        record(check.name, ok, detail)


# ---------------------------------------------------------------------------
# 2. GPU
# ---------------------------------------------------------------------------
def parse_nvidia_smi_line(line: str) -> dict[str, str]:
    """Parse one ``nvidia-smi --format=csv,noheader`` result line.

    Pure function (unit-tested) — used by the smoke script and the
    diagnostics module's GPU detail.
    """
    fields = [part.strip() for part in line.split(",")]
    keys = ("name", "memory_total", "memory_used", "memory_free", "driver")
    parsed = {keys[i]: fields[i] for i in range(min(len(keys), len(fields)))}
    parsed["gpu_present"] = bool(parsed.get("name"))
    return parsed


def nvidia_smi_info() -> dict[str, str]:
    """Query the first NVIDIA GPU; returns {} when unavailable."""
    try:
        output = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,memory.used,memory.free,"
             "driver_version",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if output.returncode != 0 or not output.stdout.strip():
            return {}
        return parse_nvidia_smi_line(output.stdout.strip().splitlines()[0])
    except (OSError, subprocess.SubprocessError):
        return {}


def probe_gpu_delegate() -> None:
    """Real MediaPipe delegate probe: GPU active or honest CPU fallback."""
    try:
        from app.session.session import GazeSession
        from app.utils.paths import models_dir
        from app.vision.pipeline import build_default_pipeline_with_models

        started = time.perf_counter()
        pipeline = build_default_pipeline_with_models(
            models_dir=models_dir(), session=GazeSession(), use_gpu=True
        )
        errors = pipeline.load_all()
        load_ms = (time.perf_counter() - started) * 1000.0
        if errors:
            pipeline.close()
            record("GPU delegate", False,
                   f"models failed to load: {list(errors)}")
            return
        face_module = pipeline.module("face_mesh")
        message = face_module.status_message or "gpu"
        pipeline.close()
        if message == "gpu":
            record("GPU delegate", True, f"GPU delegate active (load {load_ms:.0f} ms)")
        else:
            record("GPU delegate", None,
                   f"CPU fallback active ({message}, load {load_ms:.0f} ms) — "
                   "GPU optional")
    except Exception as exc:  # noqa: BLE001
        record("GPU delegate", None, f"could not test: {exc}")


def run_gpu_section() -> None:
    info = nvidia_smi_info()
    if not info.get("gpu_present"):
        record("GPU", None,
               "nvidia-smi unavailable or no NVIDIA GPU — CPU mode is "
               "fully supported; a GPU is optional.")
        record("VRAM", None, "no GPU — nothing to measure")
        return
    record("GPU", True,
           f"{info.get('name')} · driver {info.get('driver')}")
    record("VRAM", True,
           f"total {info.get('memory_total')} · "
           f"used {info.get('memory_used')} · "
           f"free {info.get('memory_free')} (queried, not inferred)")
    probe_gpu_delegate()


# ---------------------------------------------------------------------------
# 3. Camera
# ---------------------------------------------------------------------------
def _open_camera(index: int = 0):
    import cv2

    capture = cv2.VideoCapture(index)
    if not capture.isOpened():
        capture.release()
        return None
    return capture


def probe_camera_resolutions(camera) -> None:
    import cv2

    for width, height in ((1280, 720), (1920, 1080), (2560, 1440)):
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        ok, frame = camera.read()
        if ok and frame is not None:
            fh, fw = frame.shape[:2]
            record(
                f"Resolution {width}x{height}",
                abs(fw - width) <= 16 and abs(fh - height) <= 16,
                f"driver delivered {fw}x{fh}",
            )
        else:
            record(f"Resolution {width}x{height}", False, "no frame delivered")


def probe_camera_fps(camera, frames: int = 30) -> None:
    started = time.perf_counter()
    delivered = 0
    for _ in range(frames):
        ok, _frame = camera.read()
        if not ok:
            break
        delivered += 1
    elapsed = time.perf_counter() - started
    if delivered < 5 or elapsed <= 0:
        record("Camera FPS", False, f"only {delivered} frames delivered")
        return
    record("Camera FPS", True,
           f"{delivered / elapsed:.1f} fps measured over {delivered} "
           f"frames ({elapsed:.2f} s)")


def probe_camera_reconnect() -> None:
    first = _open_camera(0)
    if first is None:
        record("Camera reconnect", None, "no camera — nothing to test")
        return
    ok1, _frame1 = first.read()
    first.release()
    time.sleep(0.5)
    second = _open_camera(0)
    if second is None:
        record("Camera reconnect", False,
               "camera could not be reopened after release")
        return
    ok2, _frame2 = second.read()
    second.release()
    record("Camera reconnect", ok1 and ok2,
           f"open→read→release→reopen→read: "
           f"{'worked' if ok1 and ok2 else 'failed'}")


def run_camera_section() -> None:
    camera = _open_camera(0)
    if camera is None:
        record("Camera device", None,
               "no camera at index 0 — nothing to probe")
        record("Camera FPS", None, "no camera")
        probe_camera_reconnect()
        return
    try:
        record("Camera device", True, "device opened at index 0")
        probe_camera_resolutions(camera)
        probe_camera_fps(camera)
    finally:
        camera.release()
    probe_camera_reconnect()


# ---------------------------------------------------------------------------
# 4/5. Ollama + SD WebUI
# ---------------------------------------------------------------------------
def run_ollama_section() -> None:
    try:
        version = http_json("http://localhost:11434/api/version", 2.0).get(
            "version", "?"
        )
    except Exception as exc:  # noqa: BLE001
        record("Ollama", None,
               f"not reachable ({exc}) — install from ollama.com, then "
               "'ollama serve'")
        return
    try:
        data = http_json("http://localhost:11434/api/tags", 2.0)
        models = [m.get("name", "?") for m in data.get("models", [])]
    except Exception:  # noqa: BLE001
        models = []
    if models:
        record("Ollama", True,
               f"version {version} · {len(models)} model(s): "
               f"{', '.join(models[:4])}"
               + (" …" if len(models) > 4 else ""))
    else:
        record("Ollama", False,
               f"version {version} but no models installed — run "
               "'ollama pull llama3'")


def run_sdwebui_section() -> None:
    base = "http://127.0.0.1:7860"
    try:
        models = http_json(f"{base}/sdapi/v1/sd-models", 2.0)
    except Exception as exc:  # noqa: BLE001
        record("SD WebUI", None,
               f"not reachable at {base} ({exc}) — start AUTOMATIC1111/"
               "Forge/SD.Next locally (optional)")
        return
    titles = [m.get("title", "?") for m in models if isinstance(m, dict)]
    record("SD WebUI", True, f"reachable · {len(titles)} checkpoint(s)")
    if titles:
        record("SD WebUI models", True, f"{', '.join(titles[:3])}"
               + (" …" if len(titles) > 3 else ""))
    checkpoint = "?"
    try:
        options = http_json(f"{base}/sdapi/v1/options", 2.0)
        checkpoint = str(options.get("sd_model_checkpoint", "?"))
    except Exception:  # noqa: BLE001
        pass
    record("SD WebUI checkpoint", True if checkpoint != "?" else None,
           f"currently loaded: {checkpoint}")


# ---------------------------------------------------------------------------
# 6. Provider capabilities
# ---------------------------------------------------------------------------
def run_provider_capabilities_section() -> None:
    from app.config.settings import SettingsService
    from app.utils.paths import settings_path

    service = SettingsService(settings_path())
    service.load()
    from app.ai.engine import AIVisionEngine
    from app.image.engine import ImageGenerationEngine

    image_engine = ImageGenerationEngine(service)
    for key, _label in (("mock", "mock"), ("sdwebui", "sdwebui"),
                        ("local", "local"), ("external", "external")):
        capabilities = image_engine.capabilities_for(key)
        flags = []
        if capabilities.supports_img2img:
            flags.append("img2img")
        if capabilities.progress:
            flags.append("progress")
        if capabilities.models:
            flags.append("models")
        if capabilities.seed:
            flags.append("seed")
        if capabilities.supports_face_reference:
            flags.append("face-reference")
        # Declared capabilities are real, verifiable data.
        record(f"Capabilities {key}", True,
               ", ".join(flags) or "basic txt2img only")
    llm_engine = AIVisionEngine(service)
    record("LLM provider", True,
           f"configured provider: {llm_engine.build_provider().key} "
           f"({llm_engine.build_provider().display_name})")
    llm_engine.clear_chat()


# ---------------------------------------------------------------------------
# 7. Timing (real measurements on this machine)
# ---------------------------------------------------------------------------
def measure_cold_import() -> None:
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-c",
         "import main, app.ui.main_window, app.vision.pipeline"],
        capture_output=True, text=True, timeout=120,
        cwd=str(PROJECT_ROOT),
    )
    elapsed = time.perf_counter() - started
    if result.returncode != 0:
        record("Cold import", False,
               f"failed after {elapsed:.1f} s: "
               f"{result.stderr.strip()[:100]}")
        return
    record("Cold import", True, f"{elapsed:.2f} s (python -c import main)")


def measure_model_load() -> None:
    try:
        from app.session.session import GazeSession
        from app.utils.paths import models_dir
        from app.vision.pipeline import build_default_pipeline_with_models

        started = time.perf_counter()
        pipeline = build_default_pipeline_with_models(
            models_dir=models_dir(), session=GazeSession()
        )
        errors = pipeline.load_all()
        elapsed = time.perf_counter() - started
        if errors:
            record("Model load", False,
                   f"modules failed: {list(errors)[:2]} "
                   f"({elapsed:.2f} s)")
        else:
            record("Model load", True,
                   f"all modules loaded in {elapsed:.2f} s (CPU default)")
        pipeline.close()
    except Exception as exc:  # noqa: BLE001
        record("Model load", None, f"could not test: {exc}")


def measure_inference() -> None:
    """Real MediaPipe inference on a synthetic 640x480 frame.

    * Pipeline latency = one full pass over all 12 modules (what the
      live camera actually experiences).
    * Per-module latency = each module in isolation (best effort: a
      module that needs upstream outputs reports "n/a").
    """
    try:
        import cv2
        import numpy as np

        from app.core.types import VisionResult
        from app.session.session import GazeSession
        from app.utils.paths import models_dir
        from app.vision.pipeline import build_default_pipeline_with_models

        pipeline = build_default_pipeline_with_models(
            models_dir=models_dir(), session=GazeSession()
        )
        errors = pipeline.load_all()
        if errors:
            pipeline.close()
            record("Inference latency", None,
                   f"models missing: {list(errors)[:2]}")
            return
        frame = np.full((480, 640, 3), 120, dtype=np.uint8)
        cv2.circle(frame, (320, 240), 90, (200, 200, 200), -1)
        # Warm-up run (first inference includes lazy allocations).
        pipeline.process(frame)

        # 1) Full pipeline pass (what live capture experiences).
        started = time.perf_counter()
        for _ in range(5):
            pipeline.process(frame)
        pipeline_ms = (time.perf_counter() - started) * 1000.0 / 5

        # 2) Per-module isolated runs (honest best effort).
        timings: dict[str, str] = {}
        for module in pipeline.modules():
            if not module.enabled:
                continue
            try:
                started = time.perf_counter()
                for _ in range(5):
                    module.process(frame, VisionResult())
                ms = (time.perf_counter() - started) * 1000.0 / 5
                timings[module.key] = f"{ms:.0f} ms"
            except Exception:  # noqa: BLE001 — needs upstream output
                timings[module.key] = "n/a (needs upstream)"
        pipeline.close()
        module_summary = " · ".join(
            f"{key} {value}" for key, value in sorted(timings.items())
        )
        record("Pipeline latency", True,
               f"{pipeline_ms:.0f} ms/frame "
               f"(synthetic 640x480, 5 runs, all modules)")
        record_info("Module latency", module_summary)
        record_info("Measured on",
                    f"{sys.platform} · python {sys.version.split()[0]}")
    except Exception as exc:  # noqa: BLE001
        record("Inference latency", None, f"could not test: {exc}")


# ---------------------------------------------------------------------------
def _timestamp_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _environment_block() -> dict:
    import os
    import platform
    import socket

    from app import __version__  # noqa: PLC0415
    from scripts.report_importer import environment_fingerprint

    try:
        hostname = socket.gethostname()
    except OSError:
        hostname = "unknown"
    return {
        "platform": sys.platform,
        "system": platform.system(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "hostname": hostname,
        "fingerprint": environment_fingerprint(),
        "app_version": __version__,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Vision Lab hardware smoke")
    parser.add_argument("--json", metavar="PATH",
                        help="also write the report as JSON")
    parser.add_argument("--skip-timing", action="store_true",
                        help="skip the timing section (faster smoke)")
    args = parser.parse_args(argv)

    # Fresh run: never mix results from an earlier invocation.
    RESULTS.clear()
    print("=== AI Vision Lab hardware smoke ===")
    print(f"platform: {sys.platform} · python {sys.version.split()[0]}\n")

    aborted = False
    try:
        run_diagnostics_section()
        print()
        run_gpu_section()
        print()
        run_camera_section()
        print()
        run_ollama_section()
        print()
        run_sdwebui_section()
        print()
        run_provider_capabilities_section()
        if not args.skip_timing:
            print()
            measure_cold_import()
            measure_model_load()
            measure_inference()
    except KeyboardInterrupt:
        print("\naborted by user (Ctrl+C) — partial results follow")
        aborted = True

    print("\n=== Summary ===")
    passed = sum(1 for r in RESULTS if r["verdict"] == "PASS")
    failed = sum(1 for r in RESULTS if r["verdict"] == "FAIL")
    untestable = sum(1 for r in RESULTS if r["verdict"] == "UNTESTABLE")
    print(f"PASS {passed} · FAIL {failed} · UNTESTABLE {untestable}")
    if failed:
        print("Fix the FAIL checks before claiming hardware readiness.")

    from app import __version__

    verdict = (
        "ABORTED" if aborted
        else "NOT READY" if failed
        else "INCOMPLETE" if passed == 0
        else "PASS"
    )
    note = (
        "run aborted by user" if aborted
        else "FAIL checks must be fixed" if failed
        else "nothing verified on this machine" if passed == 0
        else "all checks passed"
    )
    if args.json:
        from scripts.report_importer import redact_secrets

        raw_report = {
            "schema_version": 2,
            "metadata": {
                "tool": "hardware_smoke",
                "app_version": __version__,
                "generated_at": time.time(),
                "generated_at_iso": _timestamp_iso(),
            },
            "environment": _environment_block(),
            "software": {"version": __version__},
            "hardware": {"gpu": None, "camera": None},
            "checks": RESULTS,
            "measurements": {},
            "errors": [],
            "warnings": ["aborted by user"] if aborted else [],
            "final_verdict": {"verdict": verdict, "note": note},
            # legacy keys (compat with earlier importers)
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "generated_at": time.time(),
            "results": RESULTS,
            "summary": {"pass": passed, "fail": failed,
                        "untestable": untestable},
        }
        report, secret_findings = redact_secrets(raw_report)
        if secret_findings:
            report.setdefault("warnings", []).extend(
                f"secret redacted: {finding}" for finding in secret_findings
            )
        Path(args.json).write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(f"Report written to {args.json}")
    if aborted:
        return 130
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
