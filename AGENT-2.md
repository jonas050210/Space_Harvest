# AGENT 2 — continuation prompt (part 2 of 3)

You are the SECOND of three agents building "Asteroid Colony Proto — orbital
supply chains". Agent 1 finished the physics, mission simulation, rendering,
HUD and economy bridge; all of it is verified (`pytest tests/ -q` = 43 passed,
upstream `test_overall.py` = 25 passed — both must stay green after your
changes). **Read `project.md` completely before touching anything**,
especially §0 (budget rule), §3 (units) and §5 (pitfall list).

## Setup

```bash
cd asteroid-colony-proto
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q
```

## Your part (finish ALL of it, then stop; agent 3 finishes the rest)

1. **Transfer-arc + porkchop visuals**
   - Render the active ship's current conic and its planned return arc as
     line meshes (sample with `elements.propagate_elements` or
     `kepler.universal_kepler`; reuse `OrbitLine`).
   - Add an in-game porkchop panel: `sim.porkchop(origin, target)` already
     returns `{depart, tof, dv, best}`; draw it as a coloured quad grid on the
     HUD (matplotlib is optional for `scripts/plot_porkchop.py` only).
   - Mark the selected window's departure date on the HUD clock.

2. **Save / load the orbital state**
   - Serialise ships (r, v, epoch, delta_v, cargo), missions and `sim.time`
     through the upstream `src/game/savegame.py` (keys `S`/`L` in the old
     game; add bindings here). Add a test: save → mutate → load → identical.

3. **Demand pricing & trade contracts**
   - Use `game.config.REGION_ECONOMY` trade_value multipliers to price
     deliveries per destination; credit credits/research accordingly in
     `Colony.receive`.
   - Surface one active premium contract (upstream `contracts.py`) on the HUD
     and pay it when a delivery matches its cargo.

4. **AI-Vision-Lab scan bonus (optional integration, must degrade gracefully)**
   - `vendor/ai-vision` is CODE ONLY. If `mediapipe`/`opencv-python-headless`
     import successfully, run `app/vision` analysis on a rendered body texture
     while a scout-holding ship WAITING at a body and grant bonus research;
     otherwise log "vision unavailable" and continue. **Never** download model
     weights; **never** let a missing dependency crash the game.

5. **Multi-revolution Lambert (M>0)**
   - Extend `src/maths/transfers.py` or `windows.py` with the M>0 branch of
     Izzo's solver; offer "slow freighter" plans that trade time for delta-v
     (show both options in the transfer plan). Verify by propagating solutions
     to the target exactly like the existing Lambert tests do.

6. **Tests & verification (mandatory)**
   - New tests for every feature above (save/load round trip, contract pay-out,
     M>0 arrival check, pricing sanity).
   - Run: `pytest tests/ -q`, upstream `test_overall.py`,
     `python -m src.main --headless --sim-days 4000`,
     and one `scripts/capture_frame.py` run under xvfb.
   - Append all outputs to `run-log.txt`.

## Rules

* Budget: venv only at `.venv`; no new binary assets > 1 MB; keep total
  workspace far below 128 MB / 10 k files (currently ~7 MB).
* Do not modify `src/game/` (upstream must stay pristine).
* Update `project.md` §4/§7 with what you completed and any NEW pitfalls.
* Finish by writing `AGENT-2-DONE.md` (one screen: what changed, test counts,
  run-log deltas) and regenerating the phase zip:
  `zip -qr asteroid-colony-proto-phase2.zip . -x "*.zip" -x "*/.venv/*" -x "*__pycache__*"`.
