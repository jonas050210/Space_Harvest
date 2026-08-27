# Roadmap — AI Vision Lab

Product language is English. Historical phase notes below are the
authoritative status, not leftover German drafts.

## PHASE 1 — Foundation + Camera + Face Mesh

**Status: done**

Project architecture, camera system, PySide6 GUI, face detection, face
mesh (478 landmarks), FPS/CPU/RAM, vision pipeline, settings, logging,
first test suite.

## PHASE 2 — Eye Tracking + Blink + Head Pose

**Status: done**

Iris tracking, gaze estimation + 9-point calibration, One-Euro smoothing,
blink state machine, head pose (solvePnP), RAM-only gaze session.

## PHASE 3 — Objects + Hands + Gestures + Persons

**Status: done**

EfficientDet-Lite0 (80 COCO classes), object tracker, hand landmarker
(21 points), geometric gestures, person-face linking, scene snapshot.

## PHASE 4 — AI Vision + Image Generation

**Status: done**

Grounded LLM (Ollama / OpenAI-compatible / Mock), deterministic
commands, chat UI, scene events, mock + API image providers, gallery.

## PHASE 5 — Performance + Image Generation expansion

**Status: done** (target-hardware verification still open — see below)

QUALITY / BALANCED / PERFORMANCE modes, GPU delegate with CPU fallback,
SD WebUI provider, capabilities, presets, generation queue.

## PHASE 6 — Body pose + Image analysis + Studio layout

**Status: done**

Pose landmarker, local image analysis, upload, feedback, versioned
regeneration, img2img, face-reference gating, EXE packaging, hardware
smoke script.

## PHASE 7 — Robustness + honest progress

**Status: done**

Live pipeline status, honest progress, writable-path fallback, privacy
scan, reconnect / provider-error robustness.

## PHASE 8 — Cleaning + Release v1.0.0

**Status: done**

Dead-code removal, analysis-engine race fix, UI polish, docs.

## PHASE 9 — Ultimate 2.0 (v1.1.0)

**Status: done**

LIVE INSPECTOR, body geometry 2.0, more commands/presets, gallery 2.0,
demo mode (16/16).

## PHASE 10 — Studio UI overhaul (v1.2.0)

**Status: done**

Nav rail (7 pages), Home dashboard, overlay presets, command center,
toasts, Demo 2.0.

## PHASE 11 — Intelligence + interaction (v1.3.0)

**Status: done**

System diagnostics (`--check`), live events 2.0, reaction engine, scene
capture, object selection, feedback 3.0.

## PHASE 12 — Professional polish (v1.4.0)

**Status: done**

Design system v1.4, Home 2.0, onboarding, live HUD, Command Center 2.0.

## PHASE 13A — Pre-hardware hardening (v1.4.1)

**Status: done**

Non-blocking provider probes, shutdown safety, memory bounds, full
light theme, settings groups + reset, workflow gating.

## PHASE 13B — Hardware acceptance tools (v1.4.2)

**Status: preparation done — actual hardware run is UNTESTABLE here**

`hardware_acceptance.py`, extended `hardware_smoke.py`,
`stability_probe.py`, LLM STOP, head-pose sign pin.

## PHASE 14 — Acceptance findings (v1.5.0)

**Status: software done. Hardware: PENDING HARDWARE ACCEPTANCE.**

Windows RSS fix, provider-switch crash, create-gating after queue
pruning, acceptance framework v2 (29-point matrix).

## PHASE 15 / 16 — Acceptance orchestration (v1.5.1 / v1.6.0 RC)

**Status: software done. Hardware: PENDING HARDWARE ACCEPTANCE.**

Report importer (STALE / version / environment), strict READY rules,
stability probe v2. Sandbox verdict: NOT READY (honest camera FAIL).

## PHASE 17 / 18 — Advanced vision + polish (v1.7.0)

**Status: done**

System TTS, local face-reference img2img, inpainting, DESCRIBE PERSON.
UI sweep, FAQ.

## PHASES 19–21 — Re-run + hardening + release gate (v1.7.1)

**Status: done**

Demo-title leak, STOP-button honesty, 50 MB upload guard,
`scripts/release_gate.py`. Software PASS · Hardware UNTESTABLE.

## PHASES 22–24 — Session memory + UX + review (v1.8.0)

**Status: done**

REMEMBER / RECALL / FORGET (local providers only), CAPTURE AND GENERATE,
dead-code removal.

## PHASE 25 — Showtime (v1.9.0)

**Status: done**

Stage Mode (F11), hardware-report view, window-state memory,
`setup_windows.bat`.

## PHASE 25.1 — 2K webcam (v1.9.1)

**Status: done**

2560×1440 + MJPG FOURCC. Real 2K verification UNTESTABLE until acceptance.

## PHASE 26 — Analytics wave (v2.0.0)

**Status: done**

INSIGHTS page, gaze heatmap, Scene Pulse, gesture actions, Session Recap.

## PHASE 27 — Bug-hunt (v2.0.0)

**Status: done**

Fuzz suite. Five real bugs fixed (settings validators, annotator guard,
importer recursion, pulse/recap/refine_prompt). Software PASS · Hardware
UNTESTABLE → NOT READY (honest).

## PHASE 28.1 — Startup hotfix (v2.1.1)

**Status: done**

Windows start path: `python setup.py` bootstraps instead of printing
setuptools usage. MediaPipe + protobuf 5 `GetPrototype` pin and shim.
Python 3.11 analyze-panel SyntaxError. RESET ALL SETTINGS no longer
crashes on the missing extensions checkbox. Gesture actions accept the
real `OPEN PALM` name. System-check results stay on the GUI thread.

## PHASE 28 — English product · Hardware handoff · Capture studio (v2.1.0)

**Status: software done. Hardware: PENDING HARDWARE ACCEPTANCE.**

- Product language is English (README / ROADMAP / CHANGELOG / scripts /
  checklist). German chat aliases remain as a documented bilingual
  feature, not leftover UI.
- Honest cleanup: stale "future ideas" that were already built (TTS,
  face reference, inpainting, heatmaps) are no longer listed as missing.
  Test count documented as 700+ functions, not an inflated headline.
  `LICENSE` is a first-class root file. `app/__init__.py` no longer
  claims "Phase 1".
- Hardware handoff pack: `scripts/accept_windows.bat` (check → smoke →
  auto acceptance → stability → merge) and
  `scripts/acceptance_checklist.txt`. On the target PC you run the bat
  file and tick the list.
- Local video recording + snapshots (`app/capture/`, Vision page RECORD /
  SNAPSHOT, hard 10 min / 2 GB caps, auto-stop on camera stop).
- ComfyUI image provider (local `/prompt` graph, honest OFFLINE).
- System STT via Windows SAPI dictation (same philosophy as TTS). No
  Whisper. Linux/macOS stay `mock` / `unavailable` and never invent a
  transcript.
- Local extension hooks (`data/extensions/*.py`, opt-in, isolated).
  Not a marketplace.

---

## Open hardware acceptance (target machine only)

This Linux sandbox has no webcam, no NVIDIA GPU, no Ollama, no SD WebUI,
no ComfyUI and cannot build a Windows EXE. Those items stay
**UNTESTABLE** until you run the pack on:

Windows 11 · i7-12700F · RTX 4060 Ti 8 GB · 32 GB RAM · Python 3.11 ·
webcam · optional Ollama / SD WebUI / ComfyUI

See README "Real hardware acceptance" and
`scripts/acceptance_checklist.txt`.

## Next (priority order)

1. **You, on the target PC** — `scripts\accept_windows.bat --minutes 10`,
   then the interactive 20-step workflow, EXE + shortcut, release gate.
2. **Findings & production release** — fold real latencies / GPU / VRAM /
   head-pose confirmation into the docs. READY only with a real report.
3. **Model-memory dedup** between live and analysis pipelines — only
   after a measurement says it is worth the risk. Documented trade-off.
4. **Neural STT** (faster-whisper or similar) — only if you want the
   extra dependency. System STT already covers the no-new-package case.
5. **More image backends** (extra ComfyUI workflows, other local UIs) —
   only on request; cloud stays opt-in and warned.
6. **Richer extensions** — vision-module hooks if a real plugin needs
   them. The registry is the public surface.
7. **main_window.py split** — 3 200+ lines. Extract page builders when
   the next UI wave needs it. Not a rewrite for its own sake.

## Deliberately not implemented

- Medical / clinical claims
- Automatic upload of frames or face photos
- Pretending GPU / camera / Ollama / ComfyUI work when they are absent
- A plugin marketplace or remote code execution
- Sharing one MediaPipe pipeline across live + analysis (stability
  first; documented memory cost)

**Design rule for every phase:** new capabilities register as a
`VisionModule`, an `ImageProvider`, a deterministic command or an
extension hook. Existing code stays put. Shared face data is never
inferred twice.
