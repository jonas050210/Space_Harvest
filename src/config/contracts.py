"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


# --- Earth faction contracts --------------------------------------------------
CONTRACT_FACTIONS = ("Terran Metals Guild", "Luna Water Authority", "Ceres Prospecting Co.")
CONTRACT_OFFER_PERIOD_DAYS = 70.0
CONTRACT_MAX_ACTIVE = 2
CONTRACT_TONNES_RANGE = (60.0, 260.0)
# Deadlines must match the network's rhythm: a round trip takes 500-700 days
# with windows and layovers, so anything shorter is a toll on standing, not a
# game.
CONTRACT_DEADLINE_DAYS = (420.0, 720.0)
CONTRACT_REWARD_MULTIPLIER_RANGE = (1.15, 1.45)  # x market price at offering
CONTRACT_REP_ON_COMPLETE = 12.0
CONTRACT_REP_ON_FAIL = 18.0
REPUTATION_PRICE_BONUS = 0.06  # max sell-price swing at +/-100 average standing

