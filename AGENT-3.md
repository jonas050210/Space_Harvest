# AGENT 3 — final continuation prompt (part 3 of 3, "does the rest")

You are the LAST of three agents. Agents 1-2 built and extended the prototype
(see `project.md` §4 and `AGENT-2-DONE.md` if present). Everything must be
green before you start: `pytest tests/ -q`, upstream `test_overall.py`,
headless run, xvfb render. **Read `project.md` first** (§0 budget rule,
§3 units, §5 pitfalls).

## Setup

```bash
cd asteroid-colony-proto
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Your part = "the rest". Finish the prototype and ship it.

1. **Balance & QA pass**
   - Play-test via `--headless` sweeps (3000/6000/12000 sim-days, both ships):
     tune `SHIP_REFUEL_RATE`, `SHIP_START_DELTA_V`, storage so no destination
     is unreachable and the fleet rarely strands by accident.
   - Keep the intentional stranding failure mode reachable but rare.
   - Record before/after numbers in `run-log.txt`.

2. **Owner-machine notes (RTX 4060 Ti, Windows)**
   - Write `RUN_ON_WINDOWS.md`: Python 3.11 install, venv, `python -m src.main`,
     expected warp/FPS behaviour, how to use xvfb-equivalent (not needed on
     Windows), troubleshooting (OpenAL warnings are harmless).

3. **Real textures (best effort)**
   - Poly Haven blocked automated downloads (403). If a browser download is
     possible for the owner, document it; otherwise improve
     `utils/procedural.py` (bump maps / normal shading) — no binary blobs >1 MB.

4. **Single-exe packaging**
   - `pyinstaller --onefile --add-data "assets:assets" -n colony-proto -m src/main.py`
     (see README). Verify the exe boots via its `--headless` mode in the
     sandbox; document the Windows build command.

5. **Docs & evidence refresh**
   - Fold any leftover docs into `project.md`; keep root markdowns to
     README.md, project.md, AGENT-*.md, RUN_ON_WINDOWS.md.
   - Regenerate `logs/` screenshots + porkchop, extend `run-log.txt`.

6. **GitHub upload (the owner asked for this)**
   - The sandbox has NO GitHub credentials. Do not look for tokens in files.
   - Prepare: `git init`, commit everything except `.venv/`, `logs/*.png`,
     `*.zip` (mirror `.gitignore`), tag `phase-3-final`.
   - Then either (a) the owner supplies a fine-grained PAT with `repo` scope
     for repo `jonas050210/asteroid-colony-proto` — push once, do not store it;
     or (b) leave `PUSH-INSTRUCTIONS.md` with the two commands to run on the
     owner's PC (`git remote add origin …; git push -u origin main`).
   - Also refresh `asteroid-colony-proto-final.zip` as the transfer artifact.

7. **Final report**
   - `FINAL-REPORT.md`: feature matrix vs the original prompt's §2.5 list,
     all test counts, run-log excerpts, size/file-count of the workspace
     (must be < 128 MB / 10 k files), and the exact GitHub state.

## Rules

* Same budget rule as everyone: venv only at `.venv`; prune caches before
  finishing (`find . -name __pycache__ -prune -exec rm -rf {} +`).
* `src/game/` stays pristine; upstream tests stay green.
