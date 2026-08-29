"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


# --- Earth market: dynamic pricing ------------------------------------------
MARKET_BASE_PRICES = {  # credits per tonne
    "ice": 8.0, "iron": 12.0, "silver": 40.0, "gold": 90.0,
    "platinum": 220.0, "components": 65.0, "electronics": 160.0,
    "thorite": 70.0, "aurellium": 480.0,
    "silicates": 18.0, "obsidian": 310.0, "helium3": 520.0,
    "cobalt": 95.0, "magnetite": 55.0, "xenonite": 610.0,
    "seedstock": 140.0, "memory_glass": 720.0,
}
# Tonnes the Earth market absorbs before the price visibly sags; rare ores
# flood much faster, so dumping a hauler load of platinum crashes its price.
MARKET_ABSORPTION_T = {"ice": 400.0, "iron": 320.0, "silver": 140.0, "gold": 60.0,
                       "platinum": 30.0, "components": 80.0, "electronics": 40.0,
                       "thorite": 45.0, "aurellium": 12.0,
                       "silicates": 200.0, "obsidian": 22.0, "helium3": 10.0,
                       "cobalt": 55.0, "magnetite": 120.0, "xenonite": 8.0,
                       "seedstock": 28.0, "memory_glass": 6.0}
MARKET_FLOOD_HALF_LIFE_DAYS = 30.0
MARKET_SEASONAL_AMPLITUDE = 0.22
MARKET_SEASONAL_PERIOD_DAYS = {"ice": 240.0, "iron": 300.0, "silver": 360.0,
                               "gold": 420.0, "platinum": 480.0, "components": 390.0, "electronics": 450.0,
                               "thorite": 330.0, "aurellium": 540.0,
                               "silicates": 280.0, "obsidian": 400.0, "helium3": 600.0,
                               "cobalt": 350.0, "magnetite": 310.0, "xenonite": 620.0,
                               "seedstock": 365.0, "memory_glass": 700.0}
MARKET_NOISE_SIGMA = 0.05           # random-walk strength, per sqrt(day)
MARKET_NOISE_MEAN_REVERSION = 0.02  # per day toward demand 1.0
MARKET_PRICE_FLOOR_FRACTION = 0.15  # price never drops below this share of base
MARKET_HISTORY_SAMPLE_DAYS = 2.0
MARKET_HISTORY_POINTS = 240

