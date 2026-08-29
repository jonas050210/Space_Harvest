"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


# --- refinery stations ----------------------------------------------------------
# A refinery smelts raw ore in a docked (waiting) ship's hold: components from
# iron+silver, electronics from gold. Refined stock sells far above raw ore,
# which is the whole economic reason to build one. The station crafts even
# while no ship is there only in tiny amounts -- it is a service, not a factory.
REFINERY_BUILD_COST = 4200.0
REFINERY_BATCHES_PER_DAY = 3.0
# Smelting passes run against a run's payload the moment the ship docks --
# this is the refinery's core service: the run arrives REFINED.
REFINERY_ARRIVAL_BATCHES = 14
REFINERY_RECIPES = (
    {"output": "components", "amount": 2.0, "input": {"iron": 3.0, "silver": 1.0}},
    {"output": "electronics", "amount": 2.0, "input": {"gold": 3.0}},
    {"output": "components", "amount": 3.0, "input": {"cobalt": 2.0, "magnetite": 2.0}},
    {"output": "electronics", "amount": 2.0, "input": {"xenonite": 1.0, "gold": 1.0}},
    {"output": "electronics", "amount": 3.0, "input": {"memory_glass": 1.0, "gold": 1.0}},
)

