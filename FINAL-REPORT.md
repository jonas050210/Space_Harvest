# FINAL REPORT — Asteroid Colony Proto, Orbital Supply Chains

Date: 2026-08-27 UTC  
Branch: `arena/01a0418d-asteroid-colony-proto`

## Delivery status

The prototype is built and verified. It runs as:

```bash
.venv/bin/python -m src.main                    # windowed game
.venv/bin/python -m src.main --headless --sim-days 6000
```

A virtual environment was created only at `asteroid-colony-proto/.venv`, which is snapshot-excluded. No binary model weights were vendored; `vendor/ai-vision` contains code/docs/scripts only.

## Feature matrix

| Area | Status | Evidence |
| --- | --- | --- |
| Upstream colony vendored unmodified | Complete | `diff -qr --exclude='__pycache__' vendor/asteroid-colony-upstream/game src/game` is clean; upstream script reports 25/25. |
| Heliocentric bodies | Complete | `src/simulation/bodies.py` defines colony, inner_belt, metallic_belt, gas_giant_orbit/Aurelia+Nix, deep_belt, derelict_zone with requested AU/e/i values. |
| Units discipline | Complete | `MU_SUN = 4*pi^2`; velocities are AU/year converted with `AU_PER_YEAR_TO_KM_S = 4.7405`; regression test covers 1 AU/year -> 29.78 km/s. |
| Kepler propagation | Complete | Universal-variable solver with revolution folding, bracket repair and relative convergence; invariant tests cover elliptic/high-e/hyperbolic cases. |
| Elements conversion | Complete | State <-> elements and anomaly conversions normalized to `[0, 2pi)`, round-trip tested. |
| Transfers/windows | Complete | Hohmann sanity plus Izzo single-rev Lambert and moving-target porkchop/refinement with min departure bounds. |
| Mission simulation | Complete | PENDING -> OUTBOUND -> capture/unload -> WAITING -> INBOUND -> dock; exact event jumps; departure/capture/return/docking burns billed separately. |
| Economy bridge | Complete | `Colony.receive()` wraps `src.game.state.initial_state()` and `src.game.logistics.store()`, reporting overflow and adding research per tonne stored. |
| Fleet management | Complete | Full round-trip affordability checks, stale departure re-solve, cache TTL, idle scan throttle, refuelling from colony energy, dry-drift failure mode. |
| Rendering/HUD | Complete | Ursina scene with sun/halo, orbital line meshes, planets/freighters/trails; HUD has clock/warp, plan, fleet, log, controls, storage/lifetime tonnage. |
| Procedural assets | Complete | Generated OBJ/PNG assets in `assets/`, each under 1 MB; no external blobs. |
| Scripts | Complete | `scripts/capture_frame.py` and `scripts/plot_porkchop.py` write `logs/screenshot.png` and `logs/porkchop.png`. |
| Documentation | Complete | `README.md`, `project.md`, `PUSH-INSTRUCTIONS.md`, and this report. |

## Final validation results

All required checks were run and appended to `run-log.txt`.

### 1. Project tests

```text
===== Thu Aug 27 04:54:08 UTC 2026 pytest tests final =====
...........................................                              [100%]
43 passed in 8.05s
```

### 2. Upstream `asteroid-colony` tests

The upstream file is a script named `test_overall.py`, not a pytest module; running it directly is the correct invocation.

```text
===== Thu Aug 27 04:54:16 UTC 2026 upstream asteroid-colony test_overall.py final =====
=== Asteroid Colony Tests ===
...
=== Result: 25 passed, 0 failed ===
```

### 3. Headless 6000-day run

```text
===== Thu Aug 27 04:54:16 UTC 2026 headless sim 6000 days final =====
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

This satisfies `>10` completed runs and both ships remain solvent.

### 4. Screenshot capture

The sandbox could not install system GL/X packages because the apt mirror was unreachable, so `xvfb-run` was unavailable. The capture script now attempts the real Ursina/Xvfb path first and, only when GL is unavailable, writes a clearly labelled deterministic Pillow fallback screenshot driven through the same `Game.update()` simulation path.

```text
===== Thu Aug 27 04:53:23 UTC 2026 capture_frame fallback final =====
[capture] windowed GL capture unavailable; using Pillow fallback
[capture] wrote /home/user/asteroid-colony-proto/logs/screenshot.png (91782 bytes)
[capture] frames=700 shots=1 runs=34 delivered=8160t fallback=1
```

On an owner machine with Xvfb/libGL installed, run the requested command exactly:

```bash
xvfb-run -a --server-args="-screen 0 1920x1200x24" .venv/bin/python scripts/capture_frame.py
```

### 5. Porkchop plot

```text
===== Thu Aug 27 04:54:39 UTC 2026 plot porkchop final =====
wrote logs/porkchop.png
```

Output: `logs/porkchop.png`.

### 6. Prune / workspace cap

```text
===== Thu Aug 27 04:55:37 UTC 2026 workspace size / prune check =====
du excluding .venv: 6.1M
file count excluding .venv: 314
remaining project caches: 0
src/game diff vs upstream excluding caches:
```

The repository is far below the 128 MB / 10,000 file cap, and project caches were pruned.

## Known limits

* Lambert implementation is single-revolution only; multi-revolution branches remain future work.
* The real windowed screenshot path requires host GL/Xvfb packages (`xvfb`, `libgl1`, `libglx-mesa0`) on headless Linux. The Arena sandbox apt mirror was unreachable during final verification, so the fallback screenshot artifact was used here.
* Economy balancing is prototype-level: storage fills quickly, overflow is reported honestly, and research accrual is deliberately simple.
* AI-Vision-Lab is vendored as code-only; no model weights or data are included.

## Owner commands — Windows target PC (i7-12700F / RTX 4060 Ti)

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

Controls in-game: TAB target, ENTER dispatch, `[ ]` warp, O orbits, F follow, C overview, mouse wheel zoom, Esc quit.

## Linux headless commands

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m src.main --headless --sim-days 6000
sudo apt-get install -y xvfb libgl1 libglx-mesa0
xvfb-run -a --server-args="-screen 0 1920x1200x24" .venv/bin/python scripts/capture_frame.py
.venv/bin/python scripts/plot_porkchop.py metallic_belt logs/porkchop.png
```
