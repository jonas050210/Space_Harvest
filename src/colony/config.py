"""Colony-economy constants shared with the orbital shell.

Only the keys the live game reads remain. The full upstream builder catalogue
lived here once; it was trimmed when Space Harvest became the product.
"""

VERSION = "1.4.0"
GAME_NAME = "Space Harvest"

DIFFICULTY = {"easy": 0.7, "medium": 1.0, "hard": 1.4}
DEFAULT_DIFFICULTY = "medium"

RESOURCES = {
    "ice": {"name": "Ice", "value": 1},
    "iron": {"name": "Iron", "value": 2},
    "gold": {"name": "Gold", "value": 8},
    "silver": {"name": "Silver", "value": 5},
    "platinum": {"name": "Platinum", "value": 12},
    "energy": {"name": "Energy", "value": 0},
    "water": {"name": "Water", "value": 3},
    "components": {"name": "Components", "value": 6},
    "electronics": {"name": "Electronics", "value": 15},
    "thorite": {"name": "Thorite", "value": 10},
    "aurellium": {"name": "Aurellium", "value": 40},
    "cobalt": {"name": "Cobalt", "value": 12},
    "magnetite": {"name": "Magnetite", "value": 7},
    "xenonite": {"name": "Xenonite", "value": 50},
}

# Research tree kept so logistics capacity bonuses still resolve.
RESEARCH = {
    "drone_specialization": {
        "name": "Drone Specialization",
        "description": "Unlock specialised drone assignments.",
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
        "description": "Scouts identify distant rare asteroids.",
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

MODULES = {
    "drone_bay": {"name": "Drone Bay", "cost": {"iron": 120, "ice": 60}, "energy_use": 2},
    "solar_panel": {"name": "Solar Panel", "cost": {"iron": 80, "ice": 30}, "energy_use": -6},
    "storage": {"name": "Storage", "cost": {"iron": 100, "ice": 40}, "energy_use": 1},
}

PRODUCTION_RECIPES = {
    "water": {"name": "Water Processing", "input": {"ice": 3}, "output": {"water": 2}, "module": "life_support"},
    "components": {"name": "Component Fabrication", "input": {"iron": 4}, "output": {"components": 1}, "module": "refinery"},
    "electronics": {
        "name": "Electronics Assembly",
        "input": {"gold": 1, "silver": 2, "components": 1},
        "output": {"electronics": 1},
        "module": "refinery",
        "research": "automated_refining",
    },
}
