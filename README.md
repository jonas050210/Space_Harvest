# Asteroid-Colony Proto

**Orbital Supply Chains** is a compact, stylised 3-D launch-window game: real planets on real heliocentric orbits, a glowing sun, a scattered asteroid belt and a starfield sky -- all generated procedurally, no binary assets. Wait for the window (a NEXT WINDOWS board counts down every route; a banner and chime announce GO), click a planet to target it, dispatch, and keep the colony breathing. Deep runs need player-built refuel depots, the long-period Comet Vigil pays a platinum jackpot if you catch it, and the Earth parts market sells drop tanks, deep drills, crew quarters and depot drone bays at seasonal prices. The astrodynamics underneath is real patched-conic mechanics: launch windows, delta-v budgets, capture burns, layovers, multi-revolution slow routes, and deliveries booked into the upstream colony economy.

The orbital layer runs patched-conic transfers solved with Izzo's universal Lambert algorithm, including its multi-revolution branches (slow, propellant-cheap routes that the planner only picks when they genuinely pay).

On top of the verified astrodynamics core sits a colony-operations layer: every rock has a procedural ore fingerprint whose veins deplete as you mine them, a dynamic Earth market pays (and crashes) for your ore, named crews fly tired and happy (or bored, or hungry), solar flares and debris seasons threaten ships in flight, Earth factions post orders that move prices with your standing, and the colony's oxygen/food/water loop runs on ice you might rather have sold.

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
- Click: select the planet under the cursor as transfer target
- B / V: accept / decline the oldest Earth offer
- R: build / upgrade a refuel depot at the selected body
- T / Y / U: buy Drop Tanks / a Deep Drill / Crew Quarters for a docked ship
- P: install a drone bay at the selected depot (fills waiting ships)
- K: cycle quality preset (belt, trails, sky) -- N mutes, both persist
- G / H: hire a miner / dismiss the unhappiest crew member (Z: botanist)
- J: jump the warp to the next interesting event (windows, ETAs, deadlines)
- N: mute audio
- F5 / F9: quick-save / quick-load (`saves/` JSON)
- Title menu: NEW GAME / CONTINUE / LOAD / SETTINGS / HOW TO PLAY / QUIT
- Mouse wheel: zoom
- ESC: pause (Resume / Save / Load / Settings / Quit to title)

## Artifacts

- `run-log.txt`: final verification output
- `logs/screenshot.png`: render/capture artifact
- `logs/porkchop.png`: transfer-window porkchop plot

Credits: Ursina Engine; Izzo (2015) Lambert reference from poliastro/lamberthub under MIT; original `asteroid-colony` and `AI-Vision-Lab` by jonas050210.
