# AGENT 3 PROMPT — copy everything below the line into a fresh AI session

You are agent 3 of 4 on "Asteroid Colony Proto — orbital supply chains".
Code: https://github.com/jonas050210/asteroid-colony-proto (clone it; your
folder has only markdown). Read `project.md` first (§0 budget, §3 units,
§5 pitfalls). `AGENT-2-DONE.md` may exist — if it does, agent 2's features
are already in the repo; build on them, don't redo them.

## Start

```bash
git clone https://github.com/jonas050210/asteroid-colony-proto.git work && cd work
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q
```

## Your part

1. Balance pass: headless sweeps (3k/6k/12k sim-days, two ships); tune
   `SHIP_REFUEL_RATE`, `SHIP_START_DELTA_V`, storage so every destination is
   reachable and accidental stranding is rare (the intentional dry-tank
   failure mode must stay). Record before/after in run-log.txt.
2. `RUN_ON_WINDOWS.md` for the owner's PC (i7-12700F/RTX 4060 Ti): Python 3.11,
   venv, `python -m src.main`, OpenAL warnings harmless, no xvfb needed.
3. Visuals: improve `src/utils/procedural.py` shading (normal-ish relief,
   banding variety). Poly Haven 403s bots — procedural stays unless a human
   downloads CC0 textures; no blobs > 1 MB.
4. Packaging: `pyinstaller --onefile --add-data "assets:assets"
   -n colony-proto -m src/main.py`; verify the exe via its `--headless` mode;
   document the Windows build command.
5. Docs: fold leftovers into project.md; keep root md set small
   (README, project, AGENT-*, RUN_ON_WINDOWS); refresh logs evidence.

## Definition of done

* pytest + upstream 25/25 + headless sweep + xvfb screenshot, outputs appended
  to run-log.txt; workspace < 128 MB / 10 k files; caches pruned;
  `AGENT-3-DONE.md` summary; project.md §4/§5 updated. Commit (push if you
  have credentials, else leave commits).
