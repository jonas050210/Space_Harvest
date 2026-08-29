"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


# --- "Firsts": KSP-style one-shot milestones -------------------------------------
# (key, toast label, credit bonus, research bonus). Checked by the game layer
# every few frames against read-only campaign state; each fires exactly once.
FIRSTS = (
    ("first_dispatch", "First sowing -- a freighter leaves the barn", 250.0, 2.0),
    ("first_capture_belt", "First harvest: the inner belt", 200.0, 2.0),
    ("first_capture_metallic", "First harvest: the metallic belt", 350.0, 4.0),
    ("first_capture_deep", "First harvest: the deep belt", 700.0, 8.0),
    ("first_capture_derelict", "First harvest: the Derelict Zone", 900.0, 10.0),
    ("first_capture_aurelia", "First harvest: Aurelia orbit", 800.0, 8.0),
    ("first_capture_comet", "COMET HARVEST -- aurellium fields open", 2500.0, 40.0),
    ("first_depot", "First barn online -- depot refuelling", 500.0, 5.0),
    ("first_refinery", "First mill smelting", 600.0, 6.0),
    ("first_drones", "Field drones operational", 400.0, 4.0),
    ("full_return_1", "First full-hold harvest home", 300.0, 3.0),
    ("full_return_10", "Ten full holds -- a proper outfit", 1200.0, 12.0),
    ("mass_2500", "2,500 t hauled to the colony", 800.0, 8.0),
    ("mass_10000", "10,000 t -- the belt is a farm", 3000.0, 30.0),
    ("fleet_5", "Five ships under charter", 600.0, 6.0),
    ("rich_25k", "Treasury passes 25,000 cr", 0.0, 10.0),
    ("rich_100k", "Treasury passes 100,000 cr", 0.0, 25.0),
    ("thorite_1", "First thorite harvest", 500.0, 6.0),
    ("aurellium_1", "First aurellium sale -- Earth is stunned", 2000.0, 30.0),
    ("first_capture_trojan", "First harvest: Trojan Field (Aurelia L4)", 700.0, 8.0),
    ("first_capture_cinder", "First harvest: Cinder Moon", 900.0, 10.0),
    ("first_capture_outer", "First harvest: Outer Reach -- the far farm", 1500.0, 20.0),
    ("first_multihop", "First multi-stop delivery (refuel hop)", 800.0, 10.0),
    ("helium3_1", "First helium-3 harvest", 1200.0, 15.0),
    ("obsidian_1", "First cinder obsidian shipment", 900.0, 10.0),
    ("first_swarm", "First hundred-drone window harvest", 1000.0, 12.0),
    ("first_surface", "First surface survey of a field", 300.0, 4.0),
    ("first_system_map", "System chart opened -- the whole farm at once", 200.0, 2.0),
    ("first_survey", "First surface survey -- veins charted", 350.0, 5.0),
    ("first_isru_spike", "ISRU spike planted -- the barn drinks deeper", 500.0, 6.0),
    ("cobalt_1", "First cobalt shipment -- blue steel for Earth", 600.0, 8.0),
    ("magnetite_1", "First magnetite haul", 400.0, 5.0),
    ("xenonite_1", "First xenonite crystal — the lab goes quiet", 1800.0, 25.0),
    ("first_tanker", "Tanker commissioned — the barns will drink", 700.0, 8.0),
    ("first_observatory", "Field observatory online", 500.0, 10.0),
    ("first_drill_yard", "Drill yard chewing bedrock", 600.0, 8.0),
    ("first_capture_frost", "First harvest: Frost Ring", 1100.0, 14.0),
    ("first_capture_ember", "First harvest: Ember Shoal", 650.0, 8.0),
    ("first_capture_l5", "First harvest: L5 Garden — the quiet field", 700.0, 8.0),
    ("first_capture_hearthwreck", "HEARTHWRECK BOARDED — memory glass sings", 2200.0, 28.0),
    ("first_capture_night", "First harvest: Night Well", 1600.0, 18.0),
    ("first_capture_sungrazer", "First harvest: Sungrazer Field — hazard pay", 1200.0, 14.0),
    ("first_capture_vagrant", "First harvest: Vagrant — out of the plane", 2000.0, 24.0),
    ("first_capture_boreas", "First harvest: Boreas — the rim is farmed", 2400.0, 30.0),
    ("first_clipper", "Clipper commissioned — the far windows open", 800.0, 8.0),
    ("first_courser", "Courser commissioned — the rim is in reach", 1000.0, 12.0),
    ("first_argosy", "Argosy launched — a season in one hold", 900.0, 10.0),
    ("first_greenhouse", "Greenhouse dome fogging the glass", 550.0, 8.0),
    ("first_foundry", "Field foundry online", 600.0, 8.0),
    ("seedstock_1", "First seedstock shipment — Earth wants a garden", 900.0, 12.0),
    ("memory_glass_1", "First memory-glass crate — the archive blinks", 2000.0, 30.0),
    ("garden_40", "Garden score 40 — a world taking root", 1200.0, 15.0),
)



# --- science unlocks -------------------------------------------------------------
# Research points (from deliveries, Firsts, observatories) buy one-shot colony
# technologies. Effects are plain multipliers/discounts the game layer applies
# to existing systems -- the sim only ever sees generic numbers.
TECHS = (
    ("standard_contracts", "Standardised Contracts", 40, {"parts_discount": 0.15}),
    ("crew_rotation", "Crew Rotation Programme", 50, {"fatigue": 0.75}),
    ("isru_catalysts", "ISRU Catalysts", 55, {"depot_generation": 1.5}),
    ("plasma_lances", "Plasma Smelting Lances", 70, {"refinery": 1.5}),
    ("swarm_doctrine", "Swarm Doctrine", 80, {"swarm_yield": 1.35}),
    ("longshore_auto", "Longshore Automation", 60, {"depot_generation": 1.25}),
    ("cryo_tankers", "Cryo Tanker Protocols", 65, {"refuel_rate": 1.20}),
    ("deep_core_bits", "Deep-Core Drill Bits", 75, {"mine_bonus": 1.20}),
    ("xenon_capture", "Xenon Capture Nets", 90, {"swarm_yield": 1.15, "mine_bonus": 1.10}),
    ("greenhouse_lattice", "Greenhouse Lattice", 70, {"garden": 1.35, "life_solar": 1.10}),
    ("wreck_charter", "Wreck Charter Rights", 85, {"contract_reward": 1.20}),
    ("magnetic_sail", "Magnetic Sail Doctrine", 75, {"refuel_rate": 1.15}),
    ("memory_foundry", "Memory Foundry", 95, {"refinery": 1.25}),
)

