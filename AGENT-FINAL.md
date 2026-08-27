# FINAL AGENT PROMPT — copy everything below the line into a fresh AI session

You are the FINAL agent on "Asteroid Colony Proto — orbital supply chains".
Agents 1-3 built it; you make it whole, prove it, and ship it. Code:
https://github.com/jonas050210/asteroid-colony-proto (clone it; your folder
has only markdown). Read `project.md` end to end before anything else, and
the `AGENT-*-DONE.md` files if present.

## Start

```bash
git clone https://github.com/jonas050210/asteroid-colony-proto.git work && cd work
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## You do "everything that is left", in this order

1. Audit: diff the repo against every claim in project.md §4 and the DONE
   files. Anything claimed but missing or broken is yours to fix.
2. Make it all green, then keep it green while you change things:
   * `.venv/bin/python -m pytest tests/ -q`
   * `vendor/asteroid-colony-upstream/test_overall.py` (25/25)
   * `python -m src.main --headless --sim-days 6000` (fleet solvent, >10 runs)
   * `xvfb-run -a --server-args="-screen 0 1920x1200x24"
      .venv/bin/python scripts/capture_frame.py` (screenshots)
   * the packaged exe in `--headless` mode, if agent 3 built one
3. Fix, don't workaround: failing tests are truth; never weaken a test to
   pass it. The §5 pitfall list tells you how each subsystem likes to break.
4. Gameplay completeness vs the ORIGINAL brief (project.md §1-2): procedural
   bodies ✔/✖, resources ore+ice ✔/✖ (extend if ✖), ship travel patched-conic
   ✔, HUD score/resources ✔, `python -m src.main` runnable ✔. Close any ✖
   with the smallest correct change + tests.
5. Answer the open questions: write `FINAL-REPORT.md` containing the feature
   matrix, every test count, run-log excerpts, controls table, known limits,
   and the exact commands the owner runs on Windows.
6. Housekeeping: prune `__pycache__`/caches, keep workspace < 128 MB / 10 k
   files (venv only at `.venv`), refresh run-log.txt and screenshots, commit
   everything as `phase-final`, and push if credentials are available;
   otherwise leave the commit and say so in FINAL-REPORT.md.

## Rules

Budget rule (project.md §0) is absolute. `src/game/` stays pristine. No new
binary assets > 1 MB. No credentials in files, ever.
