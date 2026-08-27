"""Generated-image storage: data/generated/ with a JSON index.

Only *generated* images are ever stored here — never camera frames.
File names are timestamp-based and unique; the JSON index keeps rich
metadata (timestamp, provider, prompt, negative prompt, model, seed,
steps, cfg, dimensions, duration, mock flag) for the gallery. Index
entries are version-tolerant: older records without the newer fields
load with defaults.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.utils.logging_setup import get_logger

log = get_logger("image.storage")

#: Maximum entries kept in the index (old files remain on disk).
_MAX_INDEX_ENTRIES = 200

_KNOWN_FIELDS = {
    "file", "timestamp", "provider", "prompt", "negative_prompt",
    "width", "height", "is_mock", "model", "seed", "steps", "cfg",
    "duration_ms", "status",
}


@dataclass
class ImageRecord:
    """Metadata of one generated/uploaded image."""

    file: str          # file name inside the store directory
    timestamp: float
    provider: str
    prompt: str
    width: int
    height: int
    is_mock: bool = False
    negative_prompt: str = ""
    model: str = ""
    seed: Optional[int] = None
    steps: Optional[int] = None
    cfg: Optional[float] = None
    duration_ms: Optional[float] = None
    status: str = "completed"  # completed | failed
    # Phase 6: uploads, iterations, analysis, feedback.
    source: str = "generated"  # "generated" | "uploaded"
    version: int = 1
    parent_id: str = ""        # file name of the previous version
    analysis: Optional[dict[str, Any]] = None
    feedback: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Optional["ImageRecord"]:
        try:
            seed = raw.get("seed")
            analysis = raw.get("analysis")
            feedback = raw.get("feedback") or []
            return cls(
                file=str(raw["file"]),
                timestamp=float(raw["timestamp"]),
                provider=str(raw["provider"]),
                prompt=str(raw["prompt"]),
                width=int(raw["width"]),
                height=int(raw["height"]),
                is_mock=bool(raw.get("is_mock", False)),
                negative_prompt=str(raw.get("negative_prompt", "")),
                model=str(raw.get("model", "")),
                seed=int(seed) if seed is not None else None,
                steps=int(raw["steps"]) if raw.get("steps") is not None else None,
                cfg=float(raw["cfg"]) if raw.get("cfg") is not None else None,
                duration_ms=(
                    float(raw["duration_ms"])
                    if raw.get("duration_ms") is not None
                    else None
                ),
                status=str(raw.get("status", "completed")),
                source=str(raw.get("source", "generated")),
                version=int(raw.get("version", 1)),
                parent_id=str(raw.get("parent_id", "")),
                analysis=analysis if isinstance(analysis, dict) else None,
                feedback=(
                    [entry for entry in feedback if isinstance(entry, dict)]
                    if isinstance(feedback, list)
                    else []
                ),
            )
        except (KeyError, TypeError, ValueError):
            return None


class ImageStore:
    """Saves generated images and their metadata."""

    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._index_path = self._directory / "index.json"
        self._lock = threading.Lock()
        self._index: list[ImageRecord] = self._load_index()

    # ------------------------------------------------------------------
    @property
    def directory(self) -> Path:
        return self._directory

    # ------------------------------------------------------------------
    def save(self, record: ImageRecord, image_bytes: Optional[bytes]) -> ImageRecord:
        """Persist a record; PNG data optional (only for completed images).

        Never overwrites: file names are timestamp + sequence based.
        """
        with self._lock:
            if record.file:
                filename = record.file
            else:
                stamp = time.strftime("%Y%m%d_%H%M%S")
                sequence = len(self._index)
                filename = f"gen_{stamp}_{sequence:04d}.png"
                target = self._directory / filename
                while target.exists():
                    sequence += 1
                    filename = f"gen_{stamp}_{sequence:04d}.png"
                    target = self._directory / filename

            target = self._directory / filename
            if image_bytes is not None:
                target.write_bytes(image_bytes)
            elif not target.exists():
                raise FileNotFoundError(
                    f"Image file missing and no data provided: {filename}"
                )
            record.file = filename
            # Re-saving the same file must update the index entry, not
            # append a duplicate (gallery would show the image twice).
            for index, existing in enumerate(self._index):
                if existing.file == filename:
                    self._index[index] = record
                    break
            else:
                self._index.append(record)
            if len(self._index) > _MAX_INDEX_ENTRIES:
                self._index = self._index[-_MAX_INDEX_ENTRIES:]
            self._save_index()
            log.info(
                "Generated image saved: %s (%dx%d, %s)",
                filename, record.width, record.height, record.provider,
            )
            return record

    def update(self, record: ImageRecord) -> bool:
        """Update an existing record's metadata in place (e.g. after
        attaching an analysis result). Returns success."""
        with self._lock:
            for index, existing in enumerate(self._index):
                if existing.file == record.file:
                    self._index[index] = record
                    self._save_index()
                    return True
            return False

    def get(self, file_name: str) -> Optional[ImageRecord]:
        with self._lock:
            for record in self._index:
                if record.file == file_name:
                    return record
        return None

    def delete(self, record: ImageRecord) -> bool:
        """Remove an image file and its index entry. Returns success."""
        with self._lock:
            target = self._directory / record.file
            try:
                target.unlink(missing_ok=True)
            except OSError as exc:
                log.warning("Could not delete %s: %s", target, exc)
                return False
            self._index = [r for r in self._index if r.file != record.file]
            self._save_index()
            log.info("Generated image deleted: %s", record.file)
            return True

    def list(
        self,
        limit: int = 100,
        provider_filter: Optional[str] = None,
        newest_first: bool = True,
    ) -> list[ImageRecord]:
        """Records, optionally filtered by provider and sorted."""
        with self._lock:
            records = list(self._index)
        if provider_filter:
            records = [
                r for r in records
                if r.provider == provider_filter
                or (
                    provider_filter == "mock" and r.is_mock
                )
            ]
        records.sort(
            key=lambda r: r.timestamp, reverse=newest_first
        )
        return records[:limit]

    def providers_used(self) -> list[str]:
        with self._lock:
            return sorted({r.provider for r in self._index})

    def path_of(self, record: ImageRecord) -> Path:
        return self._directory / record.file

    # ------------------------------------------------------------------
    def _load_index(self) -> list[ImageRecord]:
        if not self._index_path.exists():
            return []
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("Image index unreadable — starting empty")
            return []
        if not isinstance(raw, list):
            return []
        records: list[ImageRecord] = []
        for entry in raw:
            record = (
                ImageRecord.from_dict(entry)
                if isinstance(entry, dict)
                else None
            )
            if record is not None and (self._directory / record.file).exists():
                records.append(record)
        return records[-_MAX_INDEX_ENTRIES:]

    def _save_index(self) -> None:
        payload = json.dumps(
            [record.to_dict() for record in self._index], indent=2
        )
        tmp = self._index_path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self._index_path)
