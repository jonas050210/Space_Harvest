# ASTEROID-COLONY PROTO — PROJECT MD (everything in one file)

Master document for the multi-agent build of **"Asteroid-Colony Tycoon with
orbital supply chains"**. Read this FIRST, whatever else you do.

**Where the code is:** the canonical tree lives at
https://github.com/jonas050210/asteroid-colony-proto (public). The owner's
workspace intentionally holds ONLY these markdown files, so every agent
clones first. Prompts: `AGENT-2.md`, `AGENT-3.md`, and `AGENT-FINAL.md`
(the closer who tests/fixes/answers everything).

Owner's GitHub: `jonas050210` (repos `asteroid-colony`, `AI-Vision-Lab`).
Target PC: i7-12700F / 32 GB / RTX 4060 Ti 8 GB.

---

## 0. The one rule that blew the budget once — obey it

The workspace snapshot caps at **128 MB / 10 000 files**. The previous session
died because a virtualenv was created at `~/.venvs/...`, which IS snapshotted
(~300 MB, ~4 200 files). Therefore:

* The venv lives at `asteroid-colony-proto/.venv` (directory name `.venv` is
  snapshot-excluded). **Never** create `.venvs`, `venv/` at the home root, or
  install packages system-wide for this project.
* Never vendor binary model weights (AI-Vision-Lab's `data/models` is 30 MB —
  excluded from `vendor/ai-vision`).
* Keep generated images few (logs/ has 3, fine). If you add more, delete old.

Setup (Python 3.11-3.13, verified on 3.13):

```bash
cd asteroid-colony-proto
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q                 # 43 passed
.venv/bin/python -m src.main --headless --sim-days 3000
xvfb-run -a --server-args="-screen 0 1920x1200x24" .venv/bin/python scripts/capture_frame.py  # headless GL
```

(On a headless box `sudo apt-get install xvfb libgl1 libglx-mesa0` once;
Panda3D renders via GLX/llvmpipe. No display needed for `--headless`.)

---

## 1. Concept (chosen per owner's prompt)

Hybrid: extend the existing `asteroid-colony` repo (vendored unmodified in
`src/game/` and `vendor/asteroid-colony-upstream/`) with KSP-style orbital
mechanics. The five economic regions became **real heliocentric bodies**;
freighters fly **patched conics** with launch windows, delta-v budgets,
hold-at-target layovers and capture burns. Every delivery is booked into the
upstream economy via `game.logistics.store()`.

---

## 2. Directory map

```
asteroid-colony-proto/
├─ project.md            ← this file
├─ AGENT-2.md / AGENT-3.md  hand-off prompts for the remaining agents
├─ README.md             short pointer + quick start
├─ requirements.txt
├─ run-log.txt           evidence: tests, headless sim, capture and plot output
├─ FINAL-REPORT.md       final QA matrix, excerpts, known limits, owner commands
├─ src/
│  ├─ maths/             numpy-only astrodynamics (agent 1, done, 20 tests)
│  │   kepler.py         universal-variable Kepler propagation
│  │   elements.py       state <-> classical elements, anomaly conversions
│  │   transfers.py      Hohmann + Izzo(2015) universal Lambert (single rev)
│  │   windows.py        porkchop grid + secant refinement of moving-target intercept
│  ├─ simulation/
│  │   bodies.py         the six bodies as Keplerian orbits (keys match game.config.REGIONS)
│  │   orbital_sim.py    ships/missions/burns/refuel/dispatch (no graphics; 23 tests)
│  ├─ entities/          Freighter + OrbitLine (line-mesh) + au_to_scene
│  ├─ ui/orbital_hud.py  logistics HUD
│  ├─ utils/procedural.py  OBJ spheres + planet textures (numpy value noise)
│  ├─ config.py          units, budgets, warp steps, cache TTLs
│  └─ main.py            entry: windowed game + --headless (same update path)
├─ scripts/             capture_frame.py (xvfb render proof), plot_porkchop.py
├─ tests/               43 tests: math invariants + mission lifecycle + economy bridge
├─ assets/              procedural OBJs + PNGs
├─ logs/                screenshots, porkchop.png, run evidence
└─ vendor/              asteroid-colony-upstream (tests must stay green)
                        ai-vision (CODE ONLY, no weights)
```

---

## 3. Units & conventions (the part everyone gets wrong)

* Physics: lengths in **AU**, `MU_SUN = 4*pi^2`. Then a=1 AU has period 2*pi
  sim-seconds and the natural velocity unit is **AU/year**:
  `km_s = au_per_year * 4.7405` (`AU_PER_YEAR_TO_KM_S`). A previous bug used
  AU/sim-second and produced 1.4e8 km/s; regression-guarded by
  `test_au_per_year_converts_to_earth_orbital_speed`.
* Rendering: `SCENE_UNITS_PER_AU = 8`, mapping `(x, y, z)_AU -> Vec3(x, z, -y)`.
* Time: warp steps 1/6/24/90 sim-days per real second; headless passes days
  directly into `Game.update(dt_days)`.
* Window caching: plans cached with a **sim-time TTL** (365 d); `dispatch`
  re-solves fresh; a cached window whose departure has passed is RE-SOLVED
  with `epoch=now, min_departure_time=now`, never clamped.

---

## 4. What agent 1 delivered (done & verified)

Math: universal Kepler (energy drift ~8e-13 on 3000 fuzzed orbits incl. e=0.9
and hyperbolic), Lambert fuzz 4000 cases worst miss 1.6e-10 relative,
Hohmann vs published Earth→1.524 AU (2.94/2.65 km/s, 259 d), window refinement
miss ~1e-14 AU.
Sim: mission legs PENDING→OUTBOUND→capture/unload→WAITING (rides target until
return window opens)→INBOUND→dock; burns charged departure / arrival-match /
return-departure / docking-match; dispatch funds the full planned round trip;
refuel 22 m/s/day at colony billed to energy; cost-aware idle dispatch.
Render: sun+halo, line-mesh orbits (206 entities), trails, HUD; `capture_frame.py`
uses the real Ursina/Xvfb path when GL is available and a clearly labelled
Pillow fallback when a locked-down sandbox has no Xvfb/libGL.
Checks: `pytest tests/ -q` → **43 passed**; upstream `test_overall.py` →
**25 passed**; headless 6000 d → 18 round trips, 4 320 t; capture fallback →
700 frames, 34 runs, `logs/screenshot.png`; porkchop → `logs/porkchop.png`. 

---

## 5. Pitfall list — bugs already fixed; do not reintroduce

1. Kepler fp term is the RADIUS (chi²c2 + …+ r0(1-psi*c2)); an extra
   sqrt(|psi|c2) factor diverges.
2. Fold whole revolutions out before solving (f(chi) monotone per rev only).
3. Convergence test must be RELATIVE (chi ~1e5); absolute 1e-12 never fires.
4. `mean_to_true_anomaly`/`true_to_mean_anomaly` must normalise to [0, 2pi).
5. Stale outbound window clamped to "now" misses targets by ~40 km/s.
6. Return leg must be solved from the *arrival* epoch and bounded below by it
   (`min_departure_time=arrival`), else the crew gets a departure date in the
   past.
7. Charging `return_window.total_delta_v` at capture AND again at departure
   double-bills and strands ships; and `_complete_run` must charge the docking
   match (no free orbit insertion).
8. Round-trip cost scans are ~2 s uncached; TTL-cache plans and throttle the
   idle dispatch scan (30 d), or the game spends hours in Lambert grids.
9. Ursina 8.3 API: `app = Ursina(...); app.run()` (no `application.run()`),
   module-level `destroy(e)`, `look_at(Vec3)`, `color.rgba` takes 0-1 floats
   (ints clamp to white), `camera.ui` x spans ≈ ±0.8 at 16:10 (keep HUD >
   -0.78), orbits via `Mesh(vertices=..., mode="line")`, `base.screenshot()`
   returns the Filename it wrote, `ndarray.ptp()` removed in numpy 2.
10. Poly Haven download host 403s automated clients → procedural assets.

---

## 6. Gameplay & controls (folded from HOW_TO_PLAY)

TAB cycle target · ENTER dispatch · [ ] warp · O orbits · F follow · C overview
· scroll zoom · Esc quit. HUD shows window price (m/s both ways), fleet status/
ETA/delta-v, flight log, storage 615/1500 + lifetime tonnage. Run a ship dry
and it strands — intended failure mode, covered by tests.

## 7. Optional future work

The full phase-1 build is delivered. `AGENT-2.md` and `AGENT-3.md` remain as
optional expansion prompts: transfer-arc overlays, porkchop UI, save/load,
demand pricing, AI-Vision-Lab scan bonuses, M>0 Lambert, balance polish and
executable packaging.
