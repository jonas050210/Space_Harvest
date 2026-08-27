# Asteroid-Colony Proto

A compact 3-D colony-tycoon / orbital-logistics prototype. The upstream `asteroid-colony` regions are real heliocentric bodies, and freighters fly patched-conic supply chains with launch windows, delta-v budgets, capture/docking burns, layovers, and deliveries booked into the upstream colony economy.

On top of the verified astrodynamics core sits a colony-operations layer: every rock has a procedural ore fingerprint whose veins deplete as you mine them, a dynamic Earth market pays (and crashes) for your ore, ships wear their hulls and can be repaired, and four ship classes turn profits into fleet growth.

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
- S: sell stored ore on the Earth market (prices flood when you dump)
- X: toggle surface scraping / core drilling (fuller holds, more wear and risk)
- M: toggle automatic hull maintenance (bills the treasury)
- 1–4: commission a scout / freighter / refinery / hauler
- F5 / F9: quick-save / quick-load (`saves/` JSON)
- Mouse wheel: zoom
- Esc: quit

## Artifacts

- `run-log.txt`: final verification output
- `logs/screenshot.png`: render/capture artifact
- `logs/porkchop.png`: transfer-window porkchop plot

Credits: Ursina Engine; Izzo (2015) Lambert reference from poliastro/lamberthub under MIT; original `asteroid-colony` and `AI-Vision-Lab` by jonas050210.
