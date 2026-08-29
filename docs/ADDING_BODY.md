# Adding a New Body / Field

Space Harvest campaign bodies are data-driven but scattered across several
modules. To add a new asteroid field, moon, or planet:

## 1. Define orbit in `src/config/campaign.py`

Add entry to `CAMPAIGN_BODIES`:

```python
"my_new_field": {
    "name": "My New Field",
    "elements": {"a": 3.2, "e": 0.1, "i_deg": 5.0, "raan_deg": 100.0, "argp_deg": 20.0, "nu_deg": 0.0},
    "radius_km": 15.0,
    "soi_km": 35000.0,
    "palette": (0.8, 0.6, 0.4),
    "resources": ("iron", "silver", "gold"),
    "description": "Short lore line.",
    "render_scale": 0.7,
}
```

`a` in AU, angles in degrees. Keep `e < 0.8` for stable windows. Inclination > 20° makes
multi-rev Lambert branches competitive (see `PLANNING_MAX_REVS`).

## 2. Register ore spawns in `src/config/mining.py`

Add to `MINING_EXTRA_SPAWNS`:

```python
"my_new_field": ("thorite", "cobalt"),
```

These ores are appended to the body's base `resources` tuple at runtime.

## 3. Add texture (optional)

Place `assets/textures/game/my_new_field.png` (256x256) and
`assets/textures/game/label_my_new_field.png` (optional label).
If missing, procedural fallback generates a flat color from `palette`
and a label texture via `src.utils.procedural.label_texture`.

Run `python -m src.utils.procedural` to regenerate all planet textures.

## 4. Market prices

Ensure every ore in your field exists in `src/config/market.py`:
- `MARKET_BASE_PRICES`
- `MARKET_ABSORPTION_T`
- `MARKET_SEASONAL_PERIOD_DAYS`

And vein size in `src/config/mining.py`: `MINING_VEIN_SIZE_T`.

If you add a **new ore**, you must add it in 4 places:
- `MINING_ORES` (tuple)
- `MINING_VEIN_SIZE_T`
- `MARKET_BASE_PRICES`
- `MARKET_ABSORPTION_T` + seasonal

Plus storage in `src/colony/state.py` (now auto-includes all MINING_ORES).

## 5. Ops layer

`OpsSimulation._install_campaign_fields()` auto-installs everything in
`CAMPAIGN_BODIES` into its private `bodies` dict and `trade_targets`.
No change needed in `src/simulation/bodies.py` (sealed core stays pristine).

If the field needs special flare exposure (e.g. sun-skimmer), add to
`src/config/weather.py`: `FLARE_EXPOSURE_BY_BODY`.

## 6. HUD / Dossier

No code change - `campaign.body_dossier()` reads assay, depot, window
automatically. If you want a First for it, add to `FIRSTS` in
`src/config/progression.py`.

## 7. Test

```bash
.venv/bin/python -m pytest tests/ -q -m "not slow"
.venv/bin/python -m src.main --headless --sim-days 200
python tools/plot_porkchop.py my_new_field logs/porkchop_my_new_field.png
```

Check NEXT WINDOWS board in HUD and that `plan_round_trip` returns finite cost.

## 8. Balancing checklist

- Round-trip delta-v: `sim.round_trip_cost_ms("colony", "my_new_field")` should be
  15-35 km/s for mid-game, >35 km/s for endgame requiring depots.
- TOF: 100-300 days typical.
- Yield: rare ores (aurellium, memory_glass) only in deep fields.
- Recovery: `MINING_RECOVERY_TAU_DAYS` 2400d default, 900d for ice.

## 9. Versioning

If you change save shape (new fields in `OpsSimulation.to_json()`), bump
`Game.SAVE_VERSION` in `src/main.py` and add migration in `load_game`.
