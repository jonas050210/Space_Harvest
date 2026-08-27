# Steam readiness — Orbital Supply Chains

Version **0.9.0-steam**. Target ship PC: **i7-12700F / 32 GB DDR4 / RTX 4060 Ti 8 GB**.

## What ships in this build

| Area | Status |
| --- | --- |
| Graphics presets | **Low / Medium / High / Ultra** (belt, trails, sky, corona, flares, LOD, MSAA, orbit alpha) |
| Display settings | Resolution, fullscreen, VSync, FOV, UI scale, master volume |
| Campaign modes | Director / Tight Margins / Ironman |
| Victory modes | Endless / Charter Complete / Colony Legacy |
| Achievements | 19 Firsts + 4 secrets → `saves/achievements_progress.json` |
| Saves | Quick + named slots; cloud-friendly path helpers |
| Dispatch UX | Confirm sheet (ENTER twice), body dossier card |
| Year report | Pause → Year Report, or F1 |
| Packaging | `scripts/build_steam.py` → `dist/OrbitalSupplyChains/` |
| Steamworks | Soft bridge (`src/steam_bridge.py`); set `STEAM_APP_ID` before store |

## Graphics preset guide (RTX 4060 Ti)

| Preset | Intent |
| --- | --- |
| **Low** | Steam Deck / iGPU. No belt mesh, no trails, simple ship LOD, no corona. |
| **Medium** | Default. Full fleet silhouettes, trails, belt at 55% density, MSAA 2. |
| **High** | Showcase without max cost. Belt 85%, MSAA 4, bloom flag on. |
| **Ultra** | Ship PC. Full belt, MSAA 8, bloom + particles flags, richest orbit rings. |

Cycle live with **K**, or Settings menu. All four are real (Ultra is not a rename of High).

## Build the depot (Windows 11)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m pytest tests\ -q
.\.venv\Scripts\python scripts\build_steam.py
# upload dist\OrbitalSupplyChains\ via SteamPIPE + steam/app_build.vdf
```

Linux:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_steam.py
```

Before store launch:

1. Set `STEAM_APP_ID` in `src/config.py` to the real AppID.
2. Recreate achievements in the partner portal from `steam/achievements.vdf`.
3. Point Steam Cloud at the `saves/` patterns listed in `steam_install.json`.
4. Replace the soft `SteamClient` with a real Steamworks bind if you want overlay unlocks live.

## Verification

```text
144 pytest passed (maths + simulation + economy-ops + Steam campaign layer)
Headless 400-day arc boots, sells, builds depot, unlocks techs
src/maths + src/simulation remain the verified core (untouched this session)
```
