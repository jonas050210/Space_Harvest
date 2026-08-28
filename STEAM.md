# Steam readiness — Space Harvest

Version **1.1.0**. Ship PC: **i7-12700F / 32 GB DDR4 / RTX 4060 Ti 8 GB**.

**Space Harvest** = orbital farming on real launch windows.

## What ships

| Area | Status |
| --- | --- |
| Name / branding | Space Harvest everywhere (window, menus, depot, docs) |
| Graphics | Low / Medium / High / Ultra |
| Display | Resolution, fullscreen, VSync, FOV, UI scale, volume |
| Campaign | Director / Tight / Ironman · Endless / Charter / Legacy |
| Achievements | 19 Firsts + secrets → `saves/achievements_progress.json` |
| UX | Dispatch confirm, body dossier, year report (F1) |
| Package | `scripts/build_steam.py` → `dist/SpaceHarvest/` |

## Build (Windows 11)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m pytest tests\ -q
.\.venv\Scripts\python scripts\build_steam.py
```

Linux:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_steam.py
```

Before store launch: set `STEAM_APP_ID` in `src/config.py`, wire `steam/achievements.vdf` in the partner portal, mount Steam Cloud on `saves/*.json`.

## Verification

```text
pytest tests/ -q
python -m src.main --headless --sim-days 900
```
