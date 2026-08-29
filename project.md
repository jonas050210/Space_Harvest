# Space Harvest — Project

Orbital farming on real launch windows, with patched-conic astrodynamics
underneath. Product name **Space Harvest** v1.6.1. Executable: `SpaceHarvest`.

Repository: https://github.com/jonas050210/Space_Harvest

Target PC: i7-12700F / 32 GB / RTX 4060 Ti 8 GB. Python 3.11–3.13, Ursina 8.3.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/ruff check .                        # lint gate (also in CI)
.venv/bin/python -m pytest tests/ -q -m "not slow"   # fast loop (~2 min)
.venv/bin/python -m pytest tests/ -q          # full suite (CI runs this)
.venv/bin/python -m src.main --headless --sim-days 900
.venv/bin/python setup.py
```

CI (`.github/workflows/ci.yml`) runs ruff, the full suite, a 900-day
headless smoke and a rendering smoke with the screenshot as an artifact on
every push.

## Architecture

Nothing gameplay-related edits `src/maths/` or `src/simulation/` behaviour.

```text
src/main.py              Game shell: loop, screens, save, life support, input
src/app/controls.py      Single source of truth for play keys + how-to
src/app/audio.py         Procedural mixer
src/ops/simulation.py    OpsSimulation(OrbitalSimulation): fleet, hull, crews,
                         weather, depots, refineries, swarms, stations
src/mining.py  market.py  routes.py  campaign.py
src/colony/              Storage, JSON slots, research helper
src/maths/  simulation/  SEALED orbital core
src/entities/  ui/       Presentation
```

`Game.update(dt_days)` is identical headless and windowed. Live play does **not**
auto-dispatch; the headless self-test still does.

Saves: `src.colony.savegame` writes into `steam_bridge.cloud_root()`
(`./saves` in dev). Settings slot `_settings.json` is not a campaign save.

## Units

* Length: AU. `MU_SUN = 4*pi^2`. Velocity: AU/year; convert with `AU_PER_YEAR_TO_KM_S`.
* Delta-v billed in m/s. Render scale: `SCENE_UNITS_PER_AU = 8`.
* Warp: 1 / 6 / 24 / 90 sim-days per real second.

Balance knobs live in `src/config/__init__.py`.

## Known limits

* Multi-revolution Lambert exists and Vagrant (i = 48 deg) is the first
  body inclined enough for its branches to compete on price.
* Economy is deterministic per version (RNG state is saved).
* Quality flags `bloom` / `shadows` / `particles` / `star_twinkle` are reserved; Ultra is denser belts, trails, flares, MSAA.
* Steamworks is a soft-bridge until `STEAM_APP_ID` is set.

## Parked

Gamepad; localisation; contract negotiation panels; ship LOD imposters.
Campaign bodies are data in `config.CAMPAIGN_BODIES` (installed per-campaign
by the ops layer); add new ores only with market + mining + HUD in one pass.
