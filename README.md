# Space Harvest

**Space Harvest** is orbital farming on real launch windows.

Asteroids are your fields. Geometry is the season. Wait for the window, dispatch
a freighter (or a hundred-drone swarm), hop through refuel barns, and keep the
colony breathing.

Version **1.6.2**. Python 3.11–3.13, Ursina 8.x.

## Quick start (no download needed)

You already have the game folder — there is nothing to buy or download from a
store. First run sets itself up; later runs start instantly.

**Windows** — double-click **`Play.bat`**.

**Linux / macOS** — from inside the game folder:

```bash
./play.sh
```

The launcher creates a private `.venv` (nothing touches system Python),
installs the game's dependencies into it **once** (needs internet on first
run only), and launches Space Harvest. It then keeps using that local
environment, so every run after the first works fully offline.

Prefer to do it by hand? One command does the same thing:

| | |
| --- | --- |
| **Windows** | `py -3.11 -m venv .venv && .venv\Scripts\python setup.py` |
| **Linux / macOS** | `python3 -m venv .venv && .venv/bin/python setup.py` |

> Requirement: Python **3.11 or newer** (3.11–3.13 tested). Windows: install
> from [python.org](https://www.python.org/downloads/) and tick *“Add python.exe
> to PATH”*. No store account, no Steam client, no extra downloads beyond the
> first-run Python packages.

### Commands

Run any of these with the launcher (`Play.bat <flags>` / `./play.sh <flags>`)
or with the venv Python (`.venv\Scripts\python setup.py <flags>` on Windows,
`.venv/bin/python setup.py <flags>` on Linux/macOS):

| Command | What it does |
| --- | --- |
| `setup.py` | Play (default; installs deps on first run) |
| `setup.py --shortcut` | Drop a **Space Harvest** icon on the Desktop |
| `setup.py --test` | Run the test suite |
| `setup.py --build` | Build a standalone EXE into `dist/SpaceHarvest/` |
| `setup.py --install-only` | Install dependencies only |
| `setup.py --skip-deps` | Play without touching pip |

Also valid: `python -m src` or `python -m src.main`. Headless self-test
(no window, drives the full economy for CI):

```bash
.venv/bin/python -m src.main --headless --sim-days 900
```

Fast dev loop — lint plus the quick tests, skipping the long integration
ones (CI runs everything on every push):

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest tests/ -q -m "not slow"
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
