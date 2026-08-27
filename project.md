# Asteroid-Colony Proto — Project

Master document for **Asteroid-Colony Proto: Orbital Supply Chains**. This file intentionally contains setup, architecture, controls, QA evidence, known limits, and owner hand-off notes so the repo only needs this document plus `README.md`.

Repository: https://github.com/jonas050210/asteroid-colony-proto  
Branch used by Arena: `arena/01a0418d-asteroid-colony-proto`  
Target PC: i7-12700F / 32 GB / RTX 4060 Ti 8 GB.

---

## 1. Quick start

```bash
cd asteroid-colony-proto
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m src.main --headless --sim-days 6000
.venv/bin/python -m src.main
```

Headless Linux screenshot capture, when GL/Xvfb packages are installed:

```bash
sudo apt-get install -y xvfb libgl1 libglx-mesa0
xvfb-run -a --server-args="-screen 0 1920x1200x24" .venv/bin/python scripts/capture_frame.py
```

If Xvfb/libGL is unavailable, `scripts/capture_frame.py` falls back to a clearly labelled deterministic Pillow top-down image generated through the same simulation update path.

---

## 2. Workspace and dependency rules

* Keep the virtualenv at `asteroid-colony-proto/.venv`; `.venv/` is snapshot-excluded.
* Do not vendor binary AI/model weights. `vendor/ai-vision` is code-only.
* Dependencies: `numpy`, `pillow`, `ursina>=6`, `pytest`; `matplotlib` is used for porkchop plots.
* Generated artifacts are intentionally small. Final workspace excluding `.venv`: about 6.3 MB and 327 files.

---

## 3. Concept and feature matrix

The upstream `asteroid-colony` economic regions are modelled as real heliocentric bodies. Freighters fly patched-conic transfers with launch windows, delta-v budgets, target layovers, capture burns, return windows, and docking burns. Completed deliveries are booked into the vendored upstream economy using `src.game.logistics.store()` and grant research per tonne stored.

| Area | Status |
| --- | --- |
| Upstream colony game | Vendored unmodified in `src/game/` and `vendor/asteroid-colony-upstream/`; upstream 25-test script passes. |
| Heliocentric bodies | Colony, inner belt, metallic belt, Aurelia/gas giant orbit with moon Nix, deep belt, and derelict zone with requested AU/e/i values. |
| Astrodynamics | Numpy-only universal-variable Kepler, elements conversion, Hohmann sanity checks, single-rev Izzo Lambert, porkchop windows and secant refinement. |
| Mission simulation | PENDING → OUTBOUND → capture/unload → WAITING → INBOUND → dock, with exact event jumps and separate burn billing. |
| Economy bridge | Cargo stored through upstream logistics; overflow is reported; research points accrue per stored tonne. |
| Fleet operations | Full round-trip affordability, stale-window re-solve, plan-cache TTL, idle scan throttle, refuel from colony energy, honest dry-drift failure mode. |
| Rendering | Ursina sun/halo, line-mesh orbits, bodies, freighters, fading trails, camera presets/follow. |
| HUD | Clock/warp, selected target, transfer plan, fleet status, ETA, delta-v, flight log, controls, storage and lifetime tonnage. |
| Assets | Procedural OBJ/PNG only; no external binary blobs. |
| Tooling | Test suite, screenshot capture, porkchop plot script, run log. |

---

## 4. Units and conventions

* Physics length unit: AU.
* Solar gravitational parameter: `MU_SUN = 4*pi^2`; a = 1 AU has period `2*pi` sim-seconds.
* Natural velocity unit: AU/year. Convert with `AU_PER_YEAR_TO_KM_S = 4.7405`; 1 AU/year = about 29.78 km/s.
* Do not treat AU/sim-second as km/s.
* Render scale: `SCENE_UNITS_PER_AU = 8`.
* Coordinate mapping exists in one place: `(x, y, z)_AU -> Vec3(x, z, -y)`.
* Time warp steps: 1 / 6 / 24 / 90 sim-days per real second.
* Window cache TTL is sim-time based; expired or already-passed windows are re-solved from `now`, not clamped.

---

## 5. Gameplay and controls

* TAB: cycle target.
* ENTER: dispatch an idle freighter to the selected target.
* `[` / `]`: decrease/increase warp.
* O: toggle orbits.
* F: follow ships / cycle follow target.
* C: overview camera.
* Mouse wheel: zoom.
* Esc: quit.

The intended loop is to watch launch windows, dispatch solvent ships, receive ore/ice/metals through the upstream storage economy, and keep freighters fuelled. If a ship cannot afford a required burn, it is left drifting and the log reports the failure honestly.

---

## 6. Verification log excerpts

Full output is in `run-log.txt`.

### Project tests

```text
===== Thu Aug 27 04:54:08 UTC 2026 pytest tests final =====
...........................................                              [100%]
43 passed in 8.05s
```

### Upstream `asteroid-colony` tests

`vendor/asteroid-colony-upstream/test_overall.py` is a script-style test file and should be run directly, not collected as pytest fixtures.

```text
=== Asteroid Colony Tests ===
...
=== Result: 25 passed, 0 failed ===
```

### Headless 6000-day simulation

```text
[headless] 24000 frames over 6,000 sim-days
  Kestrel pending  Inner Belt Field         6,974 m/s left
  Petrel  pending  Inner Belt Field         6,986 m/s left
  runs completed : 18
  mass delivered : 4,320 t
  delta-v spent  : 112,790 m/s
  deliveries into colony economy: 18
  colony storage : {'used': 615.0, 'capacity': 1500, 'delivered': 850.0}
  research points: 212.5
```

### Capture and porkchop artifacts

```text
[capture] wrote /home/user/asteroid-colony-proto/logs/screenshot.png (91782 bytes)
[capture] frames=700 shots=1 runs=34 delivered=8160t fallback=1
wrote logs/porkchop.png
```

### Prune / cap check

```text
du excluding .venv: 6.1M
file count excluding .venv: 314
remaining project caches: 0
src/game diff vs upstream excluding caches:
```

---

## 7. Known limits

* Lambert is single-revolution only; multi-revolution branches are future work.
* Economy balancing is prototype-level; storage can fill quickly and overflow is shown rather than hidden.
* Windowed screenshot capture on headless Linux needs host GL/Xvfb packages. The Arena apt mirror was unreachable during final verification, so the fallback screenshot was used in this sandbox.
* `AI-Vision-Lab` is included as code only; scanner gameplay hooks are not enabled yet.

---

## 8. Windows owner commands

PowerShell from the repo root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m pytest tests/ -q
.\.venv\Scripts\python -m src.main --headless --sim-days 6000
.\.venv\Scripts\python scripts\plot_porkchop.py metallic_belt logs\porkchop.png
.\.venv\Scripts\python -m src.main
```

Optional single-file packaging later:

```powershell
.\.venv\Scripts\pyinstaller --onefile --name AsteroidColonyProto -m src.main
```

---

## 9. GitHub delivery

The Arena branch is pushed to GitHub and the pull request was created from `arena/01a0418d-asteroid-colony-proto` into `main`. No credentials or tokens are stored in the repository.
