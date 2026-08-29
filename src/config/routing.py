"""Auto-split from __init__.py - see __init__.py for aggregation."""

from __future__ import annotations


# --- multi-stop delivery planner (KSP-style refuel hops) --------------------
# Planner may insert player depots as intermediate stops so a ship that cannot
# afford a direct round trip still reaches deep fields. Max hops caps the
# search; cost_slack lets a slightly dearer hop route win if it opens sooner.
ROUTE_MAX_HOPS = 2
ROUTE_COST_SLACK = 1.08          # hop route may cost up to 8% more than direct
ROUTE_PREFER_DEPOT_HOPS = True   # default standing policy

