"""Safe hardware-report importer (Phase 15).

Loads, validates and merges the JSON reports produced by the acceptance
toolchain (smoke.json, acceptance.json, stability.json) WITHOUT ever
inventing data:

* corrupted JSON      -> error entry, never a crash
* old reports         -> marked STALE (configurable max age, default 30 days)
* version mismatch    -> WARNING (report does not count for READY)
* environment mismatch-> NOT merged automatically (different machine)
* conflicting results -> WARNING (both entries listed, none preferred)
* secret leakage      -> detected + redacted (AI_VISION_LAB_API_KEY values
                         must never appear in reports)

Only fresh, same-environment reports can contribute evidence to the
verification matrix — old data is never used as current hardware data.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import time
from pathlib import Path
from typing import Optional

#: Reports older than this are STALE (days).
DEFAULT_MAX_AGE_DAYS = 30.0

#: Known report file name patterns.
_REPORT_PATTERNS = ("smoke", "acceptance", "stability", "hardware")

#: Secret markers that must never appear in a report.
_SECRET_MARKERS = (
    "AI_VISION_LAB_API_KEY",
    "api_key",
    "apikey",
    "secret",
    "password",
    "authorization",
    "bearer ",
)

#: Report shape errors that make a file unusable.
REPORT_ERROR_READ = "unreadable"
REPORT_ERROR_JSON = "corrupt-json"
REPORT_ERROR_SHAPE = "unexpected-shape"


def environment_fingerprint() -> str:
    """Stable identifier of this machine (platform + host + CPU count).

    Two reports can only be merged when their fingerprints match —
    results from a different machine are never combined.
    """
    try:
        hostname = socket.gethostname()
    except OSError:
        hostname = "unknown"
    try:
        cpu_count = os.cpu_count() or 0
    except OSError:
        cpu_count = 0
    key = f"{platform.system()}|{platform.machine()}|{hostname}|{cpu_count}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def report_age_days(report: dict, now: Optional[float] = None) -> Optional[float]:
    """Age of a report in days (from its generated_at, if present)."""
    now = time.time() if now is None else now
    generated = None
    metadata = report.get("metadata") if isinstance(report, dict) else None
    if isinstance(metadata, dict):
        generated = metadata.get("generated_at")
    if generated is None and isinstance(report, dict):
        generated = report.get("generated_at")
    if not isinstance(generated, (int, float)):
        return None
    return max(0.0, (now - float(generated)) / 86400.0)


def app_version_of(report: dict) -> str:
    """The application version a report was produced with ("" unknown)."""
    if not isinstance(report, dict):
        return ""
    software = report.get("software")
    if isinstance(software, dict):
        version = software.get("version")
        if isinstance(version, str):
            return version
    metadata = report.get("metadata")
    if isinstance(metadata, dict):
        version = metadata.get("app_version")
        if isinstance(version, str):
            return version
    return ""


def fingerprint_of(report: dict) -> str:
    """The environment fingerprint stored in a report ("" unknown)."""
    if not isinstance(report, dict):
        return ""
    environment = report.get("environment")
    if isinstance(environment, dict):
        fingerprint = environment.get("fingerprint")
        if isinstance(fingerprint, str):
            return fingerprint
    return ""


def _scan_secrets(value, path: str, found: list[str]) -> None:
    """Recursively look for secret markers in a report structure."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            _scan_secrets(key, child_path, found)
            _scan_secrets(child, child_path, found)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_secrets(child, f"{path}[{index}]", found)
    elif isinstance(value, str):
        lowered = value.lower()
        for marker in _SECRET_MARKERS:
            if marker in lowered:
                found.append(f"{path} contains '{marker}'")
                break


def redact_secrets(report: dict) -> tuple[dict, list[str]]:
    """Return (report, findings) where sensitive values are removed.

    Key NAMES like 'api_key' are normal in reports (a boolean 'set/not
    set' flag is fine); VALUES that look like credentials are removed.
    """
    findings: list[str] = []
    # Only flag actual value-like content, never the documented env name
    # in explanation texts.
    def _walk(value):
        if isinstance(value, dict):
            return {
                key: _walk(child)
                for key, child in value.items()
            }
        if isinstance(value, list):
            return [_walk(child) for child in value]
        if isinstance(value, str):
            for marker in _SECRET_MARKERS:
                if marker in value.lower():
                    # Explanation strings mentioning the env var name are
                    # allowed; strings that *assign* a value are not.
                    if "=" in value or ":" in value:
                        findings.append(value[:120])
                        return "<redacted>"
            return value
        return value

    return _walk(report), findings


def load_report(
    path: Path,
    now: Optional[float] = None,
    max_age_days: float = DEFAULT_MAX_AGE_DAYS,
    expected_version: Optional[str] = None,
) -> dict:
    """Load and classify one report.

    Returns a dict with the loaded data plus classification fields:

        path, ok, error, data, age_days, stale, version, version_match,
        environment_match, conflicts, secret_findings
    """
    entry: dict = {
        "path": str(path),
        "ok": False,
        "error": None,
        "data": None,
        "age_days": None,
        "stale": False,
        "version": "",
        "version_match": True,
        "environment_match": True,
        "conflicts": [],
        "secret_findings": [],
    }
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        entry["error"] = f"{REPORT_ERROR_READ}: {exc}"
        return entry
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        entry["error"] = f"{REPORT_ERROR_JSON}: {exc}"
        return entry
    except (RecursionError, MemoryError) as exc:
        # Adversarial inputs (pathologically deep nesting) must never
        # crash the loader.
        entry["error"] = f"{REPORT_ERROR_JSON}: {type(exc).__name__}"
        return entry
    if not isinstance(data, dict):
        entry["error"] = f"{REPORT_ERROR_SHAPE}: top-level is "
        entry["error"] += type(data).__name__
        return entry
    entry["ok"] = True
    entry["data"] = data

    age = report_age_days(data, now=now)
    entry["age_days"] = age
    if age is not None and age > max_age_days:
        entry["stale"] = True

    entry["version"] = app_version_of(data)
    if expected_version and entry["version"] and (
        entry["version"] != expected_version
    ):
        entry["version_match"] = False

    fingerprint = fingerprint_of(data)
    if fingerprint and fingerprint != environment_fingerprint():
        entry["environment_match"] = False
        # A report from another machine is never merged automatically.
        entry["stale"] = True
        entry["error"] = entry["error"] or "environment-mismatch"

    _redacted, secret_findings = redact_secrets(data)
    entry["secret_findings"] = secret_findings
    return entry


def find_report_files(directory: Path) -> list[Path]:
    """All known report files in a directory (never invented)."""
    if not directory.is_dir():
        return []
    files: list[Path] = []
    for pattern in _REPORT_PATTERNS:
        files.extend(sorted(directory.glob(f"{pattern}*.json")))
    return sorted(set(files))


def load_reports(
    directory: Optional[Path] = None,
    now: Optional[float] = None,
    max_age_days: float = DEFAULT_MAX_AGE_DAYS,
    expected_version: Optional[str] = None,
) -> list[dict]:
    """Load + classify every report in the directory."""
    root = directory or Path.cwd()
    return [
        load_report(
            path, now=now, max_age_days=max_age_days,
            expected_version=expected_version,
        )
        for path in find_report_files(root)
    ]


def usable_evidence(entries: list[dict]) -> list[dict]:
    """Only fresh, same-environment, version-matching, secret-free
    reports may contribute evidence to the verification matrix."""
    usable: list[dict] = []
    for entry in entries:
        if not entry["ok"]:
            continue
        if entry["stale"] or not entry["version_match"]:
            continue
        if not entry["environment_match"]:
            continue
        if entry["secret_findings"]:
            continue
        usable.append(entry)
    return usable


def find_conflicts(entries: list[dict]) -> list[str]:
    """Same check name with different verdicts across reports -> WARNING.

    Never prefers one result — the conflict is reported, the decision
    stays with the acceptance run itself.
    """
    verdicts: dict[str, set] = {}
    for entry in entries:
        if not entry["ok"] or not entry["data"]:
            continue
        data = entry["data"]
        checks = data.get("checks")
        if isinstance(checks, list):
            for check in checks:
                if not isinstance(check, dict):
                    continue
                name = check.get("check") or check.get("name")
                verdict = check.get("verdict") or check.get("status")
                if name and verdict:
                    verdicts.setdefault(str(name).upper(), set()).add(
                        str(verdict)
                    )
    conflicts = [
        f"{name}: {sorted(set(v for v in vs if v))}"
        for name, vs in sorted(verdicts.items())
        if len({v for v in vs if v}) > 1
    ]
    return conflicts


def summarize_entry(entry: dict) -> str:
    """One readable line describing a loaded report."""
    if not entry["ok"]:
        return f"{Path(entry['path']).name}: {entry['error']}"
    flags = []
    if entry["stale"]:
        flags.append("STALE")
    if not entry["version_match"]:
        flags.append("VERSION-MISMATCH")
    if not entry["environment_match"]:
        flags.append("ENV-MISMATCH")
    if entry["secret_findings"]:
        flags.append("SECRETS-FOUND")
    if entry["conflicts"]:
        flags.append(f"CONFLICTS:{len(entry['conflicts'])}")
    age = (
        f"{entry['age_days']:.1f}d" if entry["age_days"] is not None
        else "no-timestamp"
    )
    suffix = f" [{', '.join(flags)}]" if flags else ""
    return (
        f"{Path(entry['path']).name}: ok · age {age} · "
        f"app v{entry['version'] or '?'}{suffix}"
    )
