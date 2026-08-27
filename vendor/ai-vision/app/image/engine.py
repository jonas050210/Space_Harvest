"""Image generation engine: provider selection, generation queue, storage.

* Providers: Mock (dev), SD WebUI (local), ComfyUI (local), Local/External OpenAI-compatible.
* One worker thread drains the generation queue sequentially — the
  camera/vision loop and the GUI event loop are never blocked.
* Jobs carry all parameters; statuses QUEUED/GENERATING/COMPLETED/
  FAILED/CANCELLED are reported via callbacks (Qt-bridged in the UI).
* Results are validated (PNG decode) and saved through the ImageStore.
* Nothing is ever sent anywhere without an explicit generate call.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional

from app.config.settings import SettingsService
from app.image.presets import apply_preset
from app.image.providers.base import GeneratedImage, ImageProvider
from app.image.providers.mock import MockImageProvider
from app.image.providers.openai_compatible import (
    APIImageProvider,
    LocalImageProvider,
)
from app.image.providers.comfyui import ComfyUIProvider
from app.image.providers.sdwebui import SDWebUIProvider
from app.image.queue import (
    COMPLETED,
    FAILED,
    GENERATING,
    GenerationJob,
    GenerationQueue,
)
from app.image.storage import ImageRecord, ImageStore
from app.utils.logging_setup import get_logger

log = get_logger("image.engine")

StatusCallback = Callable[[GenerationJob], None]
DoneCallback = Callable[[GeneratedImage, Optional[ImageRecord]], None]
ErrorCallback = Callable[[str], None]

#: Allowed image sizes (validated in settings as well).
ALLOWED_SIZES = (256, 512, 768, 1024)

#: Job status polling interval for waiting callbacks.
_WAIT_POLL = 0.05

#: Provider availability probes are network calls — cache the results so
#: the UI never blocks the GUI thread on repeated probes.
_STATUS_TTL = 10.0


class ImageGenerationEngine:
    """Owns providers, the generation queue and the image store."""

    def __init__(
        self,
        settings_service: SettingsService,
        store: Optional[ImageStore] = None,
    ) -> None:
        self._settings_service = settings_service
        self._store = store
        self._queue = GenerationQueue()
        self._worker: Optional[threading.Thread] = None
        self._worker_lock = threading.Lock()
        self._status_callbacks: list[StatusCallback] = []
        self._stop_event = threading.Event()
        #: Last completed generation stats (real measurements).
        self.last_duration_ms: Optional[float] = None
        self.last_error: Optional[str] = None
        #: provider key -> (monotonic timestamp, status dict)
        self._status_cache: dict[str, tuple[float, dict]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def store(self) -> Optional[ImageStore]:
        return self._store

    @property
    def queue(self) -> GenerationQueue:
        return self._queue

    def on_status(self, callback: StatusCallback) -> None:
        """Register a job status callback (called from the worker thread)."""
        self._status_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------
    def build_provider(self, provider_key: Optional[str] = None) -> ImageProvider:
        """Provider from the settings (or an explicit key)."""
        settings = self._settings_service.settings
        key = provider_key or settings.image_provider

        if settings.offline_mode:
            return MockImageProvider(
                width=settings.image_width, height=settings.image_height
            )
        if key == "mock":
            return MockImageProvider(
                width=settings.image_width, height=settings.image_height
            )
        if key == "sdwebui":
            return SDWebUIProvider(
                base_url=settings.sdwebui_base_url,
                width=settings.image_width,
                height=settings.image_height,
            )
        if key == "comfyui":
            return ComfyUIProvider(
                base_url=settings.comfyui_base_url,
                width=settings.image_width,
                height=settings.image_height,
            )
        api_key = os.environ.get("AI_VISION_LAB_API_KEY")
        if key == "local":
            return LocalImageProvider(
                base_url=settings.image_base_url,
                model=settings.image_model,
                width=settings.image_width,
                height=settings.image_height,
                api_key=api_key,
            )
        return APIImageProvider(
            base_url=settings.image_base_url,
            model=settings.image_model,
            width=settings.image_width,
            height=settings.image_height,
            api_key=api_key,
        )

    def provider_status(
        self, provider_key: Optional[str] = None, force: bool = True
    ) -> dict[str, str]:
        """Honest status for the UI.

        ``force=True`` probes the provider synchronously (network call —
        use from worker threads). Cached results are reused for 10 s;
        mock providers answer instantly.
        """
        settings = self._settings_service.settings
        provider = self.build_provider(provider_key)
        if provider.is_mock:
            detail = (
                "OFFLINE MODE — MOCK fallback"
                if settings.offline_mode
                else "Mock (dev fallback)"
            )
            return {"provider": "mock", "status": "mock", "detail": detail}

        cache_key = provider.key
        cached = self._status_cache.get(cache_key)
        if cached is not None:
            cached_at, cached_status = cached
            if not force and time.monotonic() - cached_at < _STATUS_TTL:
                return cached_status

        if provider.key in ("sdwebui", "comfyui"):
            availability = provider.availability()
            base = (
                settings.sdwebui_base_url if provider.key == "sdwebui"
                else settings.comfyui_base_url
            )
            label = (
                "SD WebUI" if provider.key == "sdwebui" else "ComfyUI"
            )
            if availability == "online":
                models = provider.list_models()
                detail = f"{base} · {len(models)} model(s)"
                result = {
                    "provider": provider.key,
                    "status": "online",
                    "detail": detail,
                    "models": ",".join(models),
                }
                self._status_cache[cache_key] = (time.monotonic(), result)
                return result
            result = {
                "provider": provider.key,
                "status": "offline",
                "detail": f"{label} not reachable at {base}",
            }
            self._status_cache[cache_key] = (time.monotonic(), result)
            return result

        key_ok = bool(os.environ.get("AI_VISION_LAB_API_KEY"))
        if not key_ok:
            result = {
                "provider": provider.key,
                "status": "unavailable",
                "detail": "API key NOT set (AI_VISION_LAB_API_KEY)",
            }
        else:
            scope = "local endpoint" if provider.key == "local" else "EXTERNAL API"
            result = {
                "provider": provider.key,
                "status": "configured",
                "detail": f"{scope} · {settings.image_base_url}",
            }
        self._status_cache[cache_key] = (time.monotonic(), result)
        return result

    def provider_status_cached(
        self, provider_key: Optional[str] = None, ttl: float = _STATUS_TTL
    ):
        """Non-blocking status: cached probe result, or None.

        Mock providers resolve instantly. Used by the GUI thread so the
        UI never performs network I/O.
        """
        provider = self.build_provider(provider_key)
        if provider.is_mock:
            return self.provider_status(provider_key, force=False)
        cached = self._status_cache.get(provider.key)
        if cached is not None:
            cached_at, status = cached
            if time.monotonic() - cached_at < ttl:
                return status
        return None

    def list_models(self, provider_key: Optional[str] = None) -> list[str]:
        """Models known to the selected provider (empty when unsupported)."""
        provider = self.build_provider(provider_key)
        try:
            return provider.list_models()
        except Exception:  # noqa: BLE001 — model listing is best-effort
            return []

    def capabilities_for(self, provider_key: Optional[str] = None):
        """Capabilities of the selected provider (UI renders only these)."""
        return self.build_provider(provider_key).capabilities

    # ------------------------------------------------------------------
    # Queue-based generation
    # ------------------------------------------------------------------
    def enqueue(
        self,
        prompt: str,
        provider_key: Optional[str] = None,
        negative_prompt: str = "",
        width: Optional[int] = None,
        height: Optional[int] = None,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        seed: Optional[int] = None,
        model: str = "",
        preset: str = "none",
        init_image: Optional[bytes] = None,
        mask_image: Optional[bytes] = None,
        parent_id: str = "",
        version: int = 1,
    ) -> GenerationJob:
        """Create a job (preset applied) and start the queue worker.

        ``init_image`` triggers image-to-image (provider must support it —
        otherwise the job fails with a readable error). ``mask_image``
        (together with ``init_image``) triggers inpainting. ``parent_id``
        + ``version`` record the iteration lineage.

        Face reference (Phase 17): when the user enabled a stored face
        photo AND the provider declares ``supports_face_reference``, the
        photo is used as the img2img init image (local conditioning —
        the photo never leaves this machine).
        """
        settings = self._settings_service.settings
        provider = self.build_provider(provider_key)
        if (
            init_image is None
            and mask_image is None
            and bool(settings.face_reference_enabled)
            and provider.capabilities.supports_face_reference
        ):
            face_photo = _face_reference_bytes()
            if face_photo is not None:
                init_image = face_photo
        effective = apply_preset(
            preset,
            prompt,
            negative_prompt=negative_prompt,
            default_steps=steps if steps is not None else settings.image_steps,
            default_cfg=cfg if cfg is not None else settings.image_cfg,
        )
        job = GenerationJob(
            id=0,
            prompt=effective.prompt,
            negative_prompt=effective.negative_prompt,
            provider_key=provider_key or settings.image_provider,
            width=width if width is not None else settings.image_width,
            height=height if height is not None else settings.image_height,
            steps=effective.steps,
            cfg=effective.cfg,
            seed=seed if seed is not None else settings.image_seed,
            model=model or settings.image_model,
            preset=preset,
            init_image=init_image,
            mask_image=mask_image,
            parent_id=parent_id,
            version=version,
        )
        job = self._queue.enqueue(job)
        self._ensure_worker()
        return job

    def inpaint(
        self,
        prompt: str,
        init_image: bytes,
        mask_image: bytes,
        provider_key: Optional[str] = None,
        negative_prompt: str = "",
        seed: Optional[int] = None,
        parent_id: str = "",
        version: int = 1,
    ) -> GenerationJob:
        """Enqueue a masked regeneration (inpainting).

        Capability-gated in the worker: providers without
        ``supports_inpainting`` fail the job with a readable error —
        the UI never offers the action for them.
        """
        return self.enqueue(
            prompt,
            provider_key=provider_key,
            negative_prompt=negative_prompt,
            seed=seed,
            init_image=init_image,
            mask_image=mask_image,
            parent_id=parent_id,
            version=version,
        )

    def cancel(self, job_id: int) -> bool:
        """Cancel a queued or generating job (cooperative)."""
        cancelled = self._queue.cancel(job_id)
        job = self._queue.get(job_id)
        if job is not None:
            self._notify(job)
        return cancelled

    # ------------------------------------------------------------------
    # Backward-compatible single-shot API (used by tests / callers)
    # ------------------------------------------------------------------
    def generate_async(
        self,
        prompt: str,
        on_done: Optional[DoneCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        **params: object,
    ) -> threading.Thread:
        """Enqueue one generation; returns a thread that waits for it."""
        job = self.enqueue(prompt, **params)

        def _wait() -> None:
            while True:
                if job.status == COMPLETED:
                    if on_done is not None:
                        on_done(job.result, job.record)
                    return
                if job.status == FAILED:
                    if on_error is not None:
                        on_error(job.error or "Generation failed.")
                    return
                if job.status == "CANCELLED":
                    if on_error is not None:
                        on_error("Generation cancelled.")
                    return
                time.sleep(_WAIT_POLL)

        thread = threading.Thread(
            target=_wait, name="image-generation-wait", daemon=True
        )
        thread.start()
        return thread

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------
    def _ensure_worker(self) -> None:
        with self._worker_lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(
                target=self._worker_loop, name="image-queue-worker", daemon=True
            )
            self._worker.start()

    def _worker_loop(self) -> None:
        log.info("Image generation worker started")
        while not self._stop_event.is_set():
            job = self._queue.pop_next(timeout=2.0)
            if job is None:
                continue
            self._run_job(job)
        log.info("Image generation worker stopped")

    def close(self) -> None:
        """Stop the queue worker (idempotent; queued jobs stay queued).

        The worker thread is a daemon and would die with the process
        anyway — this makes shutdown explicit and prompt.
        """
        self._stop_event.set()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=3.0)

    def _run_job(self, job: GenerationJob) -> None:
        job.status = GENERATING
        job.started_at = time.monotonic()
        job.progress = 0.0
        self._notify(job)

        provider = self.build_provider(job.provider_key)
        start = time.perf_counter()
        try:
            if job.mask_image is not None:
                if not provider.capabilities.supports_inpainting:
                    raise RuntimeError(
                        f"Provider '{provider.display_name}' does not "
                        "support inpainting."
                    )
                result = provider.inpaint(
                    prompt=job.prompt,
                    init_image=job.init_image,
                    mask_image=job.mask_image,
                    negative_prompt=job.negative_prompt,
                    steps=job.steps,
                    cfg=job.cfg,
                    seed=job.seed,
                    model=job.model,
                    on_progress=lambda p: self._on_progress(job, p),
                    cancel_event=job.cancel_event,
                )
            elif job.init_image is not None:
                if not provider.capabilities.supports_img2img:
                    raise RuntimeError(
                        f"Provider '{provider.display_name}' does not "
                        "support image-to-image."
                    )
                result = provider.generate_img2img(
                    prompt=job.prompt,
                    init_image=job.init_image,
                    negative_prompt=job.negative_prompt,
                    steps=job.steps,
                    cfg=job.cfg,
                    seed=job.seed,
                    model=job.model,
                    on_progress=lambda p: self._on_progress(job, p),
                    cancel_event=job.cancel_event,
                )
            else:
                result = provider.generate(
                    prompt=job.prompt,
                    negative_prompt=job.negative_prompt,
                    steps=job.steps,
                    cfg=job.cfg,
                    seed=job.seed,
                    model=job.model,
                    on_progress=lambda p: self._on_progress(job, p),
                    cancel_event=job.cancel_event,
                )
        except Exception as exc:  # noqa: BLE001 — readable job error
            log.warning(
                "Generation job #%d failed (%s): %s",
                job.id, provider.key, exc,
            )
            if job.cancel_event.is_set():
                job.status = "CANCELLED"
                job.error = None
            else:
                job.status = FAILED
                job.error = f"IMAGE GENERATION UNAVAILABLE — {exc}"
                self.last_error = str(exc)
            job.finished_at = time.monotonic()
            job.duration_ms = (job.finished_at - job.started_at) * 1000.0
            self._notify(job)
            return

        job.duration_ms = (time.perf_counter() - start) * 1000.0
        record = None
        if self._store is not None:
            record = ImageRecord(
                file="",
                timestamp=time.time(),
                provider=result.provider,
                prompt=result.prompt,
                width=result.width,
                height=result.height,
                is_mock=result.is_mock,
                negative_prompt=job.negative_prompt,
                model=result.extra.get("model", job.model) or "",
                seed=result.extra.get("seed"),
                steps=result.extra.get("steps", job.steps),
                cfg=result.extra.get("cfg", job.cfg),
                duration_ms=round(job.duration_ms, 1),
                source="generated",
                version=job.version,
                parent_id=job.parent_id,
            )
            try:
                record = self._store.save(record, result.png_bytes)
            except OSError as exc:
                log.error("Could not save generated image: %s", exc)
                record = None
        job.result = result
        job.record = record
        job.status = COMPLETED
        job.finished_at = time.monotonic()
        self.last_duration_ms = job.duration_ms
        self.last_error = None
        self._notify(job)
        log.info(
            "Generation job #%d completed (%.1f ms)", job.id, job.duration_ms
        )

    def _on_progress(self, job: GenerationJob, progress: float) -> None:
        job.progress = max(0.0, min(1.0, progress))
        self._notify(job)

    def _notify(self, job: GenerationJob) -> None:
        for callback in list(self._status_callbacks):
            try:
                callback(job)
            except Exception:  # noqa: BLE001 — UI callback must not kill worker
                log.exception("Status callback failed")


def _face_reference_bytes() -> Optional[bytes]:
    """The locally stored face photo (None when absent/unreadable).

    The photo lives at ``data/face_reference/face_ref.png`` and is ONLY
    used for local generation conditioning — it is never uploaded to
    any external service (external providers do not declare
    ``supports_face_reference``).
    """
    from app.utils.paths import data_dir

    path = data_dir() / "face_reference" / "face_ref.png"
    try:
        return path.read_bytes()
    except OSError:
        return None
