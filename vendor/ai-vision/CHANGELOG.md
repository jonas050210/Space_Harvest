# Changelog

All notable changes to AI Vision Lab. Format follows
[Keep a Changelog](https://keepachangelog.com/) (simplified).

## [2.1.1] — 2026-08-19 — Startup hotfix (Windows Python 3.11)

### Fixed

- **`python setup.py` / `py setup.py`** with no arguments used to print
  setuptools `error: no commands supplied`. It now bootstraps the
  project: create `.venv`, install `requirements.txt`, download models,
  run `python main.py --check`. Packaging commands (`sdist`, `egg_info`,
  `pip install -e .`) are unchanged.
- **MediaPipe + protobuf.** `AttributeError: 'MessageFactory' object has
  no attribute 'GetPrototype'` on `import mediapipe` when protobuf 5+ is
  installed. Pin `protobuf>=4.25.3,<5` and apply a compatibility shim
  before every MediaPipe import (`start.py`, `main.py`, diagnostics,
  vision helpers).
- **`start.py`** treated only `ImportError` as a missing dependency, so
  the MessageFactory crash printed and the launcher continued into a
  later SyntaxError. Any import exception is now a hard, readable stop
  with `python setup.py` / protobuf pin instructions.
- **Analyze report HTML** used nested double quotes inside f-strings
  (`colors["muted"]`) — a SyntaxError on Python 3.11, the project's
  target. Already switched to `colors['muted']`; comparison HTML no
  longer `html.escape`s its own tags.
- **RESET ALL SETTINGS** crashed: `sync_from_settings` touched
  `extensions_check`, which was never created. The checkbox is on the
  SYSTEM page.
- **Gesture actions** looked for `OPEN_PALM`; the live recognizer emits
  `OPEN PALM`. Both names (and `FIST`) now work.
- **System check** callbacks updated Qt widgets from a worker thread.
  Results now travel through queued signals.
- **`python test_overall.py`** produced no output (pytest file with no
  `__main__`). It now runs the tests.
- **RECORD / SNAPSHOT / LISTEN** buttons and chat commands were wired to
  methods that did not exist (`_toggle_recording`, `_take_snapshot`,
  `_listen_query`). Clicking them crashed. Handlers are implemented;
  the capture worker now stores the raw frame and writes the recorder.
- **`CameraController.take_snapshot`** annotated return type used
  `Path` without importing it (pyflakes).
- **Home onboarding** called `provider_status()` (network, force) on
  every 2 Hz GUI refresh. With the default Ollama provider that froze
  the UI whenever the service was down. Cached status only.
- **Image store** appended a duplicate gallery entry when the same file
  was saved twice; filename allocation is now a single lock + upsert.
- **Generation queue overflow** could drop a job that was still
  `GENERATING`. Oldest terminal/queued jobs are dropped instead.
- **Image analysis** now keeps its "never raises" contract on empty or
  non-BGR arrays. Pipeline finalize tolerates a missing frame.
- Analyze-report HTML escapes source and prompt-match terms.

### Changed

- Version **2.1.1** in `app/__init__.py` and `setup.py`.

## [2.1.0] — 2026-08-19 — Phase 28 (English product · Hardware handoff · Capture studio)

### Added

- **English product surface.** README, ROADMAP, CHANGELOG, acceptance
  scripts and the printed checklist are English. The UI already was.
  German chat aliases stay as a documented bilingual feature.
- **Hardware handoff pack.** `scripts/accept_windows.bat` runs check →
  smoke → auto acceptance → stability → merge. Printed tick-list:
  `scripts/acceptance_checklist.txt`. On the target PC you run the bat
  file and follow the list — nothing is invented here.
- **Local video recording + snapshots** (`app/capture/recorder.py`).
  Vision page RECORD / SNAPSHOT, commands START/STOP RECORDING and
  TAKE SNAPSHOT. Hard caps: 10 minutes or 2 GB. Auto-stop when the
  camera stops or the window closes. Files stay in `data/recordings/`.
- **ComfyUI provider** (`app/image/providers/comfyui.py`). Local
  `/prompt` graph (txt2img). Honest OFFLINE when ComfyUI is down.
  Setting `comfyui_base_url` (default `http://127.0.0.1:8188`).
- **System STT.** Windows SAPI dictation via PowerShell — same
  philosophy as TTS, no Whisper. LISTEN button is capability-gated.
  Linux/macOS report `mock` / `unavailable` and never invent a transcript.
- **Local extensions** (`app/extensions/`). Opt-in
  (`extensions_enabled`, default off). `data/extensions/*.py` may
  register extra commands. A broken plugin cannot crash the app.

### Fixed

- Analyze-report HTML used nested double quotes inside f-strings
  (`colors["muted"]`). That is a SyntaxError on Python 3.11 — the
  project's target. Switched to `colors['muted']`.

### Changed

- Version **2.1.0** in `app/__init__.py` and `setup.py`.
- `LICENSE` is a first-class allowed root file (release gate).
- `requirements.txt` no longer says "Phase 1 dependencies".
- Image-provider set: `mock` / `sdwebui` / `comfyui` / `local` / `external`.
- Documented test count is honest: **700+ tests** across 34 files,
  not an inflated headline.

### Verified (honest classification)

- New Phase-28 tests (recorder, ComfyUI stub, STT honesty, extension
  isolation, settings, commands, handoff artifacts, English docs).
- Hardware: **UNTESTABLE / PENDING HARDWARE ACCEPTANCE**.
- Release gate: Software PASS expected · Hardware UNTESTABLE → NOT READY.

## [2.0.0] — 2026-08-18 — Phases 26/27 (Analytics wave + final bug-hunt)

### Added (Phase 26)

- INSIGHTS page (8th studio page, Ctrl+8): attention cards, gaze-heatmap
  preview, Scene Pulse (10 min), deterministic Session Recap.
- Gaze heatmap (`app/vision/heatmap.py`): fixed grid, decay, live overlay
  + INSIGHTS preview.
- Scene Pulse timeline under the live feed (5 min) and on INSIGHTS.
- Gesture actions (setting `gesture_actions`, default off): OPEN PALM =
  capture scene, FIST = toggle HUD. 3 s cooldown + toast.
- SESSION RECAP command (offline, no LLM).

### Fixed (Phase 26 / 27)

- Heatmap LUT used NumPy indexing instead of a broken `cv2.LUT`.
- Settings float validators no longer crash on `float(None)`; string/int
  fields reject the wrong type.
- Annotator ignores 2D overlays (ndim / channel guard).
- Report importer classifies pathologically nested JSON as corrupt
  instead of raising RecursionError.
- Pulse / recap / `refine_prompt` tolerate bad input.

### Verified

- 815 collected pytest items across phases 1–27 at the time (see v2.1.0
  for the honest function count). Demos 3x 16/16.
- Release gate: Software PASS · Hardware UNTESTABLE → NOT READY.

## [1.9.1] — 2026-08-18 — Phase 25.1 (2K webcam)

- `COMMON_RESOLUTIONS` now leads with 2560x1440.
- Camera engine requests MJPG FOURCC before the resolution (best-effort).
- `hardware_smoke.py` probes 1440p.
- Real 2K verification: UNTESTABLE until acceptance.

## [1.9.0] — 2026-08-18 — Phase 25 (Stage Mode · reports · window state)

- Stage Mode (F11): frameless always-on-top live feed, zero-copy frames.
- SYSTEM → LOAD REPORTS renders the 29-point matrix from real JSONs.
- Window size / position / last page remembered.
- `scripts/setup_windows.bat` one-click Windows setup.
- Report importer moved to `app/utils/report_importer.py`.
- HUD shows "—" after the camera stops instead of a stale FPS.

## [1.8.0] — 2026-08-18 — Phases 22–24 (Session memory · UX · review)

- Session Memory: REMEMBER / RECALL / FORGET (RAM-only, local providers
  only — EXTERNAL never sees the facts).
- Compound workflow CAPTURE AND GENERATE.
- `scripts/release_gate.py` (8 checks). READY only with a real READY
  acceptance report.
- Gallery empty-state action + Home thumbnail cursor.
- Dead UI helpers removed (`KeyValueRow`, `ProcessingIndicator`, …).

## [1.7.1] — 2026-08-18 — Phases 19/20 (re-run + hardening)

- Demo title suffix appended once and restored.
- STOP button only appears for real LLM streams.
- Uploads larger than 50 MB rejected before decode.

## [1.7.0] — 2026-08-18 — Phases 17/18 (Voice · Face reference · Inpaint)

- System TTS (`VoiceEngine`): real / mock / unavailable.
- Local face-reference img2img for Mock + SD WebUI. EXTERNAL never.
- Inpainting via SD WebUI mask API + Mock echo + gallery button.
- DESCRIBE PERSON (structured, offline).
- UI sweep of every page x two sizes x both themes.

## [1.6.0] — 2026-08-18 — Phases 15/16 (Acceptance execution · RC)

- Smoke self-conflict fixed ("Camera device" vs "CAMERA").
- Full tool chain executed here with honest numbers (camera FAIL is
  real). Verdict: NOT READY. Target hardware: UNTESTABLE.
- v1.6.0 = production release candidate. Final READY needs the target PC.

## [1.5.1] — 2026-08-18 — Phase 15 (Acceptance orchestration)

- Report importer: STALE (>30 d), version / environment fingerprints,
  conflict warnings, secret scan + redaction.
- Strict READY / NOT READY / INCOMPLETE rules. Missing reports != PASS.
- Stability probe v2, JSON schema v2, Ctrl+C → exit 130.

## [1.5.0] — 2026-08-18 — Phase 14 (Acceptance findings)

- Windows RSS via ctypes `GetProcessMemoryInfo`.
- Provider-switch crash (deleted parameter widgets) fixed.
- Create-page gating after queue pruning uses the store, not the queue.
- Acceptance no longer said READY with almost nothing verified.
- Acceptance framework v2: 29-point matrix, extended probes.

## [1.4.2] — 2026-08-18 — Phase 13B (Acceptance tools)

- LLM STOP (cooperative cancel through every provider).
- `hardware_acceptance.py`, extended `hardware_smoke.py`,
  `stability_probe.py`.
- Head-pose sign pinned by a synthetic round-trip test.
- Diagnostics name contract repaired (GPU / OLLAMA).

## [1.4.1] — 2026-08-18 — Phase 13A (Hardening)

- Provider probes no longer freeze the GUI (10 s cache + worker).
- Shutdown joins helper threads; emits are teardown-safe.
- Generation queue keeps at most 60 terminal jobs in RAM.
- Light theme completed (central palette).
- Settings groups + RESET ALL SETTINGS.
- Workflow gating: no action offered that cannot work.
- Demo abort on close.

## [1.4.0] — 2026-08-18 — Phase 12 (Professional polish)

Design system v1.4, Home Dashboard 2.0, 6-step onboarding, live HUD,
Command Center 2.0, toast 2.0 (WHAT / WHY / HOW TO FIX), Create / Analyze
/ Gallery / Assistant / System 2.0, Demo 2.0 with a completion card.

## [1.3.0] — 2026-08-18 — Phase 11 (Intelligence)

`python main.py --check` (9 checks), live events 2.0, reaction engine,
scene capture, object selection, feedback 3.0, first-run welcome,
`hardware_smoke.py`. README rewritten as the product guide.

## [1.2.0] — 2026-08-18 — Phase 10 (Studio UI)

Nav rail (Home / Vision / Create / Analyze / Gallery / System /
Assistant), overlay presets, LIVE INSPECTOR 2.0, command palette,
toasts, Demo 2.0.

## [1.1.0] — 2026-08-18 — Phase 9 (AI Vision Lab 2.0)

LIVE INSPECTOR, body geometry 2.0, extra commands and presets, gallery
2.0, compare DIFF, structured provider errors, demo mode (16/16).

## [1.0.0] — 2026-08-18 — Phase 8 (First release)

Theme polish, analysis-engine race fix, `ImageGenerationEngine.close()`,
dead-code removal, version consolidation.

## [0.7.0] — 2026-08-18 — Phase 7

Honest generation progress, honest delegate display, writable-path
fallback, privacy scan as a test, robustness suite.

## [0.6.0] — 2026-08-18 — Phase 6

Body / pose vision, image analysis engine, upload, feedback + versioned
regeneration, img2img, face-reference gating, studio layout, EXE
packaging, hardware smoke.

## [0.5.0] — 2026-08-18 — Phase 5

Vision performance modes, GPU delegate with CPU fallback, SD WebUI
provider, capabilities, presets, generation queue, storage v2.

## [0.4.0] — 2026-08-18 — Phase 4

AI vision engine, Ollama / OpenAI-compatible / Mock LLM, deterministic
commands, chat UI, scene events, image generation + gallery.

## [0.3.0] — 2026-08-18 — Phase 3

Object detection + tracking, hand tracking, gestures, person tracking,
scene snapshot.

## [0.2.0] — 2026-08-18 — Phase 2

Eye tracking, gaze estimation + calibration, blink detection, head pose,
gaze session.

## [0.1.0] — 2026-08-18 — Phase 1

Architecture, camera, PySide6 GUI, face detection, face mesh, pipeline,
settings, logging, model download, first tests.
