# AGENT 2 PROMPT — copy everything below the line into a fresh AI session

You are agent 2 of 4 building "Asteroid Colony Proto — orbital supply chains".
Agent 1's finished, tested work lives in the GitHub repo
https://github.com/jonas050210/asteroid-colony-proto (public). The folder you
are in contains ONLY markdown; the code is in the repo.

## Start

```bash
git clone https://github.com/jonas050210/asteroid-colony-proto.git work
cd work
python3 -m venv .venv            # ONLY here, never at the home root (budget!)
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q        # expect 43 passed
```

Read `project.md` COMPLETELY first — §3 units (AU, mu=4pi^2, 4.7405 km/s per
AU/yr) and §5 pitfall list are mandatory. Never modify `src/game/` (upstream
`test_overall.py` must stay 25/25).

## Your part — do ALL of it, verify, commit, push if you have credentials,
otherwise leave commits for the next agent

1. Transfer visuals: draw each flying ship's current conic AND its planned
   return arc as `Mesh(mode="line")` strips; show the chosen window's
   departure date on the HUD. Add an in-game porkchop panel from
   `sim.porkchop(origin, target)` (`{depart, tof, dv, best}`), coloured quads,
   matplotlib only in `scripts/`.
2. Save/load the orbital state (ships r/v/epoch/delta_v/cargo, missions,
   sim.time) through `src/game/savegame.py`; keys S/L; round-trip test.
3. Economy depth: price deliveries with `config.REGION_ECONOMY` trade_value;
   surface one premium contract from `game.contracts` on the HUD and pay it on
   matching delivery.
4. Optional AI-Vision scan bonus: if `mediapipe`+`opencv-python-headless`
   import, analyse a rendered body texture while a ship is WAITING there and
   grant bonus research; otherwise log and continue. Never download weights
   (vendor/ai-vision is code-only), never crash on missing deps.
5. Multi-revolution Lambert (M>0, Izzo) in `src/maths/`; offer "slow
   freighter" plans (cheaper, longer) in the transfer plan; verify solutions
   by propagating them to the target exactly like the existing Lambert tests.

## Definition of done (run every one, paste outputs into run-log.txt)

* `.venv/bin/python -m pytest tests/ -q` all green (old 43 + your new tests).
* `vendor/asteroid-colony-upstream` `test_overall.py` 25/25.
* `python -m src.main --headless --sim-days 4000` finishes, fleet solvent.
* One `scripts/capture_frame.py` run under
  `xvfb-run -a --server-args="-screen 0 1920x1200x24"` writes screenshots.
* Workspace stays < 128 MB / 10 k files; venv only at `.venv`; prune
  `__pycache__` before finishing; append a `AGENT-2-DONE.md` summary; update
  `project.md` §4 with what you completed and new pitfalls in §5.
