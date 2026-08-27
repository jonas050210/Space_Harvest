# Asteroid-Colony Proto

A compact 3-D colony-tycoon / orbital-logistics prototype. The upstream `asteroid-colony` regions are real heliocentric bodies, and freighters fly patched-conic supply chains with launch windows, delta-v budgets, capture/docking burns, layovers, and deliveries booked into the upstream colony economy.

Read `project.md` for the full architecture, units, controls, QA results, known limits, and owner commands.

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

## Controls

- TAB: cycle transfer target
- ENTER: dispatch idle freighter
- `[` / `]`: change warp
- O: toggle orbits
- F: follow freighter
- C: overview camera
- Mouse wheel: zoom
- Esc: quit

## Artifacts

- `run-log.txt`: final verification output
- `logs/screenshot.png`: render/capture artifact
- `logs/porkchop.png`: transfer-window porkchop plot

Credits: Ursina Engine; Izzo (2015) Lambert reference from poliastro/lamberthub under MIT; original `asteroid-colony` and `AI-Vision-Lab` by jonas050210.
