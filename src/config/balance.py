"""Balance analysis - ensures no ship class strictly dominates another.

Used by tests and by Game.__init__ validation. Not gameplay logic, just sanity.
"""

from __future__ import annotations

from typing import Dict, List, Tuple


def ship_metrics() -> Dict[str, Dict[str, float]]:
    """Compute derived metrics per ship class."""
    from .ships import SHIP_CLASSES
    metrics = {}
    for key, spec in SHIP_CLASSES.items():
        cap = float(spec["capacity"])
        dv = float(spec["delta_v"])
        price = float(spec["price"])
        refuel = float(spec["refuel_rate"])
        wear = float(spec["wear_factor"])
        # Cost efficiency: credits per tonne of capacity
        cost_per_t = price / max(cap, 1.0)
        # Range efficiency: dv per credit
        dv_per_credit = dv / max(price, 1.0)
        # Haul efficiency: capacity * dv (tonne-m/s per credit)
        haul_per_credit = (cap * dv) / max(price, 1.0)
        metrics[key] = {
            "capacity": cap,
            "delta_v": dv,
            "price": price,
            "refuel_rate": refuel,
            "wear_factor": wear,
            "cost_per_tonne": cost_per_t,
            "dv_per_credit": dv_per_credit,
            "haul_per_credit": haul_per_credit,
        }
    return metrics


def find_dominated_classes() -> List[Tuple[str, str, str]]:
    """Return list of (dominated, dominator, reason) where one class is strictly worse."""
    metrics = ship_metrics()
    dominated = []
    keys = list(metrics.keys())
    for i, a in enumerate(keys):
        for b in keys[i+1:]:
            ma = metrics[a]
            mb = metrics[b]
            # a dominated by b if b is better or equal on all key axes and strictly better on at least one
            # Axes: capacity, delta_v, refuel_rate, wear_factor (lower better), price (lower better)
            # We consider price inverted - lower is better
            a_better_axes = 0
            b_better_axes = 0
            # Compare capacity, dv, refuel (higher better), wear and price (lower better)
            if ma["capacity"] > mb["capacity"]:
                a_better_axes += 1
            elif mb["capacity"] > ma["capacity"]:
                b_better_axes += 1
            if ma["delta_v"] > mb["delta_v"]:
                a_better_axes += 1
            elif mb["delta_v"] > ma["delta_v"]:
                b_better_axes += 1
            if ma["refuel_rate"] > mb["refuel_rate"]:
                a_better_axes += 1
            elif mb["refuel_rate"] > ma["refuel_rate"]:
                b_better_axes += 1
            if ma["wear_factor"] < mb["wear_factor"]:
                a_better_axes += 1
            elif mb["wear_factor"] < ma["wear_factor"]:
                b_better_axes += 1
            if ma["price"] < mb["price"]:
                a_better_axes += 1
            elif mb["price"] < ma["price"]:
                b_better_axes += 1

            # If one has 0 better axes and the other has >0, it's dominated
            if a_better_axes == 0 and b_better_axes > 0:
                dominated.append((a, b, f"{b} strictly better on {b_better_axes} axes"))
            elif b_better_axes == 0 and a_better_axes > 0:
                dominated.append((b, a, f"{a} strictly better on {a_better_axes} axes"))
    return dominated


def validate_balance() -> List[str]:
    """Return balance warnings, empty if balanced."""
    warnings = []
    dominated = find_dominated_classes()
    for dom, by, reason in dominated:
        warnings.append(f"Ship class {dom} dominated by {by}: {reason}")
    # Check for extreme outliers
    metrics = ship_metrics()
    for key, m in metrics.items():
        if m["cost_per_tonne"] > 100:
            warnings.append(f"{key} cost_per_tonne very high: {m['cost_per_tonne']:.1f}")
        if m["wear_factor"] > 1.5:
            warnings.append(f"{key} wear_factor high: {m['wear_factor']}")
    return warnings
