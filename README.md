# Space Harvest

**Space Harvest** is orbital farming on real launch windows.

Asteroids are your fields. Geometry is the season. Wait for the window (NEXT WINDOWS counts every route; a banner and chime shout GO), dispatch a freighter, mine the rock’s ore fingerprint, and bring the harvest home without starving the colony or flooding Earth prices.

Deep runs need **refuel depots** (barns). **Refineries** smelt ore into components and electronics. **Comet Vigil** is the aurellium jackpot. Nineteen **Firsts**, research techs, **Director / Tight / Ironman** difficulties, and **Endless / Charter / Legacy** victory modes give the campaign a spine. Achievements mirror Firsts for Steam.

Under the hood: real patched-conic astrodynamics (Izzo Lambert, multi-rev). Graphics presets **Low / Medium / High / Ultra** run from Steam Deck to an RTX 4060 Ti ship PC.

See `STEAM.md` for packaging and `project.md` for architecture.

## Quick start

```bash
git clone https://github.com/jonas050210/asteroid-colony-proto.git
cd asteroid-colony-proto
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m src.main --headless --sim-days 6000
.venv/bin/python -m src.main
```

### Windows EXE (setup.py + PyInstaller)

You do **not** hand-write an `.exe`. On a Windows 11 machine with Python:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python setup.py --test --build
# → dist\SpaceHarvest\SpaceHarvest.exe
.\.venv\Scripts\python setup.py --shortcut   # desktop icon
```

`setup.py --build` runs PyInstaller (via `scripts/build_steam.py`) on `start.py`,
bundling Python + Ursina + assets. Cross-building a Windows EXE from Linux is
not supported here — build on the target OS (or CI).

### Steam / Windows package

```bash
.venv/bin/python scripts/build_steam.py
# → dist/SpaceHarvest/
```

### Graphics

| Preset | Best for |
| --- | --- |
| Low | Deck / iGPU — no belt, no trails, simple ships |
| Medium | Default |
| High | Modern discrete GPUs |
| Ultra | i7-12700F + RTX 4060 Ti class |

**Settings** on the title menu: quality, resolution, fullscreen, VSync, FOV, volume, difficulty, victory. **K** cycles quality in-play.

## Controls

- TAB: cycle transfer target (field)
- ENTER: dispatch idle freighter (confirm sheet when enabled)
- `[` / `]`: change warp
- O: toggle orbits
- F: follow freighter
- C: overview camera
- S: sell stored ore on the Earth market (prices flood when you dump)
- X: toggle surface scraping / core drilling
- M: toggle automatic hull maintenance
- 1–4: commission scout / freighter / refinery / hauler
- Click: select the planet under the cursor
- B / V: accept / decline the oldest Earth offer
- R: build / upgrade a refuel depot (barn)
- E: build a refinery (processing plant)
- T / Y / U: Drop Tanks / Deep Drill / Crew Quarters
- I: Navigation Suite (needs aurellium)
- P: depot drone bay
- L: commission the next colony technology
- K: cycle quality (low/medium/high/ultra) — N mutes
- G / H / Z: hire miner / dismiss unhappiest / hire botanist
- J: jump warp to next event
- F1: year report (farm books)
- F5 / F9: quick-save / quick-load (F9 blocked on Ironman mid-run)
- Title: NEW HARVEST / CONTINUE / LOAD / SETTINGS / HOW TO PLAY / QUIT
- ESC: pause or cancel dispatch confirm
- Mouse wheel: zoom

## Views & drone swarms

| Key | View |
|-----|------|
| `,` | Cycle **network 3-D** → **system map** → **surface** |
| `/` | System chart (top-down solar map + AU grid) |
| `.` | Land on the selected field's **surface** (veins, pad, rocks) |
| Backspace | Back to network overview |
| **D** | Launch harvest **drone swarm** on GO window (up to **100** drones) |

Build drone bays with **P** on depots to grow the swarm. Swarms only launch while the launch window is open, pull ore for ~14 days, then cool down.

## Multi-stop deliveries (KSP-style)

Deep fields (Outer Reach, Cinder Moon, Trojan Field, Comet) often need more
delta-v than one tank. Build a **depot barn (R)** on the way; the planner
inserts **refuel hops** automatically (`colony → barn → field → barn → home`).
Press **;** to toggle hop planning. **ENTER** previews the full route.

New ores: **silicates**, **obsidian**, **helium-3**, **cobalt**, **magnetite**, **xenonite**.
New field: **Frost Ring**. Ship: **Tanker** (key `0`). Station modules: `7/8/9/'`.
Parts: F6 scanner, F7 shield, F8 mag-clamps.

## The loop

Wait for geometry → GO → dispatch → mine the field → depot/refinery on deep runs → home → sell without flooding → pay crews → reinvest → chase thorite → comet aurellium → clear Charter/Legacy or play Endless.

## Artifacts

- `logs/screenshot.png` — render / key art
- `logs/porkchop.png` — transfer-window plot

Credits: Ursina Engine; Izzo (2015) Lambert (poliastro/lamberthub, MIT); original asteroid-colony lineage by jonas050210.
