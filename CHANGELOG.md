# Changelog

## 1.6.2 — One-click launch; window-search and Steam fixes

### First-run / launch

- **Double-click to play.** New `Play.bat` (Windows) and `play.sh`
  (Linux/macOS) launchers create a private `.venv`, install dependencies
  into it once, and run the game. Nothing is installed system-wide; after
  the first run the game starts offline. `setup.py` itself also bootstraps
  dependencies on the default play path (it previously only did so for
  `--build`/`--test`), and reports a clear manual-install command instead
  of a raw `ModuleNotFoundError` traceback when it cannot.
- README leads with a no-download Quick Start and a `setup.py` command table.

### Fixes

- **Multi-revolution window search ranked the wrong cost.** The slow-arc
  (Izzo multi-rev) candidate scan scored trajectories by absolute
  heliocentric velocity instead of the burn relative to the departure and
  arrival bodies — contradicting the single-rev grid — so it refined onto
  non-optimal rendezvous and the cheap branch was never chosen. It now
  scores real delta-v and refines the best six candidates (the single-rev
  solver already refined six). The slow low-energy arc now correctly wins
  for the two highly eccentric targets where orbital mechanics says it
  should — Comet Vigil (~21% less outbound delta-v than the fast perihelion
  sprint, at the cost of a long transit) and Cinder Moon — while every
  coplanar belt body keeps its fast Hohmann-class window and Vagrant still
  demands depot barns.
- **Save version gate fell through.** A v2 (pre-1.5) save printed the
  refusal message and then loaded anyway; it now aborts the load.
- **Steam playtime was double-counted in windowed mode.** The per-frame
  `tick` accumulated playtime and `shutdown` then added the whole session
  wall-time again. `shutdown` now adds only the un-ticked remainder.
- **Headless playtime never persisted.** The self-test / CI path never
  called `SteamClient.shutdown`, so playtime was dropped; it now shuts down
  in a `finally`, writing `steam_stats.json`.

## 1.6.1 — HUD feed extracted; save version gate

### Safety

- **Save version gate.** `load_game` now checks the save payload's
  `version` field against `Game.SAVE_VERSION` (currently `3`). Newer
  saves refuse to load with an update-required message; older
  pre-1.5-format saves (v2) refuse instead of silently misloading and
  corrupting state. Written saves always stamp the current version.

### Housekeeping

- Extracted the HUD feed assembly out of `src/main.py` into
  `src/ui/hud_feed.py`. The god object shrank by ~180 lines; every
  HUD line-helper (`_crew_hud_line`, `_life_hud_line`, `_parts_hint_line`,
  etc.) and the `_ops_hud_data` dict builder now live next to the UI
  package they feed. Thin delegates on `Game` keep all existing call
  sites and tests working unchanged. Pure read-only — no behaviour
  change; deterministic baseline still matches.

## 1.6.0 — The Wide Sky

Three new fields, two new hulls, and the fixes that keep saves alive.

### New bodies

- **Sungrazer Field** — sun-skimming slag inside the colony's own orbit.
  Cheap windows, but ships riding a flare to or from it take 2.5x flare
  wear (`FLARE_EXPOSURE_BY_BODY`). Carries magnetite, thorite and — rare
  this close to home — helium-3.
- **Vagrant** — a planetesimal knocked 48 degrees out of the ecliptic.
  No hull in the fleet can round-trip it; build a barn at Vagrant first.
  The first body inclined enough that multi-revolution Lambert branches
  can genuinely compete on price. Platinum, xenonite, cobalt.
- **Boreas** — a cold ringed giant at 8.4 AU, past Night Well. Premium
  silver/gold/platinum freight for the deepest depot chains. Coursers
  can nearly round-trip it; nothing else should try without barns.

### New ship classes

- **Courser** (Q) — 36 km/s tank, 180 t hold, 11,500 cr. The far-system
  workhorse that makes Night Well and Boreas routine.
- **Argosy** (A) — 720 t hold, 19 km/s tank, 12,500 cr. A warehouse with
  an engine; moves a whole season of seedstock in one run.

### Presentation

- Every campaign body now ships a generated planet texture instead of a
  flat colour (Aurelia finally gets its bands — the banded texture existed
  but was never loaded).
- Fixed `python -m src.utils.procedural` (the generator entry point was
  unreachable: its `__main__` block sat above the functions it called).

### Save robustness

- Saves are written atomically (temp file + rename) and the previous
  version is kept as `<slot>.json.bak`.
- A corrupt or truncated save no longer crashes load: it falls back to
  the `.bak` or reports no readable save.
- Fixed the NEXT WINDOWS board printing `inf d` for unreachable targets
  (`days == days` now `math.isfinite`).

### Housekeeping

- v1.5.0 cleanup: removed the `src/game` / `src.operations` compat shims,
  `scripts/` redirect stubs, dead upstream-colony code and never-loaded
  generated assets (see git history).

## 1.5.0 — Steam readiness

Difficulty modes (Director / Tight / Ironman), victory conditions
(Endless / Charter / Legacy / Worldseed), graphics presets, achievements
bridge, PyInstaller packaging, procedural audio, crew roster, drone
swarms, station modules, multi-stop routing.
