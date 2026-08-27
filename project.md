# Asteroid-Colony Proto — Project

Master document for **Asteroid-Colony Proto: Orbital Supply Chains**. This file intentionally contains setup, architecture, controls, QA evidence, known limits, and owner hand-off notes so the repo only needs this document plus `README.md`.

Repository: https://github.com/jonas050210/asteroid-colony-proto  
Branch used by Arena: `arena/01a041a3-asteroid-colony-proto`  
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
* Savegames are runtime artifacts in `saves/` (gitignored), written through the vendored upstream `savegame` slots.
* Generated artifacts are intentionally small. Final workspace excluding `.venv`/`.git`: about 4.8 MB and 334 files.

---

## 3. Concept and feature matrix

The upstream `asteroid-colony` economic regions are modelled as real heliocentric bodies. Freighters fly patched-conic transfers with launch windows, delta-v budgets, target layovers, capture burns, return windows, and docking burns. Completed deliveries are booked into the vendored upstream economy using `src.game.logistics.store()` and grant research per tonne stored.

| Area | Status |
| --- | --- |
| Upstream colony game | Vendored unmodified in `src/game/` and `vendor/asteroid-colony-upstream/`; upstream 25-test script passes. |
| Heliocentric bodies | Colony, inner belt, metallic belt, Aurelia/gas giant orbit with moon Nix, deep belt, and derelict zone with requested AU/e/i values. |
| Astrodynamics | Numpy-only universal-variable Kepler, elements conversion, Hohmann sanity checks, single-rev Izzo Lambert, porkchop windows and secant refinement. Byte-identical to the verified core; `OpsSimulation` extends it by subclassing, never by editing. |
| Mission simulation | PENDING → OUTBOUND → capture/unload → WAITING → INBOUND → dock, with exact event jumps and separate burn billing. |
| Economy bridge | Cargo stored through upstream logistics; overflow is reported; research points accrue per stored tonne. |
| Fleet operations | Full round-trip affordability, stale-window re-solve, plan-cache TTL, idle scan throttle, refuel from colony energy, honest dry-drift failure mode. |
| Mining & depletion | Deterministic per-body ore fingerprints; exponential depletion ledgers with slow multi-year recovery; per-vein reservations for concurrent runs; surface scraping vs core drilling (hold-capped yield, hull wear, incident risk). |
| Earth market | Dynamic prices (seasonal sine + mean-reverting noise), per-resource absorption so big sales flood their own price, exponential flood recovery, trend arrows and treasury sparkline in the HUD. |
| Fleet classes & hull | Data-driven scout/freighter/refinery/hauler (hold, delta-v budget, refuel rate, wear factor, price); per-burn hull wear; low-hull dispatch interlock; credit-billed auto-repair; seeded mining incidents. |
| Crew & morale | Named 4-seat rosters per ship (hire/fire with `G`/`H`/`Z`); fatigue accrues in flight and layovers, recovers docked; morale reacts to captures, payday, overwork, cabin fever, boredom (floored) and shortages; tired crews refuse dispatch, cause incidents and mine less. Pilots refund part of every burn, engineers speed repairs, botanists cut hydroponics water use. |
| Space weather | Deterministic solar-flare cycles (quiet -> warning -> flare) and periodic debris seasons; per-day hull wear only for ships in flight; HUD + audio alerts. |
| Earth contracts | Faction orders posted as offers (`B` accept / `V` decline, or the autopilot accepts fillable ones); completion pays credits + reputation, expiry costs it; standing swings sale prices by up to 6%. |
| Life support | Oxygen/food/water loop over the whole crew: ice refinery, electrolysis, hydroponics and ISS-style water recycling on a solar-fed energy budget; shortages drain morale; the dispatcher outbids the market for ice when the pantry runs low. |
| Procedural audio | Ambient hum pitched by colony power load and four alert tones (flare, hull, shortage, payday chime), synthesised to WAV at startup - no binary assets. `N` mutes; the hum ducks under alerts. |
| Gravitational perturbations | Every 500-950 days a passing body shifts one belt orbit slightly; the campaign's own body table changes, window caches drop and the fleet re-plans; the verified module constants and tests are untouched. |
| Jump-to-event | `J` cycles upcoming moments (window openings, ETAs, flare warnings, order deadlines) and races the warp to them, restoring the old warp on arrival; a bottom ticker streams the latest log entry. |
| Save / load | F5/F9 quick-save of the full game state (ships in flight, missions, windows, ledgers, market RNG, colony state, crews, weather, contracts) as JSON via the upstream savegame slots. |
| Rendering | Ursina sun/halo, line-mesh orbits, bodies, freighters (new commissions appear automatically), fading trails, camera presets/follow. |
| HUD | Clock/warp, selected target, transfer plan with live assay, fleet status with hull, ETA, delta-v, flight log, Earth-market panel, fleet-ops panel, storage and lifetime tonnage. |
| Assets | Procedural OBJ/PNG only; no external binary blobs. |
| Tooling | Test suite (65 tests), screenshot capture, porkchop plot script, run log. |

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
* S: sell all marketable ore in colony storage at current market prices.
* X: toggle mining policy between surface scraping and core drilling.
* M: toggle automatic hull maintenance for docked ships.
* 1 / 2 / 3 / 4: commission a scout / freighter / refinery / hauler (costs credits).
* B / V: accept / decline the oldest Earth offer; G hires a miner, H dismisses the unhappiest crew member, Z hires a colony botanist.
* J: jump the warp to the next upcoming event; N: mute audio.
* F5 / F9: quick-save / quick-load the full game state.
* Mouse wheel: zoom.
* Esc: quit.

The intended loop: watch launch windows, dispatch solvent ships, mine each
body's ore fingerprint (the HUD assay shows shares and how much vein is left),
haul it home, sell it on the Earth market without flooding it, repair worn
hulls, and reinvest profits in a bigger fleet. Refinery ships mine 30% more
per run and wear slower; haulers lift 520 t but lack the reach for the
derelict zone; scouts are cheap long-range probes of new fields.

Failure modes are honest and data-driven: ships that cannot afford a burn are
left drifting with a log entry; hulls below 20% refuse dispatch until
repaired; exhausted crews refuse to fly; a broke colony lets its fleet decay;
mined-out veins yield thin holds until the fields recover (metals tau about
2,400 days, ice 900); an empty pantry grinds every crew's morale down.

The flight-orientation checklist (bottom of the screen) walks a new director
through dispatch, selling, drilling, commissioning and saving.

---

## 6. Verification log excerpts

Full output is in `run-log.txt`.

### Project tests

```text
.................................                                  [100%]
65 passed in ~45 s
```

43 pin the astrodynamics core (unchanged), 22 cover the colony-operations layer: fingerprints, depletion, drilling, flooding markets, hull wear, incidents, fleet classes, savegame round trips and the mine→ship→sell→buy vertical slice through the real `Game` loop.

### Upstream `asteroid-colony` tests

`vendor/asteroid-colony-upstream/test_overall.py` is a script-style test file and should be run directly, not collected as pytest fixtures.

```text
=== Asteroid Colony Tests ===
...
=== Result: 25 passed, 0 failed ===
```

### Astrodynamics invariance

Three proofs, recorded in `run-log.txt`:

1. `git diff e2543e3 HEAD -- src/maths src/simulation` is **empty** — the
   orbital core is byte-identical to the verified delivery.
2. The current tree's base `OrbitalSimulation`, driven with the pre-operations
   main-loop policy (refuel rate pinned to the old 22 m/s/day, scan-on-idle
   redispatch), reproduces the recorded baseline **bit-for-bit: 18 runs,
   4,320 t, 112,790 m/s**.
3. The e2543e3 tree itself, replayed in a scratch copy, produces the same
   18 / 4,320 t / 112,790 m/s on this machine today.

Mass delivered by the *economy* runs differs from the baseline (11,934 t over
84 runs in the full-economy self-test) because ships now fly richer targets,
depletion thins old veins, and incidents occasionally bite — that is the new
layer working, not drift.

### Headless 6000-day simulation (full economy)

The self-test now plays the whole loop: it sells ore every 90 days and
reinvests profits into new ship classes while the treasury stays cushioned.

```text
[headless] 24000 frames over 6,000 sim-days
  Kestrel waiting  Inner Belt Field       11,832 m/s left   hull  92.9%
  Petrel  parked   Colony Hub             23,059 m/s left   hull 100.0%
  Harrier inbound  Deep Belt Outpost      11,614 m/s left   hull  74.2%
  ...
  runs completed : 84
  mass delivered : 11,934 t
  deliveries into colony economy: 84
  colony storage : {'used': 364.3, 'capacity': 1500, 'delivered': 11,832.8}
  research points: 2,958.2
  ore mined      : 11,934 t   incidents: 0
  treasury       : 393,585 cr
destination mix: Aurelia 18, Metallic Belt Field 10, Deep Belt Outpost 6
fleet: Kestrel/Petrel/Osprey (freighter), Harrier (scout), Falcon (refinery), Condor (hauler)
```

### Capture and porkchop artifacts

```text
[capture] wrote /home/user/asteroid-colony-proto/logs/screenshot.png (80941 bytes)
[capture] frames=700 shots=1 runs=8 delivered=1434t fallback=1
wrote logs/porkchop.png
```

The windowed Ursina path (scene construction, HUD panels, buying a ship
mid-game so its mesh appears, quick-save/quick-load with mesh pruning) is
exercised with `Ursina(window_type='none')` headless boots.

### Prune / cap check

```text
du excluding .venv and .git: 4.8M
file count excluding .venv and .git: 334
remaining project caches: 0
src/game diff vs upstream excluding caches: (empty — vendored code untouched)
```

---

## 7. Known limits

* Lambert is single-revolution only; multi-revolution branches are future work.
* Auto-dispatch waits for a near-full tank and the life-support premium keeps the fleet ice-heavy whenever the pantry is thin; a director who wants metal runs should sell surplus ice down to the reserve first (the premium eases once the buffer grows).
* Roughly a third to half of Earth orders still expire unfilled under the autopilot; deadlines are matched to mission cycles but two concurrent orders can still outrun six ships.
* Colony energy is now ticked (solar array in `LIFE_SOLAR_ENERGY_PER_DAY`), but a fleet-wide refuel spike can still transiently stall the electrolysers; the life-support buffers refill afterwards.
* The savegame stores full RNG state (market, incidents, weather); replaying a save is deterministic, which is intended for testing but means saved "luck" repeats.
* Procedural audio needs a sound device; headless boots disable it gracefully.
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
