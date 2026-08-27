# Orbital Supply Chains

**Orbital Supply Chains** (v0.9.0-steam) is a stylised 3-D launch-window game: real planets on real heliocentric orbits, a glowing sun, a scattered asteroid belt and a starfield sky. Wait for the window (a NEXT WINDOWS board counts down every route; a banner and chime announce GO), click a planet to target it, dispatch, and keep the colony breathing.

Deep runs need player-built refuel depots; refineries smelt ore into components and electronics; Comet Vigil pays an aurellium jackpot; Earth sells parts at seasonal prices. Nineteen Firsts milestones, research techs, **Director / Tight / Ironman** difficulties, and **Endless / Charter / Legacy** victory modes give the campaign a spine. Achievements mirror Firsts for Steam.

The astrodynamics core is real patched-conic mechanics (Izzo Lambert, multi-rev branches). Graphics presets **Low / Medium / High / Ultra** target everything from Steam Deck to an RTX 4060 Ti ship PC.

Read `project.md` for architecture and `STEAM.md` for depot packaging.

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

### Steam / Windows package

```bash
.venv/bin/python scripts/build_steam.py
# ships dist/OrbitalSupplyChains/  (see STEAM.md)
```

### Graphics

| Preset | Best for |
| --- | --- |
| Low | Deck / iGPU — no belt, no trails, simple ships |
| Medium | Default |
| High | Modern discrete GPUs |
| Ultra | i7-12700F + RTX 4060 Ti class |

Open **Settings** from the title menu (quality, resolution, fullscreen, VSync, FOV, volume, difficulty, victory). **K** cycles quality in-play.

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
- E: build a refinery at the selected body (waiting runs arrive refined)
- T / Y / U: buy Drop Tanks / a Deep Drill / Crew Quarters for a docked ship
- I: install a Navigation Suite (needs aurellium from Comet Vigil; sharper planning refunds burns)
- P: install a drone bay at the selected depot (fills waiting ships)
- L: commission the next colony technology with research points (cheaper parts, faster depots, easier crewing, quicker smelting)
- K: cycle quality preset (low/medium/high/ultra) -- N mutes, both persist
- G / H: hire a miner / dismiss the unhappiest crew member (Z: botanist)
- J: jump the warp to the next interesting event (windows, ETAs, deadlines)
- N: mute audio
- F1: year report (pauses)
- F5 / F9: quick-save / quick-load (`saves/` JSON; F9 blocked on Ironman mid-run)
- ENTER: dispatch (second ENTER confirms when confirm-dispatch is on)
- Title menu: NEW GAME / CONTINUE / LOAD / SETTINGS / HOW TO PLAY / QUIT
- Settings: graphics, display, difficulty (Director/Tight/Ironman), victory mode
- Mouse wheel: zoom
- ESC: pause (Resume / Save / Year Report / Settings / Quit to title) or cancel confirm

## Artifacts

- `run-log.txt`: final verification output
- `logs/screenshot.png`: render/capture artifact
- `logs/porkchop.png`: transfer-window porkchop plot

Credits: Ursina Engine; Izzo (2015) Lambert reference from poliastro/lamberthub under MIT; original `asteroid-colony` and `AI-Vision-Lab` by jonas050210.
