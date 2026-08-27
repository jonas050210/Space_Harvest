# Asteroid Colony — Product and Technical Overview

## Product Identity

**Asteroid Colony** is a 3D industrial space-colony builder focused on automation, logistics, exploration, research, and economic decisions. Its chosen art direction is **stylized realistic industrial sci-fi**: readable 3D machinery, dark space, warm colony lighting, emissive resource colors, and lightweight atmospheric effects.

The project intentionally prioritizes colony management over combat. Rogue drones, meteor showers, storms, and derelicts provide tension as economic and operational hazards rather than shooter mechanics.

## Player Progression

| Stage | Primary player goal |
|---|---|
| Foundation | Mine resources, build basic modules, and maintain energy |
| Automation | Research drone specialization and establish Miner, Hauler, and Scout roles |
| Industry | Process raw materials, manage storage, and optimize station placement |
| Expansion | Unlock Deep Belt operations, advanced modules, and rare resource production |
| Trade | Reach Aurelia Orbit, complete premium contracts, and build a Trade Hub |
| Discovery | Recover Derelict Zone artifacts with Scout drones and Artifact Analysis |
| Legacy | Complete milestones and form a self-sustaining industrial colony |

## Regions

- **Inner Belt:** Reliable starter mining and first infrastructure.
- **Metallic Belt:** Strong industrial resource output after Logistics Protocols.
- **Deep Belt:** Rare metals, long-range operations, and rogue-miner anomalies.
- **Aurelia Orbit:** Premium contracts and visible freight traffic after Planetary Trade Routes.
- **Derelict Zone:** Artifact recovery and research rewards after Artifact Analysis.

## Main Systems

### Colony Director
`game/director.py` provides a single source of truth for objectives, operational warnings, contract readiness, and recommended next actions. The UI panel is toggled with **Tab**.

### Research, drones, and logistics
Research unlocks role assignments, expanded storage behavior, deep-space scanning, automated refining, planetary trade routes, and artifact analysis. Drones return typed cargo to capacity-limited storage. Production recipes create Water, Components, and Electronics.

### Station construction
Modules are placed on a grid and receive compact-layout efficiency bonuses. Functional visual units animate solar wings, refinery exhaust, trade docking lights, and operational signals.

### Economy, contracts, and decisions
Machine output changes by region. Regular and premium faction contracts compete with research and production needs. Events expose decision APIs for power protection and trade choices. Milestones award one-time resources and research points.

### Visual systems
Asteroids show resource veins and depletion. Mining uses beams, impacts, sparks, and debris. Conveyors use resource-colored packets. Planets, a trade freighter, and non-combat rogue mining drones provide world scale and progression landmarks.

### Multiplayer boundary
`game/multiplayer.py` is a deterministic, transport-agnostic session layer with snapshots, player roles, revisions, and command validation. Real sockets are explicitly postponed until the complete single-player command model is stable.

## Technical Stack

- Python 3.11+
- Ursina / Panda3D
- JSON settings, saves, and blueprints stored locally for OneDrive compatibility
- PyInstaller executable packaging
- Headless test suite in `test_overall.py`

## Repository Structure

```text
start.py                 Entry point, input bindings, save/load shortcuts
setup.py                 Dependency install, shortcut creation, executable build
test_overall.py          Headless system and visual validation
game/config.py           Content, resources, modules, research, regions, economy rules
game/state.py            Persistent colony state and simulation updates
game/director.py         Objectives, alerts, recommendations
game/regions.py          Region travel, artifacts, milestones, trade routes
game/contracts.py        Faction contracts and premium contract offers
game/entities.py         3D asteroids, drones, modules, planets, freighters, effects
game/ui/                 HUD, build, automation, region-map, mission-board, menus
game/savegame.py         Save-slot operations
game/blueprint.py        Station-layout and progression blueprint support
```

## Entry Points

```bash
python setup.py
python start.py
python start.py --test
python test_overall.py
python setup.py --build
```

## Quality Standards

- New visuals must communicate a resource, role, process, hazard, objective, or progression milestone.
- New mechanics must expose clear player value through the Colony Director or Region Map.
- Performance-safe geometry, animation, emissive colors, and particles are preferred over expensive realism.
- All player-facing content is English-only.
