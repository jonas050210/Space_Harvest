"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


# --- mining: ore fingerprints, depletion, extraction modes -------------------
MINING_SEED = 20260826         # combined with the body key, deterministic
MINING_ORES = ("ice", "iron", "silver", "gold", "platinum", "components", "electronics",
               "thorite", "aurellium", "silicates", "obsidian", "helium3",
               "cobalt", "magnetite", "xenonite", "seedstock", "memory_glass")
# Vein size per ore in tonnes: after extracting one vein-size the yield is at
# 1/e, forcing expansion to fresh rocks while slow recovery keeps the game
# from dead-ending.
MINING_VEIN_SIZE_T = {"ice": 1200.0, "iron": 1600.0, "silver": 700.0,
                      "gold": 450.0, "platinum": 300.0, "components": 500.0, "electronics": 250.0,
                      "thorite": 380.0, "aurellium": 140.0,
                      "silicates": 900.0, "obsidian": 220.0, "helium3": 90.0,
                      "cobalt": 520.0, "magnetite": 640.0, "xenonite": 110.0,
                      "seedstock": 160.0, "memory_glass": 70.0}
# Campaign-only ore spawns, appended to a body's module-declared resources.
# The deep belt and the derelict hull carry radioactive thorite in their slag;
# aurellium exists ONLY in the comet -- the jackpot that makes the chase pay.
MINING_EXTRA_SPAWNS = {
    "deep_belt": ("thorite", "silicates", "cobalt"),
    "derelict_zone": ("thorite", "cobalt"),
    "comet_vigil": ("thorite", "aurellium", "helium3", "xenonite"),
    "trojan_field": ("ice", "silicates", "silver", "magnetite"),
    "cinder_moon": ("platinum", "obsidian", "gold", "magnetite"),
    "outer_reach": ("helium3", "thorite", "platinum", "xenonite"),
    "frost_ring": ("ice", "xenonite", "cobalt"),
    "metallic_belt": ("magnetite",),
    "ember_shoal": ("obsidian", "gold", "magnetite"),
    "l5_garden": ("ice", "silicates", "seedstock"),
    "hearthwreck": ("components", "electronics", "memory_glass", "thorite"),
    "night_well": ("helium3", "xenonite", "thorite"),
    "sungrazer": ("magnetite", "thorite", "helium3"),
    "vagrant": ("platinum", "xenonite", "cobalt"),
    "boreas": ("silver", "gold", "platinum"),
}
MINING_DRILL_YIELD_BONUS = 1.6   # core drilling multiplier per run
MINING_DRILL_WEAR_PCT = 6.0      # hull cost of drilling on every drilled run
MINING_LOW_HULL_YIELD_PCT = 40.0  # below this hull %, yield scales with hull
MINING_RECOVERY_TAU_DAYS = 2400.0  # e-folding time for depleted veins to recover
# Volatiles replenish much faster than metals: ices migrate and re-condense,
# so a mined-out ice field comes back within a few years instead of decades.
MINING_RECOVERY_TAU_BY_ORE = {"ice": 900.0}
INCIDENT_CHANCE_SCRAPE = 0.02      # per capture
INCIDENT_CHANCE_DRILL = 0.09       # per capture while core drilling
INCIDENT_LOW_HULL_FACTOR = 1.2     # extra chance = factor * max(0, 40-hull)/100
INCIDENT_CARGO_LOSS = 0.35         # fraction of the delivery lost to an incident

