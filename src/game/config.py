"""Central game constants and English content definitions."""

VERSION = "0.9.2"
GAME_NAME = "Asteroid Colony"

DIFFICULTY = {"easy": 0.7, "medium": 1.0, "hard": 1.4}
DEFAULT_DIFFICULTY = "medium"

FULLSCREEN = False
WINDOW_TYPE = "onscreen"  # Set to "none" for headless tests.
TICK_RATE = 60

RESOURCES = {
    "ice": {"color": (0.6, 0.9, 1.0), "name": "Ice", "value": 1},
    "iron": {"color": (0.7, 0.5, 0.3), "name": "Iron", "value": 2},
    "gold": {"color": (0.95, 0.85, 0.2), "name": "Gold", "value": 8},
    "silver": {"color": (0.85, 0.85, 0.9), "name": "Silver", "value": 5},
    "platinum": {"color": (0.9, 0.9, 0.95), "name": "Platinum", "value": 12},
    "energy": {"color": (1.0, 0.95, 0.4), "name": "Energy", "value": 0},
    "water": {"color": (0.3, 0.65, 1.0), "name": "Water", "value": 3},
    "components": {"color": (0.55, 0.6, 0.68), "name": "Components", "value": 6},
    "electronics": {"color": (0.3, 0.95, 0.8), "name": "Electronics", "value": 15},
}

MODULES = {
    "drone_bay": {"name": "Drone Bay", "cost": {"iron": 120, "ice": 60}, "energy_use": 2, "cap_boost": 4},
    "solar_panel": {"name": "Solar Panel", "cost": {"iron": 80, "ice": 30}, "energy_use": -6, "pop_boost": 0},
    "life_support": {"name": "Life Support", "cost": {"iron": 60, "ice": 80}, "energy_use": 2, "pop_boost": 5},
    "refinery": {"name": "Refinery", "cost": {"silver": 80, "gold": 40}, "energy_use": 3, "bonus": 0.20},
    "storage": {"name": "Storage", "cost": {"iron": 100, "ice": 40}, "energy_use": 1, "cap_boost": 250},
    "shield": {"name": "Shield Generator", "cost": {"gold": 60, "platinum": 30}, "energy_use": 4, "shield_on": True},
    "trade": {"name": "Trade Terminal", "cost": {"platinum": 30, "silver": 40}, "energy_use": 2, "trade_on": True},
}

# Machine costs increase exponentially with each purchase.
MACHINES = {
    "mining_drill": {"name": "Mining Drill", "base_cost": {"ice": 30, "iron": 50}, "multiplier": 1.3, "output_per_tick": {"iron": 2, "ice": 1}, "energy_use": 1},
    "refinery": {"name": "Mini Refinery", "base_cost": {"ice": 50, "gold": 20}, "multiplier": 1.35, "output_per_tick": {"gold": 1, "silver": 1}, "energy_use": 2},
    "auto_transporter": {"name": "Auto Transporter", "base_cost": {"iron": 80, "silver": 30}, "multiplier": 1.4, "output_per_tick": {"iron": 3}, "energy_use": 3},
}

DRONE_UPGRADES = {
    "speed": {"levels": 4, "cost": {"iron": 40, "ice": 20}},
    "cargo": {"levels": 5, "cost": {"iron": 60, "ice": 30}},
    "mining": {"levels": 5, "cost": {"silver": 30, "gold": 15}},
}

DRONE_ROLES = {
    "miner": {
        "name": "Miner",
        "description": "Extracts resources quickly from nearby high-value asteroids.",
        "mining_multiplier": 1.35,
        "cargo_multiplier": 1.0,
    },
    "hauler": {
        "name": "Hauler",
        "description": "Carries larger loads and returns to the station faster.",
        "mining_multiplier": 0.75,
        "cargo_multiplier": 2.0,
        "return_speed_multiplier": 1.35,
    },
    "scout": {
        "name": "Scout",
        "description": "Scans distant asteroids and favors rare resources.",
        "mining_multiplier": 0.55,
        "cargo_multiplier": 0.8,
        "scan_multiplier": 1.6,
    },
}

RESEARCH = {
    "drone_specialization": {
        "name": "Drone Specialization",
        "description": "Unlock Miner, Hauler, and Scout drone assignments.",
        "cost": 12,
        "requires": [],
    },
    "logistics_protocols": {
        "name": "Logistics Protocols",
        "description": "Increases storage capacity and reduces delivery losses.",
        "cost": 20,
        "requires": ["drone_specialization"],
    },
    "deep_space_scanning": {
        "name": "Deep-Space Scanning",
        "description": "Scouts identify distant rare asteroids and earn bonus research.",
        "cost": 30,
        "requires": ["drone_specialization"],
    },
    "automated_refining": {
        "name": "Automated Refining",
        "description": "Refineries produce 25% more output.",
        "cost": 45,
        "requires": ["logistics_protocols"],
    },
}

PRODUCTION_RECIPES = {
    "water": {"name": "Water Processing", "input": {"ice": 3}, "output": {"water": 2}, "module": "life_support"},
    "components": {"name": "Component Fabrication", "input": {"iron": 4}, "output": {"components": 1}, "module": "refinery"},
    "electronics": {"name": "Electronics Assembly", "input": {"gold": 1, "silver": 2, "components": 1}, "output": {"electronics": 1}, "module": "refinery", "research": "automated_refining"},
}

ASTEROID_REGIONS = {
    "inner_belt": {"name": "Inner Belt", "distance": (10, 18), "resources": ["ice", "iron", "silver"]},
    "metallic_belt": {"name": "Metallic Belt", "distance": (18, 30), "resources": ["iron", "silver", "gold"]},
    "deep_belt": {"name": "Deep Belt", "distance": (30, 46), "resources": ["gold", "silver", "platinum"]},
}

# Advanced station structures unlock through research and give the colony a distinct silhouette.
MODULES.update({
    "research_observatory": {"name": "Research Observatory", "cost": {"iron": 140, "electronics": 4}, "energy_use": 3, "research_bonus": 0.4, "requires_research": "artifact_analysis"},
    "orbital_trade_hub": {"name": "Orbital Trade Hub", "cost": {"iron": 180, "components": 8, "gold": 25}, "energy_use": 4, "trade_on": True, "requires_research": "planetary_trade_routes"},
    "deep_belt_outpost": {"name": "Deep-Belt Outpost", "cost": {"iron": 220, "platinum": 20, "electronics": 8}, "energy_use": 5, "requires_research": "deep_space_scanning"},
})

RESEARCH.update({
    "planetary_trade_routes": {
        "name": "Planetary Trade Routes",
        "description": "Unlocks orbital trade infrastructure and visiting freight traffic.",
        "cost": 55,
        "requires": ["logistics_protocols"],
    },
    "artifact_analysis": {
        "name": "Artifact Analysis",
        "description": "Unlocks research observatories and derelict-zone discoveries.",
        "cost": 65,
        "requires": ["deep_space_scanning"],
    },
})

REGIONS = {
    "inner_belt": {"name": "Inner Belt", "description": "Reliable starter mining close to the colony.", "requires": None, "travel_cost": {}, "palette": (0.9, 0.95, 1.0)},
    "metallic_belt": {"name": "Metallic Belt", "description": "Dense metal fields with stronger trade opportunities.", "requires": "logistics_protocols", "travel_cost": {"energy": 3}, "palette": (0.72, 0.8, 0.96)},
    "deep_belt": {"name": "Deep Belt", "description": "Rare metals, distant operations, and anomalous machinery.", "requires": "deep_space_scanning", "travel_cost": {"energy": 6}, "palette": (0.62, 0.43, 0.92)},
    "gas_giant_orbit": {"name": "Aurelia Orbit", "description": "High-value trade routes around the ringed gas giant.", "requires": "planetary_trade_routes", "travel_cost": {"energy": 8}, "palette": (0.64, 0.4, 0.82)},
    "derelict_zone": {"name": "Derelict Zone", "description": "Abandoned industrial ruins containing recoverable artifacts.", "requires": "artifact_analysis", "travel_cost": {"energy": 10}, "palette": (0.48, 0.2, 0.34)},
}

# Region modifiers make each destination an economic decision rather than a palette swap.
REGION_ECONOMY = {
    "inner_belt": {"machine_output": 1.0, "trade_value": 1.0},
    "metallic_belt": {"machine_output": 1.12, "trade_value": 1.0},
    "deep_belt": {"machine_output": 1.05, "trade_value": 1.20},
    "gas_giant_orbit": {"machine_output": 0.9, "trade_value": 1.45},
    "derelict_zone": {"machine_output": 0.82, "trade_value": 1.1},
}
