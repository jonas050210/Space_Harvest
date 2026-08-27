# Asteroid Colony Proto — Orbital Supply Chains

3-D tycoon prototype: your `asteroid-colony` regions as real orbits, freighters
on patched-conic transfers with launch windows and delta-v budgets, deliveries
booked into the upstream economy.

**Read `project.md` — it contains everything** (setup, architecture, units,
controls, verification numbers, pitfall list, remaining work).
Hand-off prompts for the next agents: `AGENT-2.md`, `AGENT-3.md`.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # venv ONLY here, see project.md §0
.venv/bin/python -m pytest tests/ -q                # 43 passed
.venv/bin/python -m src.main --headless --sim-days 3000
.venv/bin/python -m src.main                        # play (or wrap in xvfb-run)
```

Credits: Ursina Engine; Izzo (2015) Lambert reference © poliastro/lamberthub
(MIT); colony game & AI-Vision-Lab © jonas050210.
