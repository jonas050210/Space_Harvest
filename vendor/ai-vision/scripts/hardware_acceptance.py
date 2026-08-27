"""Hardware acceptance protocol for AI Vision Lab (Phase 13B/14/15).

Run this ON the target machine (Windows 11, i7-12700F, RTX 4060 Ti 8 GB,
32 GB RAM, webcam, Ollama, SD WebUI). One-click pack:

    scripts\\accept_windows.bat --minutes 10

Or by hand:

    python scripts/hardware_acceptance.py             # guided (interactive)
    python scripts/hardware_acceptance.py --auto      # non-interactive
    python scripts/hardware_acceptance.py --json acceptance.json
    python scripts/hardware_acceptance.py --reports . # merge existing reports

The script:

1. analyses EXISTING hardware reports (smoke/acceptance/stability JSON)
   via the report importer: corrupted files, STALE reports (>30 days),
   version mismatches and other-machine reports are flagged and NEVER
   counted as current hardware data (never invented),
2. runs the full hardware smoke (diagnostics, GPU/VRAM/delegate, camera
   resolution/FPS/reconnect, Ollama, SD WebUI, provider capabilities,
   timing),
3. runs the EXTENDED probes (Ollama model/streaming/latency, SD
   txt2img/img2img/seed/progress, startup/shutdown timing, EXE +
   shortcut presence),
4. walks the 20-step END-TO-END WORKFLOW checklist (guided, or
   UNTESTABLE with --auto),
5. builds the 29-item VERIFICATION MATRIX — every item carries name,
   status (REAL VERIFIED / MOCK VERIFIED / STUB VERIFIED / UNTESTABLE),
   result, evidence, source, timestamp, error and measurements — and
   prints the final verdict:

       READY       all REQUIRED hardware steps REAL VERIFIED (passed)
       NOT READY   at least one relevant test really failed
       INCOMPLETE  not enough real hardware data (UNTESTABLE gaps)

   A missing report NEVER counts as PASS. Ollama/SD WebUI items are
   optional by default (the product runs without them); use
   --require-ollama / --require-sdwebui to make them blocking.

Exit codes: 0 READY, 1 NOT READY, 2 INCOMPLETE, 130 aborted (Ctrl+C).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import __version__  # noqa: E402
from scripts.hardware_smoke import (  # noqa: E402
    RESULTS,
    run_diagnostics_section,
    run_gpu_section,
    run_camera_section,
    run_ollama_section,
    run_provider_capabilities_section,
    run_sdwebui_section,
)
from scripts.acceptance_probes import (  # noqa: E402
    probe_exe_presence,
    probe_ollama_model_present,
    probe_ollama_stream,
    probe_sd_img2img,
    probe_sd_txt2img,
    probe_shortcut_presence,
    probe_startup_shutdown,
)
from scripts.report_importer import (  # noqa: E402
    find_conflicts,
    load_reports,
    summarize_entry,
    usable_evidence,
)

#: Matrix statuses (the ONLY statuses for actual verification).
STATUS_REAL = "REAL VERIFIED"
STATUS_MOCK = "MOCK VERIFIED"
STATUS_STUB = "STUB VERIFIED"
STATUS_UNTESTABLE = "UNTESTABLE"
_MATRIX_STATUSES = (STATUS_REAL, STATUS_MOCK, STATUS_STUB, STATUS_UNTESTABLE)

#: (step, human confirmation prompt)
E2E_STEPS: list[tuple[str, str]] = (
    ("START APP", "python main.py — window opens with the Home page"),
    ("SYSTEM CHECK", "SYSTEM page shows the 9 check badges (no FAIL)"),
    ("START LIVE", "START CAMERA — feed visible, HUD shows LIVE"),
    ("PERSON DETECTED", "step into view — PERSONS = 01 in the HUD"),
    ("BODY", "LIVE INSPECTOR shows body detected"),
    ("ARMS", "raise each arm — arm states change (RAISED/OUT/NEUTRAL)"),
    ("HANDS", "show an open palm — hand skeleton + gesture appear"),
    ("OBJECTS", "place an object (cup/mouse) — OBJECTS count rises"),
    ("SCENE", "capture the scene — SCENE panel enabled"),
    ("CAPTURE SCENE", "CAPTURE SCENE — GENERATE FROM SCENE unlocks"),
    ("AI CONTEXT", "COPY SCENE — clipboard contains the description"),
    ("GENERATE IMAGE", "GENERATE — result appears (provider of choice)"),
    ("ANALYZE", "ANALYZE — MATCH/CONFIDENCE/QUALITY cards fill"),
    ("FEEDBACK", "apply feedback — stored on the record"),
    ("REGENERATE", "REGENERATE — v2 arrives and is analyzed"),
    ("COMPARE", "COMPARE — side-by-side + blend + DIFF work"),
    ("SAVE", "SAVE COPY — file dialog writes a PNG"),
    ("GALLERY", "GALLERY — both versions with status badges"),
    ("DETAIL", "detail panel shows INFO/VERSIONS/ANALYSIS/FEEDBACK"),
    ("VERSION HISTORY", "VERSIONS lists v1 → v2 lineage"),
)

#: Production-relevant items — every one must be REAL VERIFIED (passed)
#: for READY.
_REQUIRED_ITEMS = {
    "PYTHON", "DEPENDENCIES", "MODELS",
    "CAMERA", "CAMERA RESOLUTION", "CAMERA FPS", "CAMERA RECONNECT",
    "GPU", "NVIDIA DRIVER", "VRAM", "MEDIAPIPE GPU DELEGATE",
    "CPU FALLBACK",
    "STARTUP", "SHUTDOWN", "EXE", "SHORTCUT",
    "E2E WORKFLOW", "STABILITY",
}
#: Ollama items — optional unless --require-ollama.
_OLLAMA_ITEMS = {
    "OLLAMA AVAILABILITY", "OLLAMA MODEL", "OLLAMA STREAMING",
    "OLLAMA LATENCY",
}
#: SD WebUI items — optional unless --require-sdwebui.
_SD_ITEMS = {
    "SD WEBUI AVAILABILITY", "SD CHECKPOINT", "TXT2IMG", "IMG2IMG",
    "REAL PROGRESS", "SEED",
}
#: Informational only — never blocking.
_INFO_ITEMS = {"PROVIDER CAPABILITIES"}


def _ask(step: str, prompt: str, auto: bool) -> str:
    if auto:
        return "UNTESTABLE"  # human-at-camera steps stay honest
    while True:
        answer = input(f"\n[{step}] {prompt}\n  works? [y]es / [n]o / [s]kip: ")
        choice = answer.strip().lower()
        if choice in ("y", "yes"):
            return "PASS"
        if choice in ("n", "no"):
            return "FAIL"
        if choice in ("s", "skip", ""):
            return "UNTESTABLE"


# ---------------------------------------------------------------------------
# Fresh data collection
# ---------------------------------------------------------------------------
def _synthetic_png() -> bytes:
    """A valid 256x256 PNG (noise) — init input for the img2img probe.

    The probe tests the REAL img2img API call; the init image source is
    irrelevant to that test and is clearly synthetic.
    """
    import cv2
    import numpy as np

    rng = np.random.default_rng(42)
    image = rng.integers(0, 255, (256, 256, 3), dtype=np.uint8)
    ok, png = cv2.imencode(".png", image)
    if not ok:
        return b""
    return png.tobytes()


def _run_extended(skip: bool) -> dict[str, tuple[str, str, dict]]:
    """Run the extended probes; returns {probe_key: (verdict, detail, metrics)}."""
    probes: dict[str, tuple[str, str, dict]] = {}
    if skip:
        return probes
    print("\n--- PART 3: EXTENDED PROBES (real operations) ---")
    for key, probe in (
        ("OLLAMA MODEL", probe_ollama_model_present),
        ("OLLAMA STREAMING", probe_ollama_stream),
        ("SD TXT2IMG", probe_sd_txt2img),
        ("EXE", probe_exe_presence),
        ("SHORTCUT", probe_shortcut_presence),
    ):
        verdict, detail, metrics = probe()
        probes[key] = (verdict, detail, metrics)
        print(f"[{verdict:>10}] {key}: {detail}")
    # img2img: real API call with a synthetic init PNG (honest label).
    verdict, detail, metrics = probe_sd_img2img(_synthetic_png())
    probes["SD IMG2IMG"] = (verdict, detail, metrics)
    print(f"[{verdict:>10}] SD IMG2IMG: {detail}")
    # startup/shutdown timing (always measurable where Qt runs).
    with tempfile.TemporaryDirectory(prefix="avlp-accept-") as tmp:
        verdict, detail, metrics = probe_startup_shutdown(Path(tmp))
    probes["STARTUP/SHUTDOWN"] = (verdict, detail, metrics)
    print(f"[{verdict:>10}] STARTUP/SHUTDOWN: {detail}")
    return probes


# ---------------------------------------------------------------------------
# Matrix building
# ---------------------------------------------------------------------------
def _status_of(verdict: str) -> tuple[str, str | None]:
    """Map a probe verdict to (matrix status, result).

    FAIL means the test really ran and really failed — it IS a real
    verification (of a failure), so the status stays REAL VERIFIED and
    the result carries the failure.
    """
    if verdict == "PASS":
        return STATUS_REAL, "passed"
    if verdict == "FAIL":
        return STATUS_REAL, "failed"
    return STATUS_UNTESTABLE, None


def _check_by_name(results: list[dict], name: str) -> dict | None:
    wanted = name.upper()
    for check in results:
        if str(check.get("check", "")).upper() == wanted:
            return check
    return None


def _check_by_prefix(results: list[dict], prefix: str) -> dict | None:
    for check in results:
        if str(check.get("check", "")).upper().startswith(prefix.upper()):
            return check
    return None


def _entry(status: str, result: str | None, evidence: str, source: str,
           error: str = "", measurements: dict | None = None,
           timestamp: float | None = None, required: bool = True,
           stale: bool = False) -> dict:
    return {
        "name": "",
        "status": status,
        "result": result,
        "evidence": evidence,
        "source": source,
        "timestamp": timestamp,
        "error": error,
        "measurements": measurements or {},
        "required": required,
        "stale": stale,
    }


def _from_smoke(results: list[dict], name: str, source: str = "smoke") -> dict:
    check = _check_by_name(results, name)
    if check is None:
        return _entry(STATUS_UNTESTABLE, None, "not probed", source)
    status, result = _status_of(str(check.get("verdict")))
    return _entry(
        status, result, str(check.get("detail", "")), source,
        error=str(check.get("detail", "")) if result == "failed" else "",
        timestamp=check.get("timestamp"),
    )


def _from_extended(probes: dict, key: str) -> dict:
    probe = probes.get(key)
    if probe is None:
        return _entry(STATUS_UNTESTABLE, None, "probe not run",
                      f"probe:{key}")
    verdict, detail, metrics = probe
    status, result = _status_of(verdict)
    return _entry(
        status, result, detail, f"probe:{key}",
        error=detail if result == "failed" else "",
        measurements=metrics, timestamp=time.time(),
    )


def _aggregate_workflow(workflow: list[dict]) -> dict:
    """Aggregate the E2E checklist against the FULL 20-step contract.

    A partial checklist is never a pass — every production step must be
    confirmed (a partial checklist is never a pass)."""
    passed = sum(1 for w in workflow if w["verdict"] == "PASS")
    failed = sum(1 for w in workflow if w["verdict"] == "FAIL")
    total = len(workflow)
    expected = len(E2E_STEPS)
    if total == 0:
        return _entry(
            STATUS_UNTESTABLE, None,
            "no workflow step verified on this machine", "workflow",
            timestamp=time.time(),
        )
    if failed:
        steps = [w["step"] for w in workflow if w["verdict"] == "FAIL"]
        return _entry(
            STATUS_REAL, "failed",
            f"{failed}/{total} steps failed: {', '.join(steps)}",
            "workflow", error=" · ".join(steps), timestamp=time.time(),
        )
    if total < expected or passed < expected:
        return _entry(
            STATUS_UNTESTABLE, None,
            f"workflow incomplete: {passed}/{expected} steps confirmed"
            + (f" · {failed} failed" if failed else ""),
            "workflow", timestamp=time.time(),
        )
    return _entry(
        STATUS_REAL, "passed", f"all {expected} workflow steps confirmed",
        "workflow", timestamp=time.time(),
    )


def _stability_entry(report: dict | None) -> dict:
    """STABILITY from a fresh same-environment stability report."""
    if report is None:
        return _entry(
            STATUS_UNTESTABLE, None,
            "run scripts/stability_probe.py --minutes 10 --camera 0 on "
            "the target machine (or pass its JSON via --reports)",
            "stability_probe",
        )
    verdict = str(
        (report.get("final_verdict") or {}).get("verdict", "")
    )
    measurements = report.get("measurements") or {}
    if verdict == "STABLE":
        return _entry(
            STATUS_REAL, "passed",
            f"stable — {measurements.get('duration_s')} s, "
            f"{measurements.get('frames')} frames, "
            f"{measurements.get('fps')} fps, "
            f"RSS growth {measurements.get('rss_growth_mb')} MB",
            "stability_probe", measurements=measurements,
            timestamp=report.get("metadata", {}).get("generated_at"),
        )
    if verdict == "WATCH MEMORY GROWTH":
        return _entry(
            STATUS_REAL, "passed",
            f"stable with watch item — RSS growth "
            f"{measurements.get('rss_growth_mb')} MB",
            "stability_probe", measurements=measurements,
            timestamp=report.get("metadata", {}).get("generated_at"),
        )
    if verdict in ("FAIL", "ABORTED"):
        return _entry(
            STATUS_REAL, "failed",
            f"stability run: {verdict} — "
            f"{', '.join(report.get('errors') or [])[:120] or 'no details'}",
            "stability_probe",
            error=verdict,
            measurements=measurements,
            timestamp=report.get("metadata", {}).get("generated_at"),
        )
    return _entry(
        STATUS_UNTESTABLE, None,
        "no usable stability report (stale/other machine/absent)",
        "stability_probe",
    )


def build_matrix(
    smoke_results: list[dict],
    extended: dict[str, tuple[str, str, dict]],
    workflow: list[dict],
    stability_report: dict | None = None,
    require_ollama: bool = False,
    require_sdwebui: bool = False,
) -> dict[str, dict]:
    """The full 29-item verification matrix (fresh data only)."""
    matrix: dict[str, dict] = {}

    def put(name: str, entry: dict, required: bool) -> None:
        entry["name"] = name
        entry["required"] = required
        matrix[name] = entry

    # ---------------- diagnostics-backed items ----------------
    for item, diag_name, required in (
        ("PYTHON", "PYTHON", True),
        ("DEPENDENCIES", "DEPENDENCIES", True),
        ("MODELS", "MODEL FILES", True),
        ("CAMERA", "CAMERA", True),
        ("GPU", "GPU", True),
        ("OLLAMA AVAILABILITY", "OLLAMA", False),
        ("SD WEBUI AVAILABILITY", "SD WEBUI", False),
    ):
        check = _check_by_name(smoke_results, diag_name)
        if check is None:
            entry = _entry(STATUS_UNTESTABLE, None,
                           "diagnostics not run", "diagnostics")
        else:
            status, result = _status_of(str(check.get("verdict")))
            entry = _entry(
                status, result, str(check.get("detail", "")), "diagnostics",
                error=str(check.get("detail", "")) if result == "failed" else "",
                timestamp=check.get("timestamp"),
            )
        put(item, entry, required)

    # ---------------- smoke-backed items ----------------
    resolution = _check_by_prefix(smoke_results, "Resolution ")
    if resolution is None:
        put("CAMERA RESOLUTION", _from_smoke(smoke_results, "CAMERA RESOLUTION"), True)
    else:
        status, result = _status_of(str(resolution.get("verdict")))
        put("CAMERA RESOLUTION", _entry(
            status, result, str(resolution.get("detail", "")), "smoke",
            error=str(resolution.get("detail", "")) if result == "failed" else "",
            timestamp=resolution.get("timestamp"),
        ), True)

    for item in ("CAMERA FPS", "CAMERA RECONNECT"):
        check = _check_by_name(smoke_results, item)
        if check is None:
            put(item, _entry(STATUS_UNTESTABLE, None, "not probed", "smoke"), True)
        else:
            status, result = _status_of(str(check.get("verdict")))
            put(item, _entry(
                status, result, str(check.get("detail", "")), "smoke",
                error=str(check.get("detail", "")) if result == "failed" else "",
                timestamp=check.get("timestamp"),
            ), True)

    # VRAM
    put("VRAM", _from_smoke(smoke_results, "VRAM"), True)

    # NVIDIA DRIVER — derived from the GPU check detail (real data).
    gpu_check = _check_by_name(smoke_results, "GPU")
    if gpu_check is None:
        put("NVIDIA DRIVER", _entry(STATUS_UNTESTABLE, None,
                                    "GPU check not run", "smoke"), True)
    elif "driver" in str(gpu_check.get("detail", "")).lower():
        put("NVIDIA DRIVER", _entry(
            STATUS_REAL, "passed", str(gpu_check.get("detail", "")),
            "smoke", timestamp=gpu_check.get("timestamp"),
        ), True)
    else:
        put("NVIDIA DRIVER", _entry(STATUS_UNTESTABLE, None,
                                    "no NVIDIA driver info", "smoke"), True)

    # MEDIAPIPE GPU DELEGATE + CPU FALLBACK (same probe, honest split).
    delegate = _check_by_name(smoke_results, "GPU delegate")
    if delegate is None:
        put("MEDIAPIPE GPU DELEGATE",
            _entry(STATUS_UNTESTABLE, None, "delegate probe not run", "smoke"),
            True)
        put("CPU FALLBACK",
            _entry(STATUS_UNTESTABLE, None, "delegate probe not run", "smoke"),
            True)
    else:
        detail = str(delegate.get("detail", ""))
        status, result = _status_of(str(delegate.get("verdict")))
        put("MEDIAPIPE GPU DELEGATE", _entry(
            status, result, detail, "smoke",
            error=detail if result == "failed" else "",
            timestamp=delegate.get("timestamp"),
        ), True)
        if "cpu fallback active" in detail.lower() or (
            "delegate: cpu" in detail.lower()
        ):
            put("CPU FALLBACK", _entry(
                STATUS_REAL, "passed", detail, "smoke",
                timestamp=delegate.get("timestamp"),
            ), True)
        elif result == "passed":
            put("CPU FALLBACK", _entry(
                STATUS_UNTESTABLE, None,
                "not exercised — GPU delegate active (CPU fallback only "
                "proves itself when the delegate is unavailable)",
                "smoke", timestamp=delegate.get("timestamp"),
            ), True)
        else:
            put("CPU FALLBACK", _entry(
                STATUS_UNTESTABLE, None, detail, "smoke",
                timestamp=delegate.get("timestamp"),
            ), True)

    # SD checkpoint
    put("SD CHECKPOINT", _from_smoke(smoke_results, "SD WebUI checkpoint"), False)

    # Provider capabilities (informational)
    capabilities = _check_by_prefix(smoke_results, "Capabilities ")
    if capabilities is None:
        put("PROVIDER CAPABILITIES",
            _entry(STATUS_UNTESTABLE, None, "not probed", "smoke"), False)
    else:
        put("PROVIDER CAPABILITIES", _entry(
            STATUS_REAL, "passed", str(capabilities.get("detail", "")),
            "smoke", timestamp=capabilities.get("timestamp"),
        ), False)

    # ---------------- extended-probe-backed items ----------------
    put("OLLAMA MODEL", _from_extended(extended, "OLLAMA MODEL"), False)
    put("OLLAMA STREAMING", _from_extended(extended, "OLLAMA STREAMING"), False)
    # OLLAMA LATENCY: only meaningful when streaming passed.
    streaming = matrix["OLLAMA STREAMING"]
    if streaming["status"] == STATUS_REAL and streaming["result"] == "passed":
        metrics = streaming["measurements"]
        put("OLLAMA LATENCY", _entry(
            STATUS_REAL, "passed",
            f"first token {metrics.get('first_token_ms')} ms · "
            f"total {metrics.get('total_ms')} ms",
            "probe:OLLAMA STREAMING", measurements=metrics,
            timestamp=time.time(),
        ), False)
    else:
        put("OLLAMA LATENCY", _entry(
            STATUS_UNTESTABLE, None, streaming["evidence"],
            "probe:OLLAMA STREAMING", timestamp=time.time(),
        ), False)

    txt2img = _from_extended(extended, "SD TXT2IMG")
    put("TXT2IMG", txt2img, False)
    put("IMG2IMG", _from_extended(extended, "SD IMG2IMG"), False)
    if txt2img["status"] == STATUS_REAL and txt2img["result"] == "passed":
        metrics = txt2img["measurements"]
        put("REAL PROGRESS", _entry(
            STATUS_REAL, "passed",
            f"{metrics.get('progress_samples', 0)} real progress samples "
            "in [0,1]", "probe:SD TXT2IMG", measurements=metrics,
            timestamp=time.time(),
        ), False)
        put("SEED", _entry(
            STATUS_REAL, "passed",
            f"seed readback: {metrics.get('seed')}",
            "probe:SD TXT2IMG", measurements=metrics, timestamp=time.time(),
        ), False)
    else:
        put("REAL PROGRESS", _entry(
            STATUS_UNTESTABLE, None, txt2img["evidence"],
            "probe:SD TXT2IMG", timestamp=time.time(),
        ), False)
        put("SEED", _entry(
            STATUS_UNTESTABLE, None, txt2img["evidence"],
            "probe:SD TXT2IMG", timestamp=time.time(),
        ), False)

    put("EXE", _from_extended(extended, "EXE"), True)
    put("SHORTCUT", _from_extended(extended, "SHORTCUT"), True)
    startup = _from_extended(extended, "STARTUP/SHUTDOWN")
    put("STARTUP", dict(startup, name="STARTUP"), True)
    shutdown = dict(startup, name="SHUTDOWN")
    put("SHUTDOWN", shutdown, True)

    put("E2E WORKFLOW", _aggregate_workflow(workflow), True)
    put("STABILITY", _stability_entry(stability_report), True)

    # ---------------- required/optional flags ----------------
    for name in _OLLAMA_ITEMS:
        matrix[name]["required"] = require_ollama
    for name in _SD_ITEMS:
        matrix[name]["required"] = require_sdwebui
    for name in _INFO_ITEMS:
        matrix[name]["required"] = False
    return matrix


def merge_imported_reports(matrix: dict[str, dict],
                           entries: list[dict]) -> list[str]:
    """Fill UNTESTABLE gaps from fresh, same-environment reports.

    Imported evidence is attributed to its source file + timestamp;
    nothing is invented and stale/mismatched reports never count.
    Returns warning lines.
    """
    warnings: list[str] = []
    for entry in entries:
        if not entry["ok"] or entry["stale"] or not entry["version_match"]:
            continue
        if not entry["environment_match"] or entry["secret_findings"]:
            continue
        data = entry["data"]
        source_name = Path(entry["path"]).name
        checks = data.get("checks") if isinstance(data, dict) else None
        if isinstance(checks, list):
            for check in checks:
                if not isinstance(check, dict):
                    continue
                name = str(check.get("check", "")).upper()
                for item, item_entry in matrix.items():
                    if item.upper() != name:
                        continue
                    if item_entry["status"] != STATUS_UNTESTABLE:
                        continue
                    status, result = _status_of(
                        str(check.get("verdict", ""))
                    )
                    item_entry.update({
                        "status": status,
                        "result": result,
                        "evidence": str(check.get("detail", "")),
                        "source": f"report:{source_name}",
                        "timestamp": check.get("timestamp"),
                        "error": (
                            str(check.get("detail", ""))
                            if result == "failed" else ""
                        ),
                        "imported": True,
                    })
        matrix_data = data.get("verification_matrix") if isinstance(data, dict) else None
        if isinstance(matrix_data, dict):
            for name, imported in matrix_data.items():
                item_entry = matrix.get(name)
                if item_entry is None:
                    continue
                if item_entry["status"] != STATUS_UNTESTABLE:
                    continue
                imported_status = imported.get("status")
                if imported_status not in _MATRIX_STATUSES:
                    continue
                item_entry.update({
                    "status": imported_status,
                    "result": imported.get("result"),
                    "evidence": str(imported.get("evidence", "")),
                    "source": f"report:{source_name}",
                    "timestamp": imported.get("timestamp"),
                    "error": imported.get("error", ""),
                    "measurements": imported.get("measurements", {})
                    if isinstance(imported.get("measurements"), dict) else {},
                    "imported": True,
                })
        verdict = (data.get("final_verdict") or {}).get("verdict")
        if matrix.get("STABILITY", {}).get("status") == STATUS_UNTESTABLE and (
            verdict in ("STABLE", "WATCH MEMORY GROWTH", "FAIL")
        ):
            matrix["STABILITY"] = dict(
                _stability_entry(data),
                source=f"report:{source_name}",
            )
    return warnings


# ---------------------------------------------------------------------------
def _verdict(matrix: dict[str, dict]) -> tuple[str, str, list[str]]:
    """READY / NOT READY / INCOMPLETE from the matrix (strict rules)."""
    failures: list[str] = []
    optional_failures: list[str] = []
    missing: list[str] = []
    warnings: list[str] = []
    for name, entry in matrix.items():
        if entry["status"] != STATUS_REAL:
            if entry.get("required"):
                missing.append(name)
            continue
        if entry["result"] == "failed":
            if entry.get("required"):
                failures.append(name)
            else:
                optional_failures.append(name)
        elif entry["result"] is None:
            if entry.get("required"):
                missing.append(name)
    for name, entry in matrix.items():
        if entry.get("stale"):
            warnings.append(f"{name}: STALE evidence — not counted")
    if optional_failures:
        warnings.append(
            "optional items failed (not blocking): "
            + ", ".join(sorted(optional_failures))
            + " — pass --require-ollama/--require-sdwebui to make them "
              "production-relevant"
        )
    if failures:
        return "NOT READY", (
            "at least one relevant hardware test really failed: "
            + ", ".join(sorted(failures))
        ), warnings
    if missing:
        return "INCOMPLETE", (
            "not enough real hardware data — missing REAL VERIFIED "
            "evidence for: " + ", ".join(sorted(missing))
        ), warnings
    return "READY", (
        "all production-relevant hardware steps REAL VERIFIED (passed)"
    ), warnings


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Vision Lab acceptance")
    parser.add_argument("--auto", action="store_true",
                        help="non-interactive: human steps = UNTESTABLE")
    parser.add_argument("--json", metavar="PATH",
                        help="write the full report as JSON")
    parser.add_argument("--skip-smoke", action="store_true",
                        help="skip the hardware smoke part")
    parser.add_argument("--skip-extended", action="store_true",
                        help="skip the extended probes")
    parser.add_argument("--reports", metavar="DIR",
                        help="folder with existing smoke/acceptance/"
                             "stability JSON reports")
    parser.add_argument("--require-ollama", action="store_true",
                        help="make Ollama items production-relevant")
    parser.add_argument("--require-sdwebui", action="store_true",
                        help="make SD WebUI items production-relevant")
    args = parser.parse_args(argv)

    print("=== AI Vision Lab — HARDWARE ACCEPTANCE (Phase 15) ===")
    print(f"machine: {sys.platform} · python {sys.version.split()[0]} · "
          f"app v{__version__} · "
          f"started {time.strftime('%Y-%m-%d %H:%M:%S')}")

    report_entries: list[dict] = []
    try:
        # 0) Existing reports (analysed, never invented).
        print("\n--- PART 0: EXISTING HARDWARE REPORTS ---")
        report_entries = load_reports(
            Path(args.reports) if args.reports else None,
            expected_version=__version__,
        )
        if report_entries:
            for entry in report_entries:
                print("  " + summarize_entry(entry))
            conflicts = find_conflicts(report_entries)
            if conflicts:
                print("  WARNINGS (conflicting reports):")
                for conflict in conflicts:
                    print(f"    - {conflict}")
        else:
            print("  none found — hardware state on this machine is "
                  "UNTESTABLE until real reports exist")

        # 1) Fresh run — never mix results from an earlier invocation.
        RESULTS.clear()
        if not args.skip_smoke:
            print("\n--- PART 1: HARDWARE SMOKE ---")
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

        # 2) Extended probes.
        extended = _run_extended(args.skip_extended)

        # 3) End-to-end workflow checklist.
        print("\n--- PART 2: END-TO-END WORKFLOW CHECKLIST ---")
        workflow: list[dict] = []
        for step, prompt in E2E_STEPS:
            verdict = _ask(step, prompt, args.auto)
            workflow.append({"step": step, "verdict": verdict,
                             "prompt": prompt})
            print(f"[{verdict:>10}] {step}")
    except KeyboardInterrupt:
        print("\naborted by user (Ctrl+C) — partial results follow")
        return _finish(None, None, [], report_entries, [], True, args)

    return _finish(
        RESULTS, extended, workflow, report_entries, [], False, args,
    )


def _finish(
    smoke_results: list[dict] | None,
    extended: dict | None,
    workflow: list[dict],
    report_entries: list[dict],
    extra_warnings: list[str],
    aborted: bool,
    args,
) -> int:
    from scripts.report_importer import environment_fingerprint

    smoke_results = smoke_results or []
    extended = extended or {}
    stability_report: dict | None = None
    for entry in usable_evidence(report_entries):
        data = entry["data"] or {}
        if entry["path"].lower().find("stability") >= 0:
            stability_report = data
            break

    matrix = build_matrix(
        smoke_results, extended, workflow,
        stability_report=stability_report,
        require_ollama=args.require_ollama,
        require_sdwebui=args.require_sdwebui,
    )
    merge_warnings = merge_imported_reports(matrix, report_entries)
    all_warnings = list(extra_warnings) + merge_warnings

    print("\n=== VERIFICATION MATRIX (29 items) ===")
    for name, entry in matrix.items():
        stale = " [STALE]" if entry.get("stale") else ""
        print(f"[{entry['status']:>13}] {name}{stale}: "
              f"{entry['evidence'][:80]}")

    verdict, note, verdict_warnings = (
        ("ABORTED", "run aborted by user", [])
        if aborted else _verdict(matrix)
    )
    all_warnings.extend(verdict_warnings)

    print("\n=== ACCEPTANCE SUMMARY ===")
    statuses = {
        STATUS_REAL: sum(
            1 for e in matrix.values() if e["status"] == STATUS_REAL
        ),
        STATUS_MOCK: 0,
        STATUS_STUB: 0,
        STATUS_UNTESTABLE: sum(
            1 for e in matrix.values() if e["status"] == STATUS_UNTESTABLE
        ),
    }
    passed = sum(
        1 for e in matrix.values()
        if e["status"] == STATUS_REAL and e["result"] == "passed"
    )
    failed = sum(
        1 for e in matrix.values()
        if e["status"] == STATUS_REAL and e["result"] == "failed"
    )
    print(f"VERIFICATION: REAL {passed + failed} ({passed} passed · "
          f"{failed} failed) · MOCK {statuses[STATUS_MOCK]} · "
          f"STUB {statuses[STATUS_STUB]} · "
          f"UNTESTABLE {statuses[STATUS_UNTESTABLE]}")
    if all_warnings:
        print("WARNINGS:")
        for warning in all_warnings:
            print(f"  - {warning}")
    print(f"\nACCEPTANCE: {verdict} — {note}")

    exit_code = {"READY": 0, "NOT READY": 1,
                 "INCOMPLETE": 2, "ABORTED": 130}[verdict]

    if args.json:
        from scripts.report_importer import redact_secrets

        raw_report = {
            "schema_version": 2,
            "metadata": {
                "tool": "hardware_acceptance",
                "app_version": __version__,
                "generated_at": time.time(),
                "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
            "environment": {
                "platform": sys.platform,
                "python": sys.version.split()[0],
                "fingerprint": environment_fingerprint(),
            },
            "software": {"version": __version__},
            "hardware": {"gpu": None, "camera": None},
            "checks": workflow,
            "verification_matrix": matrix,
            "extended_probes": {
                key: {"verdict": v, "detail": d, "metrics": m}
                for key, (v, d, m) in (extended or {}).items()
            },
            "measurements": {
                key: m for key, (_v, _d, m) in (extended or {}).items()
            },
            "errors": [
                e["error"] for e in matrix.values() if e.get("error")
            ],
            "warnings": all_warnings,
            "final_verdict": {"verdict": verdict, "note": note},
            # legacy keys (compat with earlier importers)
            "hardware_smoke": smoke_results,
            "workflow": workflow,
            "summary": {
                "verdict": verdict,
                "real": passed + failed,
                "failed": failed,
                "untestable": statuses[STATUS_UNTESTABLE],
            },
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
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
