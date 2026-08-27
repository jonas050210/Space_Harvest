# Asteroid Colony Proto — Orbital Supply Chains

3-D tycoon prototype: your `asteroid-colony` regions as real orbits, freighters
on patched-conic transfers with launch windows and delta-v budgets, deliveries
booked into the upstream economy.

**Read `project.md` — it contains everything** (setup, architecture, units,
controls, verification numbers and pitfall list). `FINAL-REPORT.md` contains
the final QA matrix, run-log excerpts, known limits and owner commands.
Hand-off prompts for optional future expansion remain in `AGENT-2.md`, `AGENT-3.md`.

```bash
git clone https://github.com/jonas050210/asteroid-colony-proto.git && cd asteroid-colony-proto
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # venv ONLY here, see project.md §0
.venv/bin/python -m pytest tests/ -q                # 43 passed
.venv/bin/python -m src.main --headless --sim-days 6000  # 18 completed runs in final QA
.venv/bin/python scripts/plot_porkchop.py metallic_belt logs/porkchop.png
.venv/bin/python -m src.main                        # play (or wrap in xvfb-run)
```

Credits: Ursina Engine; Izzo (2015) Lambert reference © poliastro/lamberthub
(MIT); colony game & AI-Vision-Lab © jonas050210.
