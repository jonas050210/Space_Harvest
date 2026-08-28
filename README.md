# Space Harvest

**Space Harvest** is orbital farming on real launch windows.

Asteroids are your fields. Geometry is the season. Wait for the window, dispatch freighters or a hundred-drone swarm, hop through refuel barns, and keep the colony breathing.

## One command: `setup.py`

Everything goes through **`setup.py`**. There is no `start.py`.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# PLAY (default)
.\.venv\Scripts\python setup.py

# Desktop shortcut (points at setup.py, or the EXE after --build)
.\.venv\Scripts\python setup.py --shortcut

# Tests
.\.venv\Scripts\python setup.py --test

# Windows EXE (PyInstaller)
.\.venv\Scripts\python setup.py --test --build
# → dist\SpaceHarvest\SpaceHarvest.exe
# shortcut is refreshed to the EXE automatically
```

Linux / macOS:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python setup.py              # play
.venv/bin/python setup.py --shortcut   # ~/.Desktop entry
.venv/bin/python setup.py --build
```

Also valid: `python -m src` or `python -m src.main`.

### How the EXE works

You do **not** hand-write an `.exe`. On Windows, `setup.py --build` runs **PyInstaller**, which freezes Python + Ursina + `src/` + `assets/` into `dist/SpaceHarvest/`. Build on Windows 11 for a Windows EXE.

## Package layout

```text
setup.py                 # play / shortcut / test / build  ← only owner entry
packaging/
  play_entry.py          # frozen EXE entry
  build_exe.py           # PyInstaller recipe
  steam/                 # depot / achievements metadata
src/
  app/                   # launch paths
  config/                # all balance knobs
  ops/                   # fleet operations (wraps sealed core)
  colony/                # storage / saves / research bridge
  maths/ simulation/     # SEALED orbital core
  entities/ ui/          # presentation
  main.py                # game shell (compat)
  operations.py          # shim → src.ops
  game/                  # shim → src.colony
tools/                   # capture_frame, porkchop
tests/
assets/
```

## Graphics

| Preset | Best for |
| --- | --- |
| Low | Deck / iGPU |
| Medium | Default |
| High | Discrete GPUs |
| Ultra | i7-12700F + RTX 4060 Ti |

**K** cycles quality in-play. Full settings on the title menu.

## Core loop

Wait for geometry → GO → freighter or **D** swarm → multi-stop barns → sell without flooding → surface survey / ISRU → modules → tanker fills barns → rival optional.

See `STEAM.md` for depot notes and `project.md` for architecture.

Credits: Ursina; Izzo Lambert (poliastro/lamberthub, MIT); lineage jonas050210.
