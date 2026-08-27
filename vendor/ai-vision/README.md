# AI Vision Lab

**Live AI Vision Studio** — a local-first desktop application that turns a
webcam into a computer-vision command center: face, body, arms, hands,
objects, gaze — plus AI chat, image generation, automatic image analysis,
feedback-driven regeneration, session recording and a scripted demo mode.
Everything runs locally by default; no cloud is required.

> **Release v2.1.1** — Startup hotfix: `python setup.py` actually
> bootstraps, MediaPipe/protobuf `GetPrototype` pin + shim, Python 3.11
> f-string crash, RESET ALL SETTINGS crash, real `OPEN PALM` gesture
> actions. Hardware status: **UNTESTABLE / PENDING HARDWARE ACCEPTANCE**.
>
> Release v2.1.0 — Phase 28: English product surface, one-click
> hardware-acceptance pack, local video recording + snapshots, ComfyUI
> provider, system STT (Windows SAPI, honest status), local extension
> hooks.
>
> Release v2.0.0 — Analytics wave: INSIGHTS page, gaze heatmap, Scene
> Pulse, Session Recap, gesture actions (palm = capture, fist = HUD).

---

## Overview

AI Vision Lab combines a 12-module MediaPipe vision pipeline with a
professional PySide6 studio UI:

```
WEBCAM → LIVE VISION (Face/Body/Arms/Hands/Objects/Gaze)
       → SCENE SNAPSHOT → AI CONTEXT
       → IMAGE GENERATION → IMAGE ANALYSIS
       → FEEDBACK → PROMPT REFINEMENT → REGENERATION → COMPARE
```

Deterministic commands work fully offline. The LLM is optional. Providers
are capability-gated. Every status and progress value shown in the UI
comes from a real measurement.

The product language is **English**. Deterministic chat commands still
recognize a set of German aliases (a documented bilingual feature, not
leftover UI text).

## Quick Start (Windows)

**One-click:** double-click `scripts\setup_windows.bat`, or run
`py setup.py` — venv, dependencies, models and a system check, with
honest error messages.

Manual:

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py --check
python main.py
```

Vision models are bundled under `data/models/` (~30 MB) so a fresh clone
runs offline. Optional: [Ollama](https://ollama.com) for free-form chat.
Optional: `python scripts/demo.py` for a full guided tour without
hardware.

## Features

| Area | Highlights |
|---|---|
| **Design System** | Dark premium command-center design. Status colors only when they mean something: LIVE / READY / PROCESSING / OFFLINE / ERROR / CPU / GPU / MOCK / UNTESTABLE |
| **Live Vision** | Face detection/mesh (478 landmarks), eye tracking, gaze + calibration, blink, head pose, body pose (33 landmarks), hand tracking (21 landmarks), gestures, object detection (80 COCO classes), person-face linking, live HUD |
| **Studio UI** | 8-page navigation including INSIGHTS, Home Dashboard 2.0, first-run onboarding, LIVE INSPECTOR 2.0, Command Palette (Ctrl+K), structured toasts, Stage Mode (F11), remembered window state |
| **Analytics** | INSIGHTS: attention cards, gaze heatmap (live overlay + preview), Scene Pulse timeline, deterministic Session Recap (RAM-only) |
| **Capture** | Local video recording + still snapshots (`data/recordings/`). User-started only. Hard caps (10 min / 2 GB). Frames never leave the machine |
| **Hardware reports** | SYSTEM → LOAD REPORTS renders the real 29-point verification matrix. Stale or foreign reports never count |
| **AI** | Grounded LLM chat (Ollama / OpenAI-compatible / Mock), deterministic EN commands (+ DE aliases), session memory (local providers only), scene watches, live events with cooldowns |
| **Voice** | System TTS (Windows SAPI / macOS `say` / Linux `spd-say`). System STT on Windows SAPI dictation. Capability-gated (`real` / `mock` / `unavailable`). No Whisper dependency |
| **Image Generation** | Mock / SD WebUI / ComfyUI / OpenAI-compatible. 15 presets, img2img, inpainting, queue with cancel, capability-gated options |
| **Image Analysis** | Local analysis, prompt matching, scene comparison, DIFF compare |
| **Feedback Loop** | CORRECT / PARTIAL / WRONG + categories → deterministic prompt refinement → versioned regeneration |
| **Gallery** | Search, filters, sort, hover preview, detail panel |
| **Demo Mode** | 16-step product tour with a simulated camera and a permanent DEMO FEED watermark |
| **Extensions** | Opt-in local `data/extensions/*.py` plugins. Isolated. No marketplace, nothing downloaded |
| **Operations** | `python main.py --check`, hardware smoke / acceptance / stability, performance modes, GPU delegate with CPU fallback |

## Requirements

- Python 3.11+ (target: Windows 11, Python 3.11)
- Windows 10/11, macOS or Linux
- A webcam (optional — the app and the demo run without one)
- Internet once only if you need to re-download models

## Hardware

| Component | Role | Status in this environment |
|---|---|---|
| CPU | Default vision inference | verified |
| NVIDIA GPU (e.g. RTX 4060 Ti) | Optional MediaPipe GPU delegate with CPU fallback | **UNTESTABLE here** |
| Webcam | Live vision input | **UNTESTABLE here** |
| Ollama | Local LLM | **UNTESTABLE here** |
| SD WebUI / ComfyUI | Local image generation | **UNTESTABLE here** |

On the target machine:

```bat
python main.py --check
python scripts/hardware_smoke.py
python scripts/accept_windows.bat --minutes 10
```

## Installation

```bash
cd AI-Vision-Lab
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Offline model refresh: `python scripts/download_models.py`.

## First start

1. `python main.py` — Home shows a 6-step WELCOME card:
   **SYSTEM CHECK → VISION MODELS → CAMERA SETUP → AI PROVIDER → IMAGE PROVIDER → START DEMO**.
   Every step shows real state: READY / OPTIONAL / UNAVAILABLE / ACTION REQUIRED.
2. **RUN SYSTEM CHECK** — the same 9 checks live under SYSTEM anytime.
3. Start with **START DEMO** if you have no camera and no providers.
4. Dismiss the welcome card when you are ready.

## Real hardware acceptance

Production **READY** is issued only on the target machine, never here.
Missing reports are never treated as PASS. Old reports (> 30 days),
other app versions or other machines are marked STALE and ignored.

**One-click pack** (double-click on Windows):

```bat
scripts\setup_windows.bat
scripts\accept_windows.bat --minutes 10
```

**Manual sequence:**

```bat
python main.py --check
python scripts\hardware_smoke.py --json smoke.json
python scripts\hardware_acceptance.py --json acceptance.json
python scripts\stability_probe.py --minutes 10 --camera 0 --json stability.json
python scripts\hardware_acceptance.py --json acceptance.json --reports .
packaging\windows.bat
powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1
python scripts\release_gate.py
```

Printed tick-list: `scripts/acceptance_checklist.txt`.

| Result | Meaning |
|---|---|
| **PASS** | The test really ran on this machine and succeeded |
| **FAIL** | The test really ran and failed — fix it |
| **UNTESTABLE** | Could not run here — never counted as passed |
| **READY** | Every production-relevant step is REAL VERIFIED |
| **NOT READY** | At least one relevant test really failed |
| **INCOMPLETE** | Not enough real hardware data |

Ollama / SD WebUI / ComfyUI are optional (the product runs without them).
`--require-ollama` / `--require-sdwebui` make those items blocking.

## Providers

- **LLM:** Ollama (local), OpenAI-compatible (SSE streaming), Mock.
- **Image:** Mock, SD WebUI (txt2img + img2img + inpaint), ComfyUI
  (local txt2img graph), Local / External OpenAI-compatible Images API.
- Capabilities are declared honestly. Options a provider cannot do are
  hidden or disabled — never faked.
- API keys live only in the environment variable `AI_VISION_LAB_API_KEY`.
  Keys are never stored in settings, logs, UI or source.

## Configuration

Settings live in `data/settings.json` (validated, saved atomically).

| Setting | Default | Meaning |
|---|---|---|
| `llm_provider` / `llm_model` / `llm_base_url` | `ollama` / empty / `http://localhost:11434` | LLM |
| `image_provider` | `mock` | `mock` / `sdwebui` / `comfyui` / `local` / `external` |
| `sdwebui_base_url` | `http://127.0.0.1:7860` | AUTOMATIC1111 / Forge / SD.Next |
| `comfyui_base_url` | `http://127.0.0.1:8188` | ComfyUI |
| `vision_mode` | `balanced` | QUALITY / BALANCED / PERFORMANCE |
| `vision_delegate` | `cpu` | `gpu` = GPU delegate with CPU fallback |
| `offline_mode` | `false` | Force mock fallback, no network |
| `extensions_enabled` | `false` | Load `data/extensions/*.py` |

**SYSTEM → RESET ALL SETTINGS** restores every default. Images and
uploads are kept.

## Privacy

- Camera frames never leave the process automatically.
- The LLM receives structured scene summaries only — no frames, no
  landmark arrays.
- Recordings and snapshots stay in `data/recordings/`.
- Uploads stay in `data/uploads/`. An optional face photo stays in
  `data/face_reference/`.
- External providers receive prompt text only, after an explicit click,
  with a visible warning.
- Session / chat / memory data is RAM-only.
- Extensions are local Python files. Nothing is downloaded.

## Capture (Phase 28)

- **RECORD** on the Vision page (or the command "start recording") writes
  a local video of the live camera. **STOP REC** finishes it.
- Hard stop at 10 minutes or 2 GB so a forgotten RECORD cannot fill the disk.
- Stopping the camera or closing the window stops the recording.
- **SNAPSHOT** saves the current frame as a JPEG next to the videos.
- Nothing is uploaded. Demo mode records the simulated feed and labels it.

## Voice

- **SPEAK** reads the last answer through the OS voice (capability-gated).
- **LISTEN** (Windows SAPI dictation) captures one utterance and treats it
  like a typed chat message. On Linux/macOS the button stays hidden or
  reports `mock` — it never invents a transcript.
- Neural STT (Whisper and friends) is deliberately **not** bundled.

## Extensions

Opt-in (`SYSTEM → Load local extensions`). Drop a `*.py` file into
`data/extensions/`:

```python
EXTENSION = {"name": "hello", "version": "1"}

def register(hooks):
    hooks.add_command("HELLO", ("say hello",), handler=lambda *a, **k: "hi")
```

A broken plugin is isolated. Recursive imports, hidden files and files
larger than 256 KB are skipped. There is no plugin marketplace.

## Demo mode

```bash
python main.py --demo     # guided product tour (GUI)
python scripts/demo.py    # reproducible headless run + report
```

16 steps, simulated camera, permanent DEMO FEED watermark, labeled mock
providers. No fake hardware.

## Testing

```bash
pytest                    # on the target machine (32 GB) in one go
```

In a 2 GB sandbox run the documented chunks (MediaPipe holds model
memory per process). Phase 28: `pytest tests/test_phase28_smoke.py`.

Documented suite: **700+ tests** across 34 files (phases 1–28), plus
`python main.py --check`, `scripts/hardware_smoke.py`,
`python scripts/demo.py` and `python main.py --demo`.

## Windows EXE

```bat
packaging\windows.bat                 & REM builds dist\AI-Vision-Lab\
```

onedir build. The spec was assembled on Linux; the Windows build itself
is **UNTESTABLE** in this environment.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Camera not found | unplugged / used by another app / Windows privacy | plug in, close other apps, allow desktop camera access, press refresh |
| GPU not detected | no `nvidia-smi` / no GPU | CPU mode is fully supported |
| CPU fallback | MediaPipe GPU delegate not in this build | intended and stable |
| Ollama unavailable | service not running | `ollama serve`; check the base URL |
| SD WebUI / ComfyUI offline | service not running | start it (ports 7860 / 8188) |
| Provider error | endpoint / key | read the queue/gallery message; check `AI_VISION_LAB_API_KEY` |
| Permission denied | project folder not writable | use a writable folder — the app falls back to `~/.ai-vision-lab` |
| Slow FPS | heavy modules + high resolution | PERFORMANCE mode, 720p, disable Face Mesh / objects |
| LISTEN hidden | no OS recognizer | expected on Linux/macOS; type the command instead |
| RECORD fails | camera not running / no codec | start the camera; MJPG/AVI fallback is automatic |
| `setup.py` used to say "no commands supplied" | it is now the bootstrap | run `py setup.py` (or `scripts\setup_windows.bat`) |
| `MessageFactory` / `GetPrototype` | protobuf 5+ vs MediaPipe 0.10 | `pip install "protobuf>=4.25.3,<5"` then `python start.py` |
| `f-string: unmatched '['` | Python 3.11 + nested quotes | fixed in v2.1.1 — update and retry |

## FAQ

**Do I need a GPU?** No. CPU is the stable default.

**Do I need Ollama?** No. Deterministic commands, vision, generation
(Mock / SD WebUI / ComfyUI) and analysis work without it.

**Is this a medical eye tracker?** No. Gaze and head-pose values are
webcam estimates (documented, calibratable).

**Are images uploaded?** Only if you pick an EXTERNAL provider and press
GENERATE — with a visible warning.

**Does the app speak / listen?** Speak: yes, via the OS voice when one
is found. Listen: Windows SAPI only. Otherwise the controls stay honest.

**Where is my data?** `data/` (models, settings, generated images,
uploads, recordings) — project-relative, no Windows hard-coding.

## License

MIT. Vendored static data (MediaPipe mesh/hand/pose connections, COCO
labels) is Apache-2.0 and attributed in the respective source files.
