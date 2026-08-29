"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


# --- upgrade parts (Earth parts market) ---------------------------------------
# Buy with T (tank) / Y (drill) / U (quarters) for a docked ship, P for a
# depot drone bay. Prices ride the same seasonal/noise economy as ore: buy
# tanks when the parts market is cheap. Escalating counts keep it a decision.
PARTS_CATALOG = {
    "tank": {"name": "Drop Tanks", "base_price": 1800.0, "delta_v": 3500.0, "max_per_ship": 2},
    "drill": {"name": "Deep Drill", "base_price": 2400.0, "mine_bonus": 0.25, "max_per_ship": 2},
    "quarters": {"name": "Crew Quarters", "base_price": 1500.0, "rest_bonus": 0.5, "max_per_ship": 1},
    "drones": {"name": "Depot Drone Bay", "base_price": 3200.0, "mine_per_day": 5.0, "max_per_depot": 2},
    # The aurellium super-part: comet loot becomes campaign power. Op-layer
    # trajectory-planning skill (like pilots), never a physics change.
    "navsuite": {"name": "Navigation Suite", "base_price": 5200.0, "refund": 0.05,
                 "max_per_ship": 1, "aurellium_t": 6},
    # Ore Scanner: richer assay / slight mine bonus (ops layer).
    "scanner": {"name": "Ore Scanner", "base_price": 2100.0, "mine_bonus": 0.12, "max_per_ship": 1},
    # Shield weave: less hull wear per burn.
    "shield": {"name": "Shield Weave", "base_price": 2800.0, "wear_factor": 0.75, "max_per_ship": 1},
    # Mag-clamps: hold capacity bump without changing ship class.
    "magclamp": {"name": "Mag-Clamps", "base_price": 1900.0, "capacity": 40.0, "max_per_ship": 2},
    "icebox": {"name": "Icebox Hold", "base_price": 1600.0, "capacity": 50.0, "max_per_ship": 2},
    "sail": {"name": "Solar Sail", "base_price": 2400.0, "wear_factor": 0.85, "max_per_ship": 1},
}
PARTS_PRICE_ESCALATION = 1.25
PARTS_SEASON_DAYS = {"tank": 300.0, "drill": 340.0, "quarters": 260.0, "drones": 400.0,
                     "navsuite": 600.0, "scanner": 320.0, "shield": 380.0, "magclamp": 290.0,
                     "icebox": 280.0, "sail": 410.0}

