# Changelog

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
