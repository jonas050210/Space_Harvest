# Steam readiness — Space Harvest

Version **1.5.0**. Ship PC: **i7-12700F / 32 GB DDR4 / RTX 4060 Ti 8 GB**.

**Space Harvest** = orbital farming on real launch windows.

## What ships

| Area | Status |
| --- | --- |
| Name / branding | Space Harvest everywhere (window, menus, depot, docs) |
| Graphics | Low / Medium / High / Ultra (belt, trails, flares, MSAA) |
| Display | Resolution, fullscreen, VSync, FOV, UI scale, volume |
| Campaign | Director / Tight / Ironman · Endless / Charter / Legacy |
| Achievements | Firsts + secrets → `saves/achievements_progress.json` |
| UX | Mouse command bar, ship picker, dispatch confirm, body dossier, year report (F1) |
| Package | `python setup.py --build` → `dist/SpaceHarvest/` |

Steamworks itself is still a soft-bridge (`STEAM_APP_ID = 0`). Achievements
latch to disk; overlay attaches when a real AppID and `steam_api` are present.

## Build (Windows 11)

```powershell
python setup.py --test --build
```

Before store launch: set `STEAM_APP_ID` in `src/config/__init__.py`, wire
`steam/achievements.vdf` in the partner portal, mount Steam Cloud on `saves/*.json`.

## Verification

```text
pytest tests/ -q
python -m src.main --headless --sim-days 900
```
