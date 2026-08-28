# Space Harvest

**Space Harvest** is orbital farming on real launch windows.

Asteroids are your fields. Geometry is the season. Wait for the window, dispatch
a freighter (or a hundred-drone swarm), hop through refuel barns, and keep the
colony breathing.

Version **1.6.0**. Python 3.11–3.13, Ursina 8.x.

## One command: `setup.py`

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python setup.py              # play
.venv/bin/python setup.py --test       # pytest
.venv/bin/python setup.py --build      # PyInstaller → dist/SpaceHarvest/
```

Windows:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python setup.py
```

Also valid: `python -m src` or `python -m src.main`. Headless self-test:

```bash
python -m src.main --headless --sim-days 900
```

## Play

The belt does **not** fly itself. Idle ships wait for you.

**The Wide Sky (v1.6):** skim the sun at **Sungrazer Field** (flare-hot
helium-3), crack the plane-change to **Vagrant** at 48° (barns mandatory),
and push the depot chain out to **Boreas**, the ringed giant on the rim.

| Input | Action |
| --- | --- |
| Click a rock / TAB | Target a field |
| Click a ship / SPACE | Select an idle hull |
| ENTER or **GO** | Dispatch (twice if confirm is on) |
| D or **SWARM** | Harvest swarm while the window is GO |
| S / 5 / 6 or **SELL** | Sell 100% / 50% / 25% |
| R or **BARN** | Build / upgrade a refuel depot |
| `,` `/` `.` Backspace | Cycle views / map / surface / network |
| [ ] | Warp |
| Q / A | Commission a courser / an argosy |
| F5 / ESC | Save / pause |

How-to-play is on the title menu. Full key list lives in `src/app/controls.py`
— that file is the single source of truth.

## Layout

```text
setup.py                 play / shortcut / test / build
packaging/               PyInstaller entry
src/app/                 launch, controls, audio
src/config/              balance knobs
src/ops/                 fleet operations (wraps sealed core)
src/colony/              storage / saves / research bridge
src/maths  simulation/   SEALED orbital core
src/entities  ui/        presentation
tests/
assets/
steam/                   depot / achievements metadata
```

Saves go to `./saves` in development, or `Documents/My Games/SpaceHarvest`
(Windows) / `~/.local/share/SpaceHarvest` (Linux) when frozen.

## Graphics

K cycles Low / Medium / High / Ultra in play. Full settings on the title menu.

Credits: Ursina; Izzo Lambert (poliastro/lamberthub, MIT).
