"""Economy actions - extracted from main.py God Object."""

from __future__ import annotations

from src.colony import state as colony_state
from src.config import (
    LIFE_ICE_RESERVE_T,
    MARKET_BASE_PRICES,
    PARTS_CATALOG,
    SHIP_CLASSES,
    TECHS,
)


def sell_all(game, fraction: float = 1.0) -> None:
    fraction = max(0.0, min(1.0, float(fraction)))
    resources = game.colony.state.get("resources", {})
    lots: dict[str, float] = {}
    for res, amount in resources.items():
        if res not in MARKET_BASE_PRICES or amount < 1.0:
            continue
        if res == "ice":
            amount = max(0.0, amount - LIFE_ICE_RESERVE_T)
        amount = float(amount) * fraction
        if amount >= 1.0:
            lots[res] = amount
    if not lots:
        game.say("No ore in colony storage worth selling (ice reserve held back).")
        return
    multiplier = game.contracts.price_multiplier()
    proceeds, sold = game.market.sell(lots)
    proceeds *= multiplier
    colony_state.add_resources(game.colony.state, {res: -amount for res, amount in sold.items()})
    game.credits += proceeds
    game._tut["sold"] = True
    game.sim.crew_payday()
    detail = ", ".join(f"{res} {amount:,.0f} t" for res, amount in sorted(sold.items()))
    note = f" (Earth standing x{multiplier:.2f})" if abs(multiplier - 1.0) > 0.005 else ""
    game.say(f"Sold {detail} to Earth for {proceeds:,.0f} cr{note}.", seconds=8.0)
    # Track recent deliveries for contract offers
    for ore in sold:
        game._recent_deliveries[ore] = game.market.day


def buy_ship_class(game, cls_key: str) -> None:
    if cls_key not in SHIP_CLASSES:
        game.say(f"Unknown ship class '{cls_key}'.")
        return
    spec = SHIP_CLASSES[cls_key]
    if game.credits < spec["price"]:
        game.say(
            f"A {spec['name']} costs {spec['price']:,.0f} cr; "
            f"the treasury holds {game.credits:,.0f} cr."
        )
        return
    ship, message = game.sim.buy_ship(cls_key)
    if ship is None:
        game.say(message)
        return
    game.credits -= spec["price"]
    game._tut["bought"] = True
    game.say(f"{message} Bill: {spec['price']:,.0f} cr.", seconds=8.0)


def buy_part(game, part_key: str) -> None:
    info = PARTS_CATALOG.get(part_key)
    if info is None or part_key == "drones":
        game.say("Unknown part.")
        return
    ship = game._best_part_ship()
    if ship is None:
        game.say("No ship is docked at the colony for a refit.")
        return
    owned = sum(game.sim.upgrades.get(s.name, {}).get(part_key, 0) for s in game.sim.ships)
    price = game.market.part_price(part_key, owned) * (1.0 - game._parts_discount)
    if game.credits < price:
        game.say(f"{info['name']} costs {price:,.0f} cr; treasury {game.credits:,.0f} cr.")
        return
    aurellium_t = float(info.get("aurellium_t", 0.0))
    if aurellium_t > 0.0:
        resources = game.colony.state.get("resources", {})
        if resources.get("aurellium", 0.0) < aurellium_t:
            game.say(f"The {info['name']} needs {aurellium_t:.0f} t aurellium -- "
                     "only Comet Vigil carries it.")
            return
    ok, message = game.sim.install_part(ship.name, part_key)
    if not ok:
        game.say(message)
        return
    game.credits -= price
    if aurellium_t > 0.0:
        colony_state.add_resources(game.colony.state, {"aurellium": -aurellium_t})
    game._play_alert("build")
    note = f" and {aurellium_t:.0f} t aurellium" if aurellium_t else ""
    game.say(f"{message} Bill {price:,.0f} cr{note}.", seconds=7.0)


def buy_tech(game) -> None:
    research = game.colony.state.get("research_points", 0.0)
    for key, name, cost, _effects in TECHS:
        if key in game.techs:
            continue
        if research < cost:
            game.say(f"{name} needs {cost:.0f} RP; have {research:,.0f} RP.")
            return
        game.colony.state["research_points"] = research - cost
        game.techs.add(key)
        game._apply_techs()
        game.say(f"RESEARCH COMPLETE: {name}.", seconds=7.0)
        return
    game.say("All technologies already unlocked.")


def buy_drone_bay(game) -> None:
    """Install a drone bay at the selected target's depot."""
    target = game.hud.selected_target() if game.hud is not None else "deep_belt"
    depot = game.sim.depots.get(target)
    if depot is None:
        game.say("Build a depot there first (R).")
        return
    owned = depot.upgrades.get("drones", 0)
    price = game.market.part_price("drones", owned) * (1.0 - getattr(game, "_parts_discount", 0.0))
    if game.credits < price:
        game.say(f"A drone bay costs {price:,.0f} cr; treasury {game.credits:,.0f} cr.")
        return
    ok, msg = game.sim.install_depot_part(target, "drones")
    if not ok:
        game.say(msg)
        return
    game.credits -= price
    game._play_alert("build")
    game.say(f"{msg} Bill {price:,.0f} cr.", seconds=7.0)


def build_depot_selected(game) -> None:
    """Build (or upgrade) a refuel depot at the selected body.

    Headless mode has no selection, so it defaults to the deep belt --
    the depot site that unlocks the far network.
    """
    target = game.hud.selected_target() if game.hud is not None else "deep_belt"
    cost = game.sim.depot_upgrade_cost(target)
    if game.credits < cost:
        body_name = game.sim.bodies.get(target).name if target in game.sim.bodies else target
        game.say(f"A depot at {body_name} costs {cost:,.0f} cr; the treasury holds {game.credits:,.0f} cr.")
        return
    ok, msg = game.sim.build_depot(target)
    if not ok:
        game.say(msg)
        return
    game.credits -= cost
    game._play_alert("build")
    game.say(f"{msg} Bill {cost:,.0f} cr.", seconds=8.0)
