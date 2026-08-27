"""Long-run stability probe (Phase 13B / 15).

Runs the real vision pipeline (demo camera by default, or index N with
``--camera``) for N minutes while sampling process memory and thread
count. Reports honest growth numbers — nothing is inferred.

    python scripts/stability_probe.py --minutes 5
    python scripts/stability_probe.py --minutes 10 --camera 0 --json run.json

Measured and reported:

* frames + FPS (frames / elapsed, real)
* RSS start/end/peak (psutil, /proc or ctypes — without any source the
  memory column is UNTESTABLE)
* thread count start/end/peak
* read failures + camera reconnects (real camera only: up to 3
  reopen attempts, each counted)
* errors + crashes (any unexpected exception is recorded, the run
  reports honestly instead of dying silently)

The JSON report uses the v2 schema (metadata / environment / software /
hardware / measurements / errors / final_verdict) and never contains
secrets.

* ``--camera``: real webcam index. Without it the demo feed runs —
  clearly labeled "DEMO FEED", not real hardware.

Exit codes: 0 stable, 1 real failure, 130 aborted by user.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import __version__  # noqa: E402
from scripts.report_importer import environment_fingerprint  # noqa: E402

#: Consecutive failed reads before a reconnect attempt (real camera).
_MAX_READ_FAILURES = 10
#: How many reconnect attempts are made before giving up.
_MAX_RECONNECTS = 3
#: Interval between samples (seconds).
_SAMPLE_INTERVAL = 5.0


# ---------------------------------------------------------------------------
# Measurement sources (stdlib only; psutil optional)
# ---------------------------------------------------------------------------
def _memory_mb() -> float | None:
    try:
        import psutil  # optional

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        pass
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/status", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024.0  # kB -> MB
        except OSError:
            return None
    if sys.platform == "win32":
        from app.utils.performance import _win32_rss_mb

        return _win32_rss_mb()
    return None


def _thread_count() -> int | None:
    try:
        import psutil  # optional

        return psutil.Process().num_threads()
    except ImportError:
        pass
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/status", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("Threads:"):
                        return int(line.split()[1])
        except OSError:
            return None
    return None


def _timestamp_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _environment_block() -> dict:
    return {
        "platform": sys.platform,
        "system": platform.system(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "hostname": _safe_hostname(),
        "fingerprint": environment_fingerprint(),
    }


def _safe_hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return "unknown"


# ---------------------------------------------------------------------------
# Camera source (real camera with reconnect, or the demo feed)
# ---------------------------------------------------------------------------
class _CameraSource:
    """Real webcam wrapper: counts read failures and reconnects."""

    def __init__(self, index: int):
        import cv2

        self._index = index
        self._cv2 = cv2
        self._capture = cv2.VideoCapture(index)
        self.read_failures = 0      # consecutive failures (reset on success)
        self.total_failures = 0     # total failures across the whole run
        self.reconnects = 0
        self.errors: list[str] = []

    def is_opened(self) -> bool:
        return self._capture is not None and self._capture.isOpened()

    def read(self):
        """One frame; auto-reconnects after repeated failures (honest)."""
        if self._capture is None or not self._capture.isOpened():
            if not self._try_reconnect():
                return False, None
        ok, frame = self._capture.read()
        if ok and frame is not None:
            self.read_failures = 0
            return True, frame
        self.read_failures += 1
        self.total_failures += 1
        if self.read_failures >= _MAX_READ_FAILURES:
            self.errors.append(
                f"camera lost after {_MAX_READ_FAILURES} consecutive "
                "failed reads"
            )
            if not self._try_reconnect():
                return False, None
        time.sleep(0.01)
        return False, None

    def _try_reconnect(self) -> bool:
        if self.reconnects >= _MAX_RECONNECTS:
            self.errors.append(
                f"gave up after {_MAX_RECONNECTS} reconnect attempts"
            )
            return False
        self.reconnects += 1
        if self._capture is not None:
            self._capture.release()
        self._capture = self._cv2.VideoCapture(self._index)
        if not self._capture.isOpened():
            return False
        self.read_failures = 0
        return True

    def release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Vision Lab stability probe")
    parser.add_argument("--minutes", type=float, default=3.0,
                        help="probe duration in minutes (default 3)")
    parser.add_argument("--camera", type=int, default=None,
                        help="real camera index (default: demo feed)")
    parser.add_argument("--json", metavar="PATH",
                        help="write the samples as JSON")
    args = parser.parse_args(argv)

    print("=== AI Vision Lab stability probe ===")
    feed = "DEMO FEED (simulated camera)" if args.camera is None \
        else f"real camera index {args.camera}"
    print(f"feed: {feed} · duration: {args.minutes} min · "
          f"machine: {sys.platform}")

    from app.session.session import GazeSession
    from app.utils.paths import models_dir
    from app.vision.pipeline import build_default_pipeline_with_models

    session = GazeSession()
    pipeline = build_default_pipeline_with_models(
        models_dir=models_dir(), session=session
    )
    errors = pipeline.load_all()
    if errors:
        print(f"[FAIL] models missing: {list(errors)[:3]}")
        pipeline.close()
        return 1
    print("[PASS] pipeline loaded")

    demo_mode = args.camera is None
    if demo_mode:
        from app.demo.frames import DemoFrameSource

        source: object = DemoFrameSource(0)
    else:
        camera = _CameraSource(args.camera)
        if not camera.is_opened():
            print(f"[FAIL] camera {args.camera} could not be opened")
            pipeline.close()
            return 1
        source = camera

    samples: list[dict] = []
    frames = 0
    run_errors: list[str] = []
    started = time.monotonic()
    deadline = started + args.minutes * 60.0
    next_sample = started
    aborted = False
    try:
        while time.monotonic() < deadline:
            try:
                ok, frame = source.read()
            except Exception as exc:  # noqa: BLE001 — honest error, keep going
                run_errors.append(f"read error: {exc}")
                ok, frame = False, None
            if not ok or frame is None:
                continue
            try:
                result = pipeline.process(frame)
            except Exception as exc:  # noqa: BLE001 — record, keep going
                run_errors.append(f"pipeline error: {exc}")
                continue
            frames += 1
            if result is None:
                continue
            now = time.monotonic()
            if now >= next_sample:
                next_sample = now + _SAMPLE_INTERVAL
                samples.append({
                    "t": round(now - started, 1),
                    "frames": frames,
                    "memory_mb": _memory_mb(),
                    "threads": _thread_count(),
                })
                print(f"  t={samples[-1]['t']:7.1f}s frames={frames:6d} "
                      f"rss={samples[-1]['memory_mb']} MB "
                      f"threads={samples[-1]['threads']}")
    except KeyboardInterrupt:
        print("probe stopped by user (Ctrl+C)")
        aborted = True
    finally:
        source.release()
        pipeline.close()

    elapsed = time.monotonic() - started
    fps = frames / elapsed if elapsed > 0 else 0.0
    print(f"\n=== Result ({elapsed:.1f} s, {frames} frames, "
          f"{fps:.1f} fps) ===")
    if not samples:
        print("no samples collected")
        return 1

    memory_values = [s["memory_mb"] for s in samples if s["memory_mb"]]
    thread_values = [s["threads"] for s in samples if s["threads"]]
    measurements = {
        "duration_s": round(elapsed, 1),
        "frames": frames,
        "fps": round(fps, 1),
        "rss_start_mb": memory_values[0] if memory_values else None,
        "rss_end_mb": memory_values[-1] if memory_values else None,
        "rss_peak_mb": max(memory_values) if memory_values else None,
        "rss_growth_mb": (
            round(memory_values[-1] - memory_values[0], 1)
            if memory_values else None
        ),
        "threads_start": thread_values[0] if thread_values else None,
        "threads_end": thread_values[-1] if thread_values else None,
        "threads_peak": max(thread_values) if thread_values else None,
        "read_failures": getattr(source, "total_failures",
                                  getattr(source, "read_failures", 0)),
        "reconnects": getattr(source, "reconnects", 0),
    }
    if memory_values:
        print(f"RSS: start {memory_values[0]:.1f} MB · "
              f"end {memory_values[-1]:.1f} MB · "
              f"growth {measurements['rss_growth_mb']:+.1f} MB "
              f"(peak {max(memory_values):.1f} MB)")
    else:
        print("RSS: UNTESTABLE (no measurement source on this machine)")
    if thread_values:
        print(f"THREADS: start {thread_values[0]} · "
              f"end {thread_values[-1]} (peak {max(thread_values)})")
    else:
        print("THREADS: UNTESTABLE")
    if not demo_mode:
        print(f"CAMERA: {measurements['read_failures']} read failures · "
              f"{measurements['reconnects']} reconnects")
    for error in run_errors:
        print(f"  ERROR: {error}")

    if run_errors:
        verdict = "FAIL"
    elif memory_values and measurements["rss_growth_mb"] >= 100:
        verdict = "WATCH MEMORY GROWTH"
    elif aborted:
        verdict = "ABORTED"
    elif memory_values or thread_values:
        verdict = "STABLE"
    else:
        verdict = "UNTESTABLE"
    print(f"Verdict: {verdict}")

    if args.json:
        report = {
            "schema_version": 2,
            "metadata": {
                "tool": "stability_probe",
                "app_version": __version__,
                "generated_at": time.time(),
                "generated_at_iso": _timestamp_iso(),
            },
            "environment": _environment_block(),
            "software": {"version": __version__},
            "hardware": {
                "camera": None if demo_mode else {"index": args.camera},
                "gpu": None,
            },
            "feed": feed,
            "measurements": measurements,
            "samples": samples,
            "errors": run_errors,
            "warnings": [],
            "final_verdict": {"verdict": verdict,
                              "note": "real run, real numbers"},
            # legacy keys (compat with earlier importers)
            "duration_s": round(elapsed, 1),
            "frames": frames,
            "summary": {"verdict": verdict},
        }
        Path(args.json).write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(f"Report written to {args.json}")

    if aborted:
        return 130
    return 0 if verdict == "STABLE" else 1


if __name__ == "__main__":
    sys.exit(main())
