"""Runtime validation of balance constants - fails fast on bad config."""

from __future__ import annotations

import math


def validate() -> list[str]:
    """Return list of error messages, empty if all good."""
    errors: list[str] = []
    try:
        from . import (
            MU_SUN, SHIP_CLASSES, MINING_ORES, MINING_VEIN_SIZE_T,
            MARKET_BASE_PRICES, MARKET_ABSORPTION_T,
            FLEET_NAME_POOL, HULL_MAX_PCT, HULL_MIN_PCT,
            DEPOT_BUILD_COST, REFINERY_BUILD_COST,
            QUALITY_PRESETS, GAME_VERSION,
        )
    except Exception as exc:
        return [f"Failed to import config for validation: {exc}"]

    # Units
    if not math.isfinite(MU_SUN) or MU_SUN <= 0:
        errors.append(f"MU_SUN must be positive finite, got {MU_SUN}")

    # Ships
    if not SHIP_CLASSES:
        errors.append("SHIP_CLASSES empty")
    for key, spec in SHIP_CLASSES.items():
        for field in ("capacity", "delta_v", "price", "refuel_rate"):
            val = spec.get(field)
            if not isinstance(val, (int, float)) or not math.isfinite(val) or val <= 0:
                errors.append(f"SHIP_CLASSES[{key}].{field} invalid: {val}")
        if spec.get("wear_factor", 1.0) <= 0:
            errors.append(f"SHIP_CLASSES[{key}].wear_factor must be >0")

    # Names pool unique
    if len(FLEET_NAME_POOL) != len(set(FLEET_NAME_POOL)):
        errors.append("FLEET_NAME_POOL contains duplicates")

    # Hull
    if not (0 < HULL_MIN_PCT < HULL_MAX_PCT <= 100):
        errors.append(f"Hull min/max invalid: min {HULL_MIN_PCT} max {HULL_MAX_PCT}")

    # Mining
    if not MINING_ORES:
        errors.append("MINING_ORES empty")
    for ore in MINING_ORES:
        if ore not in MINING_VEIN_SIZE_T:
            errors.append(f"Ore {ore} missing from MINING_VEIN_SIZE_T")
        if ore not in MARKET_BASE_PRICES:
            errors.append(f"Ore {ore} missing from MARKET_BASE_PRICES")
        if ore not in MARKET_ABSORPTION_T:
            errors.append(f"Ore {ore} missing from MARKET_ABSORPTION_T")

    # Market prices positive
    for ore, price in MARKET_BASE_PRICES.items():
        if price <= 0:
            errors.append(f"MARKET_BASE_PRICES[{ore}] must be >0, got {price}")

    # Depot / refinery costs
    if DEPOT_BUILD_COST <= 0:
        errors.append(f"DEPOT_BUILD_COST invalid {DEPOT_BUILD_COST}")
    if REFINERY_BUILD_COST <= 0:
        errors.append(f"REFINERY_BUILD_COST invalid {REFINERY_BUILD_COST}")

    # Quality presets have required keys
    required_q = {"belt", "trails", "sky", "labels", "orbit_alpha"}
    for qname, preset in QUALITY_PRESETS.items():
        missing = required_q - set(preset.keys())
        if missing:
            errors.append(f"QUALITY_PRESETS[{qname}] missing keys {missing}")

    # Version format
    if not GAME_VERSION or not isinstance(GAME_VERSION, str):
        errors.append(f"GAME_VERSION invalid {GAME_VERSION!r}")

    return errors


def validate_or_raise() -> None:
    errs = validate()
    if errs:
        raise ValueError("Config validation failed:\n" + "\n".join(f" - {e}" for e in errs))
