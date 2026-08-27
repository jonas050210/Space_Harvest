"""Extended hardware-acceptance probes (Phase 14).

Every probe performs a REAL operation against the configured service and
reports PASS / FAIL / UNTESTABLE with real measurements. Base URLs,
models and timeouts are injectable so the probes are unit-testable
against stub servers — on the target machine they run against the real
Ollama / SD WebUI.

Honesty contract: a service that is not reachable is UNTESTABLE (with
setup instructions), never a fake PASS.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

#: (verdict, detail, metrics) — metrics carries real measurements only.
ProbeResult = tuple[str, str, dict]


def probe_ollama_model_present(
    base_url: str = "http://localhost:11434",
    model: str = "llama3",
    timeout: float = 5.0,
) -> ProbeResult:
    """Configured Ollama model really installed? (real API call)."""
    from app.ai.providers.ollama import OllamaProvider

    provider = OllamaProvider(
        base_url=base_url, model=model, timeout=timeout
    )
    if provider.availability() != "online":
        return (
            "UNTESTABLE",
            f"Ollama not reachable at {base_url} — install from "
            "ollama.com, run 'ollama serve' and 'ollama pull llama3'",
            {},
        )
    models = provider.list_models()
    base_model = model.split(":")[0]
    matches = [m for m in models if m == model or m.split(":")[0] == base_model]
    if matches:
        return (
            "PASS",
            f"model '{model}' installed ({matches[0]})",
            {"installed_models": len(models), "match": matches[0]},
        )
    return (
        "FAIL",
        f"model '{model}' NOT installed — run: ollama pull {model} "
        f"(installed: {', '.join(models[:5]) or 'none'})",
        {"installed_models": len(models)},
    )


def probe_ollama_stream(
    base_url: str = "http://localhost:11434",
    model: str = "llama3",
    timeout: float = 30.0,
    prompt: str = "Reply with the single word: ready",
) -> ProbeResult:
    """Real Ollama streaming + latency measurement.

    Measures: time to first token, total duration, token count.
    """
    from app.ai.providers.ollama import OllamaProvider

    provider = OllamaProvider(
        base_url=base_url, model=model, timeout=timeout
    )
    if provider.availability() != "online":
        return (
            "UNTESTABLE",
            f"Ollama not reachable at {base_url} — install from "
            "ollama.com, run 'ollama serve' and 'ollama pull llama3'",
            {},
        )
    tokens: list[str] = []
    first_token: list[float] = []

    def on_token(text: str) -> None:
        tokens.append(text)
        if not first_token:
            first_token.append(time.perf_counter())

    started = time.perf_counter()
    try:
        provider.complete(
            [{"role": "user", "content": prompt}],
            on_token=on_token,
        )
    except RuntimeError as exc:
        return ("FAIL", f"streaming failed: {exc}", {})
    elapsed = time.perf_counter() - started
    first_ms = (first_token[0] - started) * 1000.0 if first_token else None
    metrics = {
        "total_ms": round(elapsed * 1000.0, 1),
        "first_token_ms": round(first_ms, 1) if first_ms else None,
        "tokens": len(tokens),
        "answer": "".join(tokens)[:60],
    }
    return (
        "PASS",
        f"streaming OK — {len(tokens)} tokens, "
        f"first token {metrics['first_token_ms']} ms, "
        f"total {metrics['total_ms']} ms",
        metrics,
    )


def probe_sd_txt2img(
    base_url: str = "http://127.0.0.1:7860",
    timeout: float = 120.0,
    prompt: str = "a flat gray test card, minimal",
) -> ProbeResult:
    """Real SD WebUI txt2img: PNG validation, seed readback, progress."""
    from app.image.providers.sdwebui import SDWebUIProvider

    provider = SDWebUIProvider(
        base_url=base_url, width=256, height=256, timeout=timeout
    )
    if provider.availability() != "online":
        return (
            "UNTESTABLE",
            f"SD WebUI not reachable at {base_url} — start "
            "AUTOMATIC1111/Forge/SD.Next locally (optional)",
            {},
        )
    progress: list[float] = []
    started = time.perf_counter()
    try:
        image = provider.generate(
            prompt,
            steps=2,
            seed=12345,
            on_progress=progress.append,
        )
    except RuntimeError as exc:
        return ("FAIL", f"txt2img failed: {exc}", {})
    elapsed = time.perf_counter() - started
    seed = image.extra.get("seed")
    metrics = {
        "duration_ms": round(elapsed * 1000.0, 1),
        "width": image.width,
        "height": image.height,
        "seed": seed,
        "progress_samples": len(progress),
        "png_bytes": len(image.png_bytes),
    }
    if not image.png_bytes:
        return ("FAIL", "txt2img returned no image data", metrics)
    if seed != 12345:
        return (
            "FAIL",
            f"seed readback failed (expected 12345, got {seed})",
            metrics,
        )
    if progress:
        out_of_range = [p for p in progress if not 0.0 <= p <= 1.0]
        if out_of_range:
            return ("FAIL", f"progress out of range: {out_of_range[:3]}", metrics)
    return (
        "PASS",
        f"txt2img OK — {image.width}x{image.height}, "
        f"{len(image.png_bytes)} bytes, seed {seed}, "
        f"{len(progress)} progress samples, "
        f"{metrics['duration_ms']} ms",
        metrics,
    )


def probe_sd_img2img(
    init_image: bytes,
    base_url: str = "http://127.0.0.1:7860",
    timeout: float = 120.0,
    prompt: str = "same image, slightly brighter",
) -> ProbeResult:
    """Real SD WebUI img2img on a previously generated PNG."""
    from app.image.providers.sdwebui import SDWebUIProvider

    provider = SDWebUIProvider(
        base_url=base_url, width=256, height=256, timeout=timeout
    )
    if provider.availability() != "online":
        return (
            "UNTESTABLE",
            f"SD WebUI not reachable at {base_url} — start it locally "
            "(optional)",
            {},
        )
    started = time.perf_counter()
    try:
        image = provider.generate_img2img(
            prompt, init_image, steps=2, seed=12345
        )
    except RuntimeError as exc:
        return ("FAIL", f"img2img failed: {exc}", {})
    metrics = {
        "duration_ms": round((time.perf_counter() - started) * 1000.0, 1),
        "seed": image.extra.get("seed"),
        "png_bytes": len(image.png_bytes),
    }
    if not image.png_bytes:
        return ("FAIL", "img2img returned no image data", metrics)
    return (
        "PASS",
        f"img2img OK — {len(image.png_bytes)} bytes, "
        f"seed {metrics['seed']}, {metrics['duration_ms']} ms",
        metrics,
    )


def probe_startup_shutdown(data_dir: Path) -> ProbeResult:
    """Real app construction + clean close (offscreen-safe).

    Uses an isolated data directory with the bundled models copied in
    (the same files the target machine loads), so the measurement
    includes the real module initialization.
    """
    import os
    import shutil

    os.environ["QT_QPA_PLATFORM"] = os.environ.get(
        "QT_QPA_PLATFORM", "offscreen"
    )
    models_source = PROJECT_ROOT / "data" / "models"
    if models_source.is_dir() and not (data_dir / "models").exists():
        shutil.copytree(models_source, data_dir / "models")
    os.environ["AI_VISION_LAB_DATA_DIR"] = str(data_dir)
    try:
        from PySide6.QtWidgets import QApplication

        from app.config.settings import SettingsService
        from app.ui.main_window import MainWindow
        from app.ui.theme import apply_theme
        from app.utils.paths import settings_path

        app = QApplication.instance() or QApplication([])
        apply_theme(app, dark=True)
        service = SettingsService(settings_path())
        service.load()
        service.update(image_provider="mock")
        started = time.perf_counter()
        window = MainWindow(service, defer_vision_load=True)
        window.show()
        window.load_vision_modules_now()
        from PySide6.QtCore import QCoreApplication

        for _ in range(5):
            QCoreApplication.processEvents()
        startup_ms = (time.perf_counter() - started) * 1000.0

        started = time.perf_counter()
        window.close()
        for _ in range(5):
            QCoreApplication.processEvents()
        shutdown_ms = (time.perf_counter() - started) * 1000.0
        return (
            "PASS",
            f"startup {startup_ms:.0f} ms · shutdown {shutdown_ms:.0f} ms "
            "(window + deferred module load, offscreen)",
            {"startup_ms": round(startup_ms, 1),
             "shutdown_ms": round(shutdown_ms, 1)},
        )
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"startup/shutdown test failed: {exc}", {})


def probe_exe_presence() -> ProbeResult:
    """Windows EXE presence check (honest — never claims a runtime test)."""
    exe = PROJECT_ROOT / "dist" / "AI-Vision-Lab" / "AI-Vision-Lab.exe"
    if sys.platform != "win32" and not exe.exists():
        return (
            "UNTESTABLE",
            "no Windows build present — run packaging\\windows.bat on the "
            "target machine, then verify the EXE starts",
            {},
        )
    if not exe.exists():
        return (
            "FAIL",
            "dist/AI-Vision-Lab/AI-Vision-Lab.exe missing — run "
            "packaging\\windows.bat",
            {},
        )
    size_mb = exe.stat().st_size / (1024 * 1024)
    return (
        "PASS",
        f"EXE present ({size_mb:.1f} MB onedir bundle) — start it on "
        "Windows to verify runtime",
        {"size_mb": round(size_mb, 1)},
    )


def probe_shortcut_presence() -> ProbeResult:
    """Desktop shortcut presence check (Windows only)."""
    if sys.platform != "win32":
        return (
            "UNTESTABLE",
            "shortcut creation is Windows-only — run "
            "scripts\\create_shortcut.ps1 on the target machine",
            {},
        )
    try:
        import ctypes

        desktop = (
            ctypes.windll.shell32.SHGetFolderPathW(
                None, 0x0010, None, 0, ctypes.create_unicode_buffer(260)
            )
        )
    except Exception:  # noqa: BLE001
        return ("UNTESTABLE", "could not resolve the Desktop folder", {})
    shortcut = Path(desktop) / "AI Vision Lab.lnk"
    if shortcut.exists():
        return ("PASS", f"shortcut present: {shortcut}", {})
    return (
        "FAIL",
        "no 'AI Vision Lab.lnk' on the Desktop — run "
        "scripts\\create_shortcut.ps1",
        {},
    )


def collect_existing_reports(
    directory: Optional[Path] = None,
) -> list[Path]:
    """Find previously written hardware reports (never invented)."""
    root = directory or PROJECT_ROOT
    candidates = list(root.glob("smoke*.json")) + \
        list(root.glob("acceptance*.json")) + \
        list(root.glob("stability*.json")) + \
        list(root.glob("hardware*.json"))
    return sorted(set(candidates))


def summarize_report(path: Path) -> str:
    """One-line honest summary of an existing JSON report."""
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"{path.name}: unreadable ({exc})"
    summary = data.get("summary") or {}
    if "smoke" in summary and "workflow" in summary:
        return (
            f"{path.name}: smoke "
            f"{summary['smoke'].get('pass', 0)}P/"
            f"{summary['smoke'].get('fail', 0)}F/"
            f"{summary['smoke'].get('untestable', 0)}U · workflow "
            f"{summary['workflow'].get('pass', 0)}P/"
            f"{summary['workflow'].get('fail', 0)}F/"
            f"{summary['workflow'].get('untestable', 0)}U · "
            f"verdict {summary.get('verdict', '?')}"
        )
    if "samples" in data:
        return (
            f"{path.name}: stability — {data.get('frames', 0)} frames, "
            f"{len(data.get('samples', []))} samples, "
            f"feed {data.get('feed', '?')}"
        )
    return f"{path.name}: {summary or 'no summary'}"


#: Full verification matrix (Phase 14, 29 items) — every item maps to a
#: probe/step so the acceptance report is complete and honest.
VERIFICATION_MATRIX: tuple[tuple[str, str], ...] = (
    ("PYTHON", "diagnostics"),
    ("DEPENDENCIES", "diagnostics"),
    ("MODELS", "diagnostics"),
    ("CAMERA", "diagnostics"),
    ("CAMERA RESOLUTION", "smoke"),
    ("CAMERA FPS", "smoke"),
    ("CAMERA RECONNECT", "smoke"),
    ("GPU", "smoke"),
    ("NVIDIA DRIVER", "smoke"),
    ("VRAM", "smoke"),
    ("MEDIAPIPE GPU DELEGATE", "smoke"),
    ("CPU FALLBACK", "smoke"),
    ("OLLAMA AVAILABILITY", "diagnostics"),
    ("OLLAMA MODEL", "probe_ollama_model"),
    ("OLLAMA STREAMING", "probe_ollama_stream"),
    ("OLLAMA LATENCY", "probe_ollama_stream"),
    ("SD WEBUI AVAILABILITY", "diagnostics"),
    ("SD CHECKPOINT", "smoke"),
    ("TXT2IMG", "probe_sd_txt2img"),
    ("IMG2IMG", "probe_sd_img2img"),
    ("REAL PROGRESS", "probe_sd_txt2img"),
    ("SEED", "probe_sd_txt2img"),
    ("PROVIDER CAPABILITIES", "smoke"),
    ("E2E WORKFLOW", "manual"),
    ("STABILITY", "stability_probe"),
    ("EXE", "probe_exe_presence"),
    ("SHORTCUT", "probe_shortcut_presence"),
    ("STARTUP", "probe_startup_shutdown"),
    ("SHUTDOWN", "probe_startup_shutdown"),
)
