# Asteroid Colony

A stylized realistic industrial sci-fi colony builder. Establish an asteroid outpost, automate mining and logistics, research new technologies, travel to distant regions, recover derelict artifacts, and build an orbital trade network.

## Core Loop

1. Mine Ice, Iron, Silver, Gold, and Platinum with specialized drones.
2. Deliver cargo into capacity-limited storage and process it into Water, Components, and Electronics.
3. Spend research points to unlock drone roles, deep-space scanning, planetary trade routes, and artifact analysis.
4. Build and place functional station modules on the colony grid.
5. Travel through the Inner Belt, Metallic Belt, Deep Belt, Aurelia Orbit, and the Derelict Zone.
6. Complete faction contracts, claim milestones, and grow the colony into a deep-space industrial network.

## Key Systems

- **Colony Director:** Live objective, risk alerts, contract readiness, and a recommended next action. Toggle it with **Tab**.
- **Drone roles:** Miner, Hauler, and Scout specializations with readable colors and visible cargo pods.
- **Research and production:** Progressive unlocks; Ice to Water, Iron to Components, and advanced Electronics assembly.
- **Station layout:** Grid placement, adjacency efficiency, animated modules, and industrial visual feedback.
- **Region Map:** Clickable travel cards, locked-route visibility, objectives, artifact-site status, contracts, and milestone rewards.
- **Economic strategy:** Region-specific machine output, storage pressure, premium Aurelia trade contracts, and event decisions.
- **Visual direction:** Stylized realistic industrial sci-fi: resource veins, mining impacts, active conveyors, planets, trade freighters, and deep-space anomalies.
- **Multiplayer readiness:** Deterministic session, command revisioning, snapshots, and role-ready co-op architecture; sockets intentionally remain deferred until the solo simulation is stable.

## Controls

| Control | Action |
|---|---|
| WASD / Arrow Keys | Move camera |
| Q / E | Rotate camera |
| Mouse wheel | Zoom |
| Left click | Select objects / mine nearby asteroid |
| Tab | Toggle Colony Director |
| 1 | Colony overview camera |
| 2 | Industry camera |
| 3 | Deep-space camera |
| Escape | Pause menu |
| S / L | Save / load latest save |

## Run

```bash
python setup.py
python start.py
python test_overall.py
```

Build a Windows executable with:

```bash
python setup.py --build
```

The output is `dist/AsteroidColony.exe`.

## Testing

The project includes headless checks for save/load, economy, research, logistics, regions, artifact recovery, milestone rewards, visuals, and Ursina startup.

```bash
python test_overall.py
```

## Project Layout

```text
start.py            Game entry point and input bindings
setup.py            Dependency, shortcut, and executable helper
game/director.py    Objective, alert, and recommendation engine
game/regions.py     Travel, artifact recovery, trade routes, and milestones
game/contracts.py   Faction and premium contract logic
game/ui/            HUD, automation, map, mission, and menu interfaces
project.md          Full technical and product overview
```

## License

MIT — free to use and extend.
