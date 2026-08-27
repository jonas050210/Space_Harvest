"""AI Vision Lab — production release gate (Phase 21).

Checks everything a release must satisfy and prints an honest verdict:

    python scripts/release_gate.py                 # static + dynamic checks
    python scripts/release_gate.py --with-tests    # also runs the test suite
                                                   # (chunked; slow in the sandbox)

Checks (each PASS / FAIL / UNTESTABLE with evidence — nothing invented):

1.  VERSION CONSISTENCY  — app/__init__.py == setup.py == README ==
    CHANGELOG == ROADMAP mentions
2.  ROOT HYGIENE        — exactly the allowed root files
3.  SECRET SCAN         — no key/secret patterns in code
4.  PYFLAKES            — zero findings (subprocess)
5.  COMPILEALL          — full syntax compile (subprocess)
6.  PACKAGING           — spec/bat/ps1/build requirements present + sane
7.  TESTS               — full suite in documented chunks (only with
    --with-tests; exit 137 OOM in small sandboxes is reported, never
    hidden)
8.  HARDWARE ACCEPTANCE — real reports (smoke/acceptance/stability) with
    a READY verdict are REQUIRED for a production release; without them
    the gate reports NOT READY / PENDING HARDWARE ACCEPTANCE. Missing
    reports are never treated as PASS.

Exit codes: 0 = READY, 1 = NOT READY (fix items listed), 2 = gate
could not complete honestly (environment limits).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

#: Exactly the allowed root files (project invariant).
ALLOWED_ROOT_FILES = {
    "README.md", "CHANGELOG.md", "ROADMAP.md", "requirements.txt",
    "setup.py", "start.py", "test_overall.py", "main.py", "pytest.ini",
    "LICENSE",
    ".gitignore",
}

#: Secret patterns that must never appear in source.
SECRET_PATTERNS = (
    "sk-[A-Za-z0-9]{16,}",      # OpenAI-style keys
    "api[_-]?key\\s*=\\s*[\"'][^\"']{8,}[\"']",
    "password\\s*=\\s*[\"'][^\"']+[\"']",
    "secret\\s*=\\s*[\"'][^\"']+[\"']",
)

#: Documented test chunks (2-GB sandbox; a single run may OOM).
TEST_CHUNKS: tuple[tuple[str, ...], ...] = (
    ("tests/test_phase28_smoke.py",),
    ("tests/test_phase27_smoke.py", "tests/test_phase26_smoke.py"),
    ("tests/test_phase25_smoke.py", "tests/test_webcam_2k_support.py"),
    ("tests/test_phase22_smoke.py", "tests/test_phase20_smoke.py"),
    ("tests/test_phase17_smoke.py", "tests/test_phase15_smoke.py"),
    ("tests/test_phase14_smoke.py", "tests/test_phase13b_smoke.py"),
    ("tests/test_phase13a_smoke.py",),
    ("tests/test_phase12_smoke.py", "tests/test_phase11_smoke.py"),
    ("tests/test_phase10_smoke.py", "tests/test_phase9_smoke.py"),
    ("tests/test_gui_integration.py",),
    ("tests/test_phase7_smoke.py", "tests/test_phase6_smoke.py"),
    ("tests/test_phase4_smoke.py", "tests/test_phase5_smoke.py"),
    ("tests/test_phase2_smoke.py", "tests/test_phase3_smoke.py"),
    ("tests/test_camera.py", "tests/test_config.py",
     "tests/test_face_modules.py", "tests/test_face_tracker.py",
     "tests/test_fps.py", "tests/test_model_manager.py",
     "tests/test_pipeline.py", "tests/test_settings.py",
     "tests/test_start_launcher.py", "tests/test_utils.py",
     "test_overall.py"),
)

RESULTS: list[tuple[str, str, str]] = []  # (name, verdict, detail)


def record(name: str, verdict: str, detail: str) -> None:
    RESULTS.append((name, verdict, detail))
    print(f"[{verdict:>10}] {name}: {detail}")


def _python() -> str:
    return sys.executable


def check_version_consistency() -> None:
    from app import __version__

    setup_text = (PROJECT_ROOT / "setup.py").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    roadmap = (PROJECT_ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    problems = []
    if f'version="{__version__}"' not in setup_text:
        problems.append("setup.py version mismatch")
    if f"v{__version__}" not in readme:
        problems.append("README does not mention the version")
    if f"[{__version__}]" not in changelog:
        problems.append("CHANGELOG has no entry for the version")
    if __version__ not in roadmap:
        problems.append("ROADMAP does not mention the version")
    if problems:
        record("VERSION CONSISTENCY", "FAIL", "; ".join(problems))
    else:
        record("VERSION CONSISTENCY", "PASS", f"v{__version__} everywhere")


def check_root_hygiene() -> None:
    entries = {
        path.name for path in PROJECT_ROOT.iterdir()
        if path.name != ".venv" and not path.name.startswith(".pytest")
    }
    files = {name for name in entries
             if (PROJECT_ROOT / name).is_file()}
    unexpected = sorted(files - ALLOWED_ROOT_FILES)
    missing = sorted(ALLOWED_ROOT_FILES - files)
    if unexpected or missing:
        record("ROOT HYGIENE", "FAIL",
               f"unexpected: {unexpected or '-'} · missing: {missing or '-'}")
    else:
        record("ROOT HYGIENE", "PASS",
               f"exactly the {len(ALLOWED_ROOT_FILES)} allowed files")


def check_secret_scan() -> None:
    """Scan SHIPPED code only — the test suite intentionally contains
    dummy key literals (for the scan tests themselves) and is never
    shipped."""
    import re

    scan_roots = (
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
    )
    scan_files = (
        PROJECT_ROOT / "main.py",
        PROJECT_ROOT / "start.py",
        PROJECT_ROOT / "setup.py",
        PROJECT_ROOT / "test_overall.py",
    )
    findings: list[str] = []
    paths = list(scan_files)
    for root in scan_roots:
        if root.is_dir():
            paths.extend(root.rglob("*.py"))
    for path in paths:
        if ".venv" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            match = re.search(pattern, text)
            if match:
                findings.append(f"{path.name}:{pattern[:20]}")
    if findings:
        record("SECRET SCAN", "FAIL", "; ".join(findings[:5]))
    else:
        record("SECRET SCAN", "PASS",
               "no key/secret patterns in shipped code")


def _run(command: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )
        return result.returncode, (result.stdout + result.stderr)[-400:]
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def check_pyflakes() -> None:
    code, output = _run(
        [_python(), "-m", "pyflakes", "app", "main.py", "start.py",
         "scripts", "test_overall.py", "tests"]
    )
    if code == 0:
        record("PYFLAKES", "PASS", "zero findings")
    else:
        record("PYFLAKES", "FAIL", output.replace("\n", " | ")[:200])


def check_compileall() -> None:
    code, output = _run(
        [_python(), "-m", "compileall", "-q", "app", "main.py", "start.py",
         "scripts", "test_overall.py", "tests"]
    )
    if code == 0:
        record("COMPILEALL", "PASS", "full syntax compile ok")
    else:
        record("COMPILEALL", "FAIL", output[:200])


def check_packaging() -> None:
    required = (
        "packaging/windows.spec",
        "packaging/windows.bat",
        "packaging/requirements-build.txt",
        "scripts/create_shortcut.ps1",
        "assets/app_icon.png",
    )
    missing = [p for p in required if not (PROJECT_ROOT / p).exists()]
    if missing:
        record("PACKAGING", "FAIL", f"missing: {missing}")
        return
    spec = (PROJECT_ROOT / "packaging/windows.spec").read_text(
        encoding="utf-8"
    )
    if "COLLECT" not in spec or "assets" not in spec:
        record("PACKAGING", "FAIL", "spec missing COLLECT/assets")
        return
    record("PACKAGING", "PASS",
           "spec/bat/ps1/build-requirements/icon present "
           "(Windows runtime: UNTESTABLE here)")


def check_tests() -> None:
    failures: list[str] = []
    for index, chunk in enumerate(TEST_CHUNKS, start=1):
        code, output = _run(
            [_python(), "-m", "pytest", *chunk, "-q"], timeout=900,
        )
        if code == 0:
            continue
        failures.append(
            f"chunk {index} exit {code}"
            + (" (OOM 137 — sandbox memory limit)" if code == 137 else "")
        )
    if failures:
        record("TESTS", "FAIL", "; ".join(failures))
        return
    record("TESTS", "PASS", f"{len(TEST_CHUNKS)} chunks green")


def check_hardware_acceptance() -> None:
    """Production release requires real, fresh, same-machine reports
    with a READY verdict. Missing reports are never a PASS."""
    from scripts.report_importer import load_reports

    entries = load_reports(PROJECT_ROOT, expected_version=None)
    usable = [e for e in entries if e["ok"] and not e["stale"]
              and e["version_match"] and e["environment_match"]
              and not e["secret_findings"]]
    ready_report = None
    for entry in usable:
        data = entry["data"] or {}
        verdict = (data.get("final_verdict") or {}).get("verdict")
        if verdict == "READY":
            ready_report = entry
            break
    if ready_report is not None:
        record("HARDWARE ACCEPTANCE", "PASS",
               f"READY report: {Path(ready_report['path']).name}")
    else:
        detail = (
            "no fresh READY acceptance report — run the acceptance on "
            "the target hardware (README 'Real Hardware Acceptance'). "
            "Missing reports are never treated as PASS."
        )
        if entries:
            detail = f"reports found: {len(entries)} (none READY) · " + detail
        record("HARDWARE ACCEPTANCE", "UNTESTABLE", detail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Vision Lab release gate")
    parser.add_argument("--with-tests", action="store_true",
                        help="also run the full test suite (chunked)")
    args = parser.parse_args(argv)

    print("=== AI VISION LAB — RELEASE GATE ===")
    check_version_consistency()
    check_root_hygiene()
    check_secret_scan()
    check_pyflakes()
    check_compileall()
    check_packaging()
    if args.with_tests:
        check_tests()
    else:
        record("TESTS", "UNTESTABLE",
               "not run — use --with-tests (chunked, slow in sandbox)")
    check_hardware_acceptance()

    print("\n=== RELEASE GATE SUMMARY ===")
    passed = sum(1 for _n, v, _d in RESULTS if v == "PASS")
    failed = sum(1 for _n, v, _d in RESULTS if v == "FAIL")
    untestable = sum(1 for _n, v, _d in RESULTS if v == "UNTESTABLE")
    print(f"PASS {passed} · FAIL {failed} · UNTESTABLE {untestable}")

    if failed:
        verdict = "NOT READY"
        note = "Fix the FAIL items and run the gate again."
        exit_code = 1
    elif untestable and passed == 0:
        verdict = "NOT READY"
        note = "Nothing could be verified — run the full gate."
        exit_code = 2
    elif untestable:
        verdict = "NOT READY"
        note = ("Software gate passed, but the HARDWARE ACCEPTANCE is "
                "pending (UNTESTABLE here) — no production release "
                "without a real READY report.")
        exit_code = 2
    else:
        verdict = "READY"
        note = "All release conditions satisfied."
        exit_code = 0
    print(f"RELEASE GATE: {verdict} — {note}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
