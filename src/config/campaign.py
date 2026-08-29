"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


# --- the comet ----------------------------------------------------------------
# "Vigil" is a long-period comet: perihelion inside the inner belt, aphelion
# deep beyond Aurelia. Its windows are rare and its arrival moves FAST, so
# captures there are brutally expensive -- depot-assisted runs shine. The ore
# is the jackpot: primordial ices and platinum-group metal from the slag crust.
COMET_KEY = "comet_vigil"
COMET_ELEMENTS = {"a": 4.45, "e": 0.80, "i_deg": 12.0, "raan_deg": 210.0,
                  "argp_deg": 15.0, "nu_deg": 170.0}
COMET_VEIN_BONUS = 1.0     # multiplier on its per-ore vein sizes
COMET_TAIL_AU = 0.55       # tail sprite length at perihelion (scene-side)


# --- campaign deep fields (installed by OpsSimulation, not the module BODIES table) ---
# Trojan Field sits near Aurelia's L4; Cinder is a volcanic moon-analogue on a
# tight Aurelia-like orbit; Outer Reach is the multi-hop endgame rock.
CAMPAIGN_BODIES = {
    "trojan_field": {
        "name": "Trojan Field",
        "elements": {"a": 2.80, "e": 0.04, "i_deg": 2.2, "raan_deg": 40.0,
                     "argp_deg": 20.0, "nu_deg": 330.0},  # ~L4 leading Aurelia
        "radius_km": 14.0, "soi_km": 32000.0,
        "palette": (0.78, 0.88, 0.72),
        "resources": ("ice", "silicates", "silver"),
        "description": "Aurelia L4 trojans -- stable ice and silicate fields.",
        "render_scale": 0.7,
    },
    "cinder_moon": {
        "name": "Cinder Moon",
        "elements": {"a": 2.95, "e": 0.08, "i_deg": 5.5, "raan_deg": 55.0,
                     "argp_deg": 100.0, "nu_deg": 40.0},
        "radius_km": 9.0, "soi_km": 22000.0,
        "palette": (0.92, 0.35, 0.22),
        "resources": ("platinum", "obsidian", "gold"),
        "description": "Volcanic rock -- hazard-rich, obsidian and platinum veins.",
        "render_scale": 0.5,
    },
    "outer_reach": {
        "name": "Outer Reach",
        "elements": {"a": 5.10, "e": 0.22, "i_deg": 9.0, "raan_deg": 280.0,
                     "argp_deg": 160.0, "nu_deg": 20.0},
        "radius_km": 22.0, "soi_km": 50000.0,
        "palette": (0.35, 0.55, 0.95),
        "resources": ("helium3", "thorite", "platinum", "xenonite"),
        "description": "Far-system prospect -- multi-hop depot runs required.",
        "render_scale": 0.85,
    },
    "frost_ring": {
        "name": "Frost Ring",
        "elements": {"a": 4.20, "e": 0.14, "i_deg": 7.5, "raan_deg": 190.0,
                     "argp_deg": 80.0, "nu_deg": 100.0},
        "radius_km": 16.0, "soi_km": 38000.0,
        "palette": (0.70, 0.88, 1.0),
        "resources": ("ice", "xenonite", "cobalt"),
        "description": "Icy shepherd ring — xenonite snow and cobalt slag.",
        "render_scale": 0.65,
    },
    "ember_shoal": {
        "name": "Ember Shoal",
        "elements": {"a": 1.72, "e": 0.09, "i_deg": 3.8, "raan_deg": 118.0,
                     "argp_deg": 40.0, "nu_deg": 200.0},
        "radius_km": 11.0, "soi_km": 26000.0,
        "palette": (0.95, 0.42, 0.18),
        "resources": ("obsidian", "gold", "iron"),
        "description": "Inner volcanic shoal — cheap windows, hot rock.",
        "render_scale": 0.55,
    },
    "l5_garden": {
        "name": "L5 Garden",
        "elements": {"a": 2.80, "e": 0.04, "i_deg": 2.2, "raan_deg": 40.0,
                     "argp_deg": 20.0, "nu_deg": 150.0},  # ~L5 trailing Aurelia
        "radius_km": 13.0, "soi_km": 30000.0,
        "palette": (0.45, 0.82, 0.55),
        "resources": ("ice", "silicates", "seedstock"),
        "description": "Aurelia L5 — quiet ice and the seedstock Earth will pay for.",
        "render_scale": 0.68,
    },
    "hearthwreck": {
        "name": "Hearthwreck",
        "elements": {"a": 5.65, "e": 0.31, "i_deg": 11.0, "raan_deg": 300.0,
                     "argp_deg": 175.0, "nu_deg": 55.0},
        "radius_km": 18.0, "soi_km": 42000.0,
        "palette": (0.62, 0.55, 0.48),
        "resources": ("components", "electronics", "memory_glass"),
        "description": "A derelict generation ship. Multi-hop salvage. Memory glass only here.",
        "render_scale": 0.9,
    },
    "night_well": {
        "name": "Night Well",
        "elements": {"a": 6.40, "e": 0.18, "i_deg": 8.2, "raan_deg": 15.0,
                     "argp_deg": 250.0, "nu_deg": 10.0},
        "radius_km": 20.0, "soi_km": 48000.0,
        "palette": (0.22, 0.28, 0.48),
        "resources": ("helium3", "xenonite", "thorite"),
        "description": "A dark well past Outer Reach. Clippers and barns, or stay home.",
        "render_scale": 0.8,
    },
    # -- The Far Charter (v1.6): the empty inner system, the plane, and the rim --
    "sungrazer": {
        "name": "Sungrazer Field",
        "elements": {"a": 0.95, "e": 0.28, "i_deg": 4.0, "raan_deg": 25.0,
                     "argp_deg": 310.0, "nu_deg": 140.0},
        "radius_km": 10.0, "soi_km": 24000.0,
        "palette": (0.96, 0.66, 0.22),
        "resources": ("magnetite", "thorite", "helium3"),
        "description": "Sun-skimming slag. Cheap windows, hellish flares, helium-3 baked in.",
        "render_scale": 0.5,
    },
    "vagrant": {
        "name": "Vagrant",
        "elements": {"a": 3.05, "e": 0.12, "i_deg": 48.0, "raan_deg": 95.0,
                     "argp_deg": 210.0, "nu_deg": 240.0},
        "radius_km": 15.0, "soi_km": 34000.0,
        "palette": (0.40, 0.78, 0.72),
        "resources": ("platinum", "xenonite", "cobalt"),
        "description": "A planetesimal knocked out of the plane. Brutal plane-change burns.",
        "render_scale": 0.7,
    },
    "boreas": {
        "name": "Boreas",
        "elements": {"a": 8.40, "e": 0.06, "i_deg": 2.6, "raan_deg": 150.0,
                     "argp_deg": 90.0, "nu_deg": 200.0},
        "radius_km": 52000.0, "soi_km": 4.0e6,
        "palette": (0.55, 0.62, 0.95),
        "resources": ("silver", "gold", "platinum"),
        "description": "A cold giant on the far rim. Premium freight beyond the last barn.",
        "render_scale": 2.2,
    },
}


