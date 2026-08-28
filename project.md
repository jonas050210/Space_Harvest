# Space Harvest — Project

Master document for **Space Harvest** — orbital farming on real launch windows,
with patched-conic astrodynamics underneath. Architecture, setup, units, systems,
controls, QA, known limits and hand-off notes live here alongside `README.md`
and `STEAM.md`.

Repository: https://github.com/jonas050210/asteroid-colony-proto
Arena branch: `arena/01a0449e-asteroid-colony-proto`
Target PC: i7-12700F / 32 GB / RTX 4060 Ti 8 GB. Python 3.11–3.13, Ursina 8.3.
Product name: **Space Harvest** (v1.0.0). Executable: `SpaceHarvest`.

---

## Contents

1. Quick start
2. Architecture
3. Units and conventions
4. Systems reference (what to tune, where)
5. Concept and feature matrix
6. Gameplay and controls
7. Verification evidence
8. Known limits
9. Windows owner commands
10. Delivery status
11. Design history and parked ideas

---

## 1. Quick start

```bash
cd asteroid-colony-proto
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q          # 134 tests
.venv/bin/python -m src.main --headless --sim-days 6000   # self-test, ~90 s
.venv/bin/python -m src.main                  # play
```

Headless screenshot capture when GL/Xvfb packages are installed:

```bash
sudo apt-get install -y xvfb libgl1 libglx-mesa0
xvfb-run -a --server-args="-screen 0 1920x1200x24" .venv/bin/python scripts/capture_frame.py
```

Without GL, `scripts/capture_frame.py` falls back to a clearly labelled Pillow "key
art" render driven by the same `Game.update` path and the same committed textures.

---

## 2. Architecture

Product entry is **``setup.py``** only (play / shortcut / EXE). Package layout: ``src/ops`` (fleet), ``src/colony`` (economy bridge), ``src/config`` (knobs), sealed ``src/maths`` + ``src/simulation``, ``packaging/`` for PyInstaller. Shims: ``operations.py`` → ops, ``game/`` → colony.

## 2. Architecture

### 2.1 Layering rule (the founding constraint)

The game is built as strictly separated layers. **Nothing gameplay-related ever edits
`src/maths/` behaviour or `src/game/` (vendored upstream code).** Every feature was
added by subclassing, wrapping, or data — which is why the astrodynamics could be
re-verified bit-for-bit at any time during development.

```text
┌────────────────────────────────────────────────────────────────────┐
│ src/main.py            Game shell: loop, screens, credits, save,   │
│                        life support, contracts, firsts, science,   │
│                        windows board, toasts, input machine        │
├────────────────────────────────────────────────────────────────────┤
│ src/operations.py      OpsSimulation(OrbitalSimulation) SUBCLASS:  │
│                        ship classes, hull wear, crews, weather,    │
│                        perturbations, depots, refineries, parts,   │
│                        tech multipliers, incidents                 │
├──────────────────────────────┬─────────────────────────────────────┤
│ src/mining.py                │ src/market.py                       │
│ fingerprints, depletion      │ ore pricing, flooding, contracts,   │
│ ledgers, extraction planner  │ parts pricing, Contracts offers     │
├──────────────────────────────┴─────────────────────────────────────┤
│ src/simulation/orbital_sim.py  VERIFIED CORE (untouched):          │
│   OrbitalSimulation, Ship, Mission, Leg, Delivery, event stepping  │
│ src/simulation/bodies.py       VERIFIED DATA (untouched): BODIES   │
├────────────────────────────────────────────────────────────────────┤
│ src/maths/  VERIFIED (behaviour untouched): kepler, elements,      │
│   transfers (Izzo single-rev + additive multi-rev), windows        │
├────────────────────────────────────────────────────────────────────┤
│ src/game/  VENDORED upstream colony economy (never modified):      │
│   logistics.store() books every delivery, research per tonne,      │
│   savegame JSON slots reused for campaign saves + settings         │
└────────────────────────────────────────────────────────────────────┘

Presentation (separate, replaceable):
  src/entities/orbital_scene.py   3-D scene (Ursina)
  src/entities/ship.py            Freighter meshes, trails
  src/ui/orbital_hud.py           HUD panels + MenuOverlay screens
  src/utils/procedural.py         every texture/sound/asset generator
scripts/capture_frame.py           screenshot (GL or fallback key art)
scripts/plot_porkchop.py           delta-v porkchop plot
```

`src/main.py`'s `Game` composes `OpsSimulation` + `Colony` (upstream economy bridge) +
`Market`/`Contracts` + `credits`. The `--headless` path drives the identical
`Game.update(dt_days)` as the windowed path — that is what lets the whole game be
verified without a display.

### 2.2 Model–render separation

The simulation never imports graphics. `OrbitalScene.update(sim)` reads
`fleet_report()` and body positions each frame; quality presets, LOD decisions and
mesh merging are pure presentation concerns. A different renderer could consume the
same model layer unchanged.

### 2.3 Campaign bodies vs the module table

`OpsSimulation.__init__` copies the module body table (`self.bodies = dict(...)`).
Campaign-only bodies — **Comet Vigil** — and gravitational perturbations live in that
copy. The module-level `BODIES` (which the 43 core tests read) stays pristine. Ore
fingerprints for campaign bodies are registered via `mining.register_body_ores`;
campaign rarity spawns (thorite/aurellium) register at `mining` import time so
fingerprints are correct before any campaign exists.

### 2.4 Determinism

Fixed seeds everywhere (`OrbitalSimulation(seed)`, `Market(seed)`, ops RNG) plus one
hard rule learned the hard way: **anything fed into an RNG must be sorted** (set
iteration order is hash-randomised between processes — this bit the contract-offer
path once). Savegames store full RNG states (market demand, incident roll, weather),
so replaying a save reproduces its future exactly. The headless self-test reproduces
its own numbers exactly for a given code version.

### 2.5 Savegame format (v2 JSON, via upstream `savegame` slots)

`F5` writes `saves/quick.json` containing: `credits`, `auto_repair`, `market`
(prices state + RNG), `contracts` (active/pending/reputation), `firsts` (milestone
latches), `techs` (science unlocks), `colony` (upstream state incl. life-support
stocks), and `sim` — which serialises every ship (state vector, class, hull, parts,
crew), every mission (including the planned return window with its `revs`), pending
deliveries, depletion ledgers, vein reservations, depots, refineries, tech multipliers,
weather state, perturbation timer, and the ops RNG. Settings persist separately in
`saves/_settings.json` (quality preset, audio, camera glide).

### 2.6 The Only Rule

No unnecessary files. Across five feature sessions the repo grew by exactly **four**
new modules (`mining.py`, `market.py`, `operations.py`, plus one test file); every
subsequent feature — depots, refineries, crews, weather, contracts, science, menus,
audio, the comet — was folded into those or into existing files.

---

## 3. Units and conventions

* Physics length unit: **AU**. `MU_SUN = 4*pi^2`, so a = 1 AU has period `2*pi`
  sim-seconds.
* Natural velocity unit: **AU/year**; `AU_PER_YEAR_TO_KM_S = 4.7405`
  (1 AU/year ≈ 29.78 km/s). Never treat AU/sim-second as km/s.
* **Delta-v is billed in m/s** (ships carry ~21–30 km/s class budgets). Internal
  window solutions are AU/year; `sim.delta_v_km_s()` converts at the boundary.
* Render scale: `SCENE_UNITS_PER_AU = 8`; coordinate mapping exists in exactly one
  place: `(x, y, z)_AU -> Vec3(x, z, -y)`.
* Time warp steps: 1 / 6 / 24 / 90 sim-days per real second.
* Crew rates are per crew-member per sim-day in abstract life-support units; ore is
  tonnes; depot tanks store delta-v in m/s (the same currency ships burn).
* Window caches are sim-time based; expired or passed windows are re-solved from
  `now`, never clamped.
* Tech effects reach the sim only as generic multipliers in `sim.tech_mults`
  (`fatigue`, `depot_generation`, `refinery`) plus a parts-price discount in the game
  layer — the sim never learns tech names.

---

## 4. Systems reference (where to tune what)

All gameplay knobs are data in **`src/config.py`** — no code changes needed for
balance work:

| Knob block | What it controls |
| --- | --- |
| `SHIP_CLASSES` | Scout / Freighter / Refinery / Hauler: hold, delta-v budget, price, refuel rate, wear factor, mine bonus. |
| `HULL_*` | Wear per m/s, critical threshold (20%), repair rate and cost. |
| `MINING_*` | Ore list, per-ore vein sizes, drill yield/wear, incident chances, recovery taus (`_BY_ORE`: ice 900 d, metals 2,400 d), extra spawns (thorite/aurellium map). |
| `MARKET_*` | Base prices, absorption (flooding speed), flood half-life, seasonal amplitudes/periods, noise, floor, history. |
| `PARTS_CATALOG` | Drop Tanks, Deep Drill, Crew Quarters, Depot Drone Bay, Navigation Suite: price, effect, per-ship/depot caps, aurellium cost. |
| `TECHS` | The four research unlocks and their effects. |
| `CONTRACT_*`, `REPUTATION_PRICE_BONUS` | Offer cadence, size, deadline window, reputation swings. |
| `CREW_*` | Roster template, fatigue/morale rates and floors, hire costs, role effects (pilot/engineer/botanist/navsuite). |
| `LIFE_*` | Metabolism, recycling fraction, ice refinery, solar budget, ice reserve. |
| `FLARE_*`, `DEBRIS_*`, `PERTURB_*` | Hazard cadence and severity. |
| `DEPOT_*`, `REFINERY_*` | Build costs, capacities, generation, arrival smelting batches. |
| `COMET_ELEMENTS`, `FIRSTS` | The comet's orbit; the 19 milestones and their rewards. |
| `PLANNING_*` | Multi-revolution gating. |
| `QUALITY_PRESETS` | What low/medium/high toggles. |

---

## 5. Concept and feature matrix

Upstream `asteroid-colony` economic regions are modelled as real heliocentric bodies.
Freighters fly patched-conic transfers with launch windows, delta-v budgets, layovers,
capture burns and docking burns. Deliveries are booked into the vendored upstream
economy (`src.game.logistics.store()`) and grant research per tonne stored — research
that now buys technologies.

| Area | Status |
| --- | --- |
| Upstream colony game | Vendored unmodified in `src/game/` and `vendor/asteroid-colony-upstream/`; upstream 25-test script passes. |
| Heliocentric bodies | Colony (1.20 AU), inner belt, metallic belt, Aurelia orbit (2.80 AU) with moon Nix, deep belt, derelict zone — plus campaign-only **Comet Vigil** (a=4.45, e=0.80). |
| Astrodynamics | Numpy-only universal-variable Kepler, elements conversion, Hohmann checks, single-rev Izzo Lambert plus additive multi-revolution branches (dense TOF-curve scan + continuous bisection; arrivals ~1e-13 AU), porkchop grids, secant refinement to true rendezvous. Core behaviour untouched; verified by 37 maths/simulation tests. |
| Mission simulation | PENDING → OUTBOUND → capture/unload → WAITING → INBOUND → dock; exact event-time jumps; separate departure/arrival/docking billing. |
| Economy bridge | Deliveries stored through upstream logistics; overflow reported; research per tonne; ore sells on the Earth market; techs bought with the research. |
| Fleet operations | Round-trip affordability (fresh pricing on dispatch), stale-window re-solve, cache TTL, idle-scan throttle, per-class refuel from colony energy, honest dry-drift failure, depot-assisted dispatch (delta-v loan repaid at docking). |
| Mining & depletion | Deterministic per-body fingerprints (CRC-seeded), exponential depletion ledgers, per-ore recovery taus, vein reservations for concurrent runs, scrape vs core drilling, drone-bay extraction. |
| Earth market | Seasonal sine + mean-reverting noise per ore, per-resource absorption flooding, exponential recovery, marginal-price sale execution, parts pricing with count escalation, trend arrows. |
| Rare ores | Thorite (deep belt, derelict hull, comet slag) and aurellium (**comet only**, 480 cr/t base, tiny absorption) — the deep-game economy. |
| Fleet classes & hull | Data-driven classes with distinct silhouettes; per-burn wear; low-hull dispatch interlock; credit-billed auto-repair; seeded incidents (crew-scaled). |
| Crew & morale | Named rosters (pilot/miners/engineer, +hires); fatigue by leg, recovery docked (quarters boost); morale from captures/payday, drained by overwork/cabin fever/boredom (floored)/flares/shortages; effects on yield and incident chance; hire/fire. |
| Science unlocks | Four one-shot technologies bought with research points, applied as generic sim multipliers; persist with the campaign. |
| Firsts & goals | 19 latched one-shot milestones (captures per body incl. the comet, stations, drones, full-hold returns, tonnage, treasury, rare-ore shipments) paying credits + research; the next three show live as GOALS. |
| Refuel depots | Player ISRU stations: delta-v tank + per-level generation; ships top up while waiting and draw the ride home at docking. |
| Refinery stations | Smelt a run's payload at docking (components from iron+silver, electronics from gold) and keep smelting drone-loaded ore; refined stock outsells raw ore. |
| Parts market | Seasonal, count-escalating Earth prices; T/Y/U/I refit ships, P installs drone bays. |
| Comet Vigil | Campaign-only eccentric body: rare expensive windows (depot runs shine), primordial ores incl. aurellium, anti-sunward tail with inverse-square brightness, on the windows board. |
| Contracts & reputation | Faction offers (B/V, or autopilot accepts fillable); rewards + standing; standing moves sale prices ±6%. |
| Life support | O2/food/water loop (ice refinery → electrolysis → hydroponics, ISS-style water recycling) on a solar energy budget; shortages drain morale; the dispatcher's ice premium protects the pantry. |
| Space weather | Flare cycles + debris seasons; wear only in flight; HUD + audio alerts. |
| Gravitational perturbations | Every 500–950 days one belt orbit shifts in the campaign's own table; caches drop, fleet re-plans. |
| Jump-to-event | J races the warp to the next window/ETA/deadline and restores warp on arrival; log ticker. |
| Procedural audio | Hum pitched by power load (ducks under alerts) + flare/hull/shortage/chime/window-click/build tones; all synthesised WAVs; N mutes; graceful headless disable. |
| Rendering | Starfield skybox dome, layered sun corona, unlit textured planets with billboard name tags, Aurelia's double ring, single-mesh asteroid belt (one draw call), per-class ship silhouettes with tints + engine flares, fading trails, smoothed chase camera, click-picking, pulsing reticle, quality presets. |
| Game shell | Title menu (new/continue/load/settings/how-to/quit), pause with quit-to-title, persistent settings, 3-page how-to-play, toast stack, launch-window GO moment, NEXT WINDOWS board, GOALS list. |
| Save / load | Full campaign JSON (fleets in flight, markets, RNG, crews, weather, stations, techs, milestones) via upstream slots + separate settings slot. |
| HUD | Clock/warp, transfer plan with live assay, fleet rows (status, m/s, dv bar, ETA, hull, part tags), market prices + trends, treasury + Firsts counter, crew line, weather, contracts + offers, depots/stations line, life support, NEXT WINDOWS, GOALS, toasts, tutorial checklist. |
| Assets | 100% procedural (numpy + Pillow + wave); committed generated textures total ~350 KB; no binary blobs. |
| Tooling | 134-test suite, screenshot capture with key-art fallback, porkchop plot, run-log. |

---

## 6. Gameplay and controls

### Title menu
W/S + ENTER navigate: **NEW GAME / CONTINUE / LOAD LAST SAVE / SETTINGS / HOW TO
PLAY / QUIT**. ESC on the menu quits. Settings (quality / audio / camera glide)
apply and persist instantly.

### In play

| Key | Action |
| --- | --- |
| TAB / left-click | Cycle target / pick the body under the cursor |
| ENTER | Dispatch an idle ship to the target (GO banner + chime announce the window) |
| `[` / `]` | Warp down / up (1–90 d/s) |
| S | Sell all marketable ore (ice reserve held back) |
| X | Toggle surface scraping / core drilling |
| M | Toggle automatic hull maintenance |
| R / E | Build or upgrade a **refuel depot** / build a **refinery** at the target |
| T / Y / U | Buy Drop Tanks / Deep Drill / Crew Quarters for a docked ship |
| I / P | Install Navigation Suite (costs aurellium) / a depot drone bay |
| L | Commission the next technology with research points |
| B / V | Accept / decline the oldest Earth offer |
| G / H / Z | Hire miner / dismiss unhappiest crew / hire colony botanist |
| 1–4 | Commission scout / freighter / refinery-ship / hauler |
| J | Jump the warp to the next upcoming event |
| K / N | Cycle quality preset / mute audio |
| O / F / C | Toggle orbits / follow ships / overview camera |
| F5 / F9 | Quick-save / quick-load |
| ESC / Q | Pause menu (resume/save/load/settings/quit-to-title) / quit |
| Mouse wheel | Zoom |

### The intended loop

Wait for geometry (NEXT WINDOWS board) → dispatch → mine each body's fingerprint
(HUD assay shows shares and remaining vein) → depot-stop on deep runs → refinery
smelts the payload → home → sell without flooding the market → pay crews and repairs
→ reinvest (ships, parts, stations, science) → chase thorite, then the comet's
aurellium → Firsts track mastery (GOALS shows the next three).

Class lore: refinery ships mine 30% more per run and wear slowest; haulers lift 520 t
but lack the reach for deep targets (until depots); scouts are the long-range
specialists — the only class that flies Comet Vigil round-trip on one tank.

Failure modes are honest: dry ships drift with a log entry; hulls below 20% refuse
dispatch; exhausted crews refuse to fly; a broke colony lets maintenance lapse and
hulls decay; mined-out veins yield thin holds for years; an empty pantry grinds every
crew's morale down.

---

## 7. Verification evidence

Full evidence lives in `run-log.txt` (one appended section per work session).

### Current state

```text
project tests : 134 passed  (48 core: maths + simulation; 86: economy-ops)
upstream tests: 25 passed, 0 failed
windowed path : exercised headlessly via Ursina(window_type='none')
workspace     : ~6.5 MB / ~357 files excluding .venv and .git
```

### Astrodynamics invariance (the standing guarantee)

1. `git diff e2543e3 HEAD -- src/maths src/simulation` is **empty** — the orbital
   core is byte-identical to the verified delivery (checked every session, recorded
   in `run-log.txt`).
2. The base `OrbitalSimulation`, driven with the pre-operations policy, reproduces
   the recorded baseline **bit-for-bit: 18 runs / 4,320 t / 112,790 m/s**.
3. 48 of the 134 tests pin the core: Kepler propagation, energy/angular-momentum
   conservation, Hohmann references, Lambert arrival checks, multi-rev branch
   properties (`M*P < tof < (M+1)*P`, arrivals ~1e-13 AU), window/refinement
   behaviour, and full round trips per body.

### Full-economy self-test (latest session)

The 6,000-day self-test sells every 90 days, grows the fleet, builds the deep-belt
depot (to level 2), an inner-belt refinery, and commissions every technology:

```text
runs completed : 56        mass delivered : 8,382 t
deliveries     : 56        research       : 2,001 RP
ore mined      : 9,626 t   incidents      : 4
treasury       : 224,014 cr
Firsts fired   : 15/19 (incl. comet capture, thorite shipment, refinery)
refined        : 985 t components delivered
```

### Artifacts

`logs/screenshot.png` — with GL/Xvfb: a real frame; without: the committed key-art
fallback built from the actual game textures, showing the comet, windows board, HUD
panels and toasts. `logs/porkchop.png` — departure×TOF delta-v plot.

---

## 8. Known limits

* Multi-revolution transfers exist but the gate (≥15% saving) essentially never
  opens: Hohmann-class single-rev windows dominate this near-coplanar network, as
  orbital mechanics predicts. The branches cost nothing idle and are ready for
  strongly inclined future targets (tested via forced adoption).
* The economy is deterministic per version; replaying a save repeats its "luck"
  (RNG state is saved). Intended for testing.
* Under the autopilot roughly a third of Earth offers still expire (two concurrent
  orders vs 500+ day cycles). A human timing sales does better — the autopilot is a
  demo, not an optimiser.
* The life-support ice premium keeps the fleet ice-heavy while the pantry is thin;
  selling surplus ice down to the reserve eases it.
* A fleet-wide refuel spike can transiently stall the electrolysers; buffers refill
  afterwards.
* Procedural audio needs a sound device; headless boots disable it gracefully. Audio
  has not yet been heard on real hardware.
* Windowed capture on headless Linux needs host GL/Xvfb (the sandbox's apt mirror is
  unreachable; the committed screenshot is the labelled key-art fallback).
* `AI-Vision-Lab` ships as code only; scanner hooks are not enabled.

---

## 9. Windows owner commands

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m pytest tests/ -q
.\.venv\Scripts\python -m src.main --headless --sim-days 6000
.\.venv\Scripts\python scripts\plot_porkchop.py metallic_belt logs\porkchop.png
.\.venv\Scripts\python -m src.main
```

Optional single-file packaging:

```powershell
.\.venv\Scripts\pyinstaller --onefile --name AsteroidColonyProto -m src.main
```

First-play checklist: play the title menu, click planets, chase a GO banner, listen
to the audio (never verified in-sandbox), try K quality presets, and note anything
that feels off — all balance lives in `src/config.py`.

---

## 10. Delivery status

* Branch `arena/01a041a3-asteroid-colony-proto` is pushed to GitHub through commit
  `1f709d1` ("Docs: science unlocks and Navigation Suite rows in project.md") and
  every later session commit. No credentials or tokens are stored in the repository.
* `src/game/` and `src/maths/`, `src/simulation/` remain byte-identical to the
  verified delivery `e2543e3` (empty diff, re-checked this session).
* Working tree clean at last verification; every session ended with the full test
  battery green before pushing.

### 10.1 Steam-ready pass (v0.9.0-steam)

CEO session shipped a Steam surface **without touching the orbital core**:

* Graphics presets **low / medium / high / ultra** (belt density, trails, flares,
  corona, ship LOD, MSAA, orbit alpha, bloom/particles flags).
* Full settings menu: resolution, fullscreen, VSync, FOV, UI scale, master volume,
  confirm-dispatch, body dossier, difficulty, victory mode.
* Campaign: Director / Tight Margins / Ironman; Endless / Charter / Legacy victory;
  achievement tracker + Steam soft-bridge; year report; dispatch confirm sheet.
* Packaging: `scripts/build_steam.py`, `STEAM.md`, `steam/*.vdf`.
* Tests: 144 passed (10 new campaign/Steam cases). See `STEAM.md`.

---

## 11. Design history and parked ideas

Sessions, in order: (1) verified orbital prototype delivery; (2) operations layer —
mining, market, fleet classes, hull; (3) economy wiring — credits, sell, buy, HUD,
save/load; (4) crews, space weather; (5) contracts, life support, value dispatch,
tutorial, procedural audio; (6) specialisations, negotiation, jump-to-event,
perturbations; (7) multi-revolution Lambert + determinism lock; (8) Steam-polish
pass — textures, scene, depots, menus, GO moment, toasts, picking, camera; (9) the
shelf — windows board, reticle, merged belt, quality presets, Comet Vigil, parts
market, upgrades, drone bays, full menu; (10) rare ores, refineries, Firsts;
(11) science unlocks, Navigation Suite, GOALS log.

Parked ideas (vetted against the architecture, none require touching the core):
trojan asteroid cluster at Aurelia's L4; volcanic moon of Aurelia (hazard-rich
platinum); a terraforming-candidate "planet score" endgame consuming ice; a derelict
generation-ship encounter; ship LOD imposters; contract negotiation UI panels;
gamepad support; localisation (the upstream game already has an i18n module).
