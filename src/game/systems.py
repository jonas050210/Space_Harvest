"""Game tick systems - extracted from main.py God Object.

Each function takes Game instance and dt, mutates game state.
Pure extraction, no behavior change.
"""

from __future__ import annotations

from src.config import (
    GARDEN_SCORE_PER_ICE,
    LIFE_ELECTROLYSIS_ENERGY_PER_O2,
    LIFE_ELECTROLYSIS_WATER_PER_O2,
    LIFE_FOOD_PER_CREW_DAY,
    LIFE_HYDROPONICS_ENERGY_PER_FOOD,
    LIFE_HYDROPONICS_WATER_PER_FOOD,
    LIFE_ICE_MELT_RATE_PER_DAY,
    LIFE_ICE_TO_WATER_YIELD,
    LIFE_OXYGEN_PER_CREW_DAY,
    LIFE_SHORTAGE_MORALE_DRAIN_PER_DAY,
    LIFE_SOLAR_ENERGY_PER_DAY,
    LIFE_START_FOOD,
    LIFE_START_OXYGEN,
    LIFE_START_WATER,
    LIFE_WATER_PER_CREW_DAY,
    LIFE_WATER_RECYCLE_FRACTION,
)


def tick_life_support(game, dt_days: float) -> None:
    """Consume and produce oxygen, food and water for the whole crew."""
    state = game.colony.state
    resources = state.setdefault("resources", {})
    crew_count = sum(len(roster) for roster in game.sim.crew.values())
    if crew_count == 0:
        return

    max_energy = state.get("max_energy", 30)
    solar = LIFE_SOLAR_ENERGY_PER_DAY * float(game.sim.tech_mults.get("life_solar", 1.0))
    resources["energy"] = min(max_energy, resources.get("energy", 0.0) + solar * dt_days)
    energy_used = 0.0

    water_low = 0.5 * LIFE_START_WATER
    if resources.get("water", 0.0) < water_low and resources.get("ice", 0.0) > 0.0:
        melt = min(LIFE_ICE_MELT_RATE_PER_DAY * dt_days,
                   resources.get("ice", 0.0),
                   max(0.0, water_low - resources.get("water", 0.0)) / LIFE_ICE_TO_WATER_YIELD)
        resources["ice"] = resources.get("ice", 0.0) - melt
        resources["water"] = resources.get("water", 0.0) + melt * LIFE_ICE_TO_WATER_YIELD
        energy_used += 0.1 * melt

    need_o2 = crew_count * LIFE_OXYGEN_PER_CREW_DAY * dt_days
    need_food = crew_count * LIFE_FOOD_PER_CREW_DAY * dt_days
    need_water = crew_count * LIFE_WATER_PER_CREW_DAY * dt_days

    want_o2 = need_o2 + max(0.0, LIFE_START_OXYGEN - resources.get("oxygen", 0.0))
    spare_water = max(0.0, resources.get("water", 0.0) - need_water)
    budget = max(0.0, resources.get("energy", 0.0))
    made_o2 = min(want_o2,
                  spare_water / LIFE_ELECTROLYSIS_WATER_PER_O2,
                  budget / LIFE_ELECTROLYSIS_ENERGY_PER_O2)
    resources["water"] = resources.get("water", 0.0) - made_o2 * LIFE_ELECTROLYSIS_WATER_PER_O2
    resources["energy"] = resources.get("energy", 0.0) - made_o2 * LIFE_ELECTROLYSIS_ENERGY_PER_O2
    energy_used += made_o2 * LIFE_ELECTROLYSIS_ENERGY_PER_O2
    resources["oxygen"] = resources.get("oxygen", 0.0) + made_o2

    want_food = need_food + max(0.0, LIFE_START_FOOD - resources.get("food", 0.0))
    spare_water = max(0.0, resources.get("water", 0.0) - need_water)
    budget = max(0.0, resources.get("energy", 0.0))
    water_per_food = LIFE_HYDROPONICS_WATER_PER_FOOD * game.sim.botanist_water_factor()
    made_food = min(want_food,
                    spare_water / water_per_food,
                    budget / LIFE_HYDROPONICS_ENERGY_PER_FOOD)
    resources["water"] = resources.get("water", 0.0) - made_food * water_per_food
    resources["energy"] = resources.get("energy", 0.0) - made_food * LIFE_HYDROPONICS_ENERGY_PER_FOOD
    energy_used += made_food * LIFE_HYDROPONICS_ENERGY_PER_FOOD
    resources["food"] = resources.get("food", 0.0) + made_food

    water_used = need_water + made_o2 * LIFE_ELECTROLYSIS_WATER_PER_O2 + made_food * LIFE_HYDROPONICS_WATER_PER_FOOD
    resources["oxygen"] = max(0.0, resources.get("oxygen", 0.0) - need_o2)
    resources["food"] = max(0.0, resources.get("food", 0.0) - need_food)
    resources["water"] = max(0.0, resources.get("water", 0.0) - need_water)
    resources["water"] = resources.get("water", 0.0) + water_used * LIFE_WATER_RECYCLE_FRACTION

    game._life_shortage_flag = (
        resources.get("oxygen", 0.0) <= 0.0 or resources.get("food", 0.0) <= 0.0
    )
    if game._life_shortage_flag:
        game.sim.apply_hardship(LIFE_SHORTAGE_MORALE_DRAIN_PER_DAY * dt_days)

    reference = max(1.0, LIFE_SOLAR_ENERGY_PER_DAY * 4.0)
    load = 0.15 + 0.6 * (energy_used / dt_days) / reference
    game.power_load = min(1.0, max(0.05, load))


def tick_garden(game, dt_days: float) -> None:
    """Greenhouse domes drink colony ice and raise garden score."""
    if dt_days <= 0.0:
        return
    want = 0.0
    if hasattr(game.sim, "tick_garden_ice"):
        want = float(game.sim.tick_garden_ice(dt_days))
    if want <= 0.0:
        return
    resources = game.colony.state.setdefault("resources", {})
    drink = min(float(resources.get("ice", 0.0)), want)
    if drink <= 0.0:
        return
    resources["ice"] = float(resources.get("ice", 0.0)) - drink
    garden_mult = float(game.sim.tech_mults.get("garden", 1.0))
    game.colony.state["garden_score"] = (
        float(game.colony.state.get("garden_score", 0.0))
        + drink * GARDEN_SCORE_PER_ICE * garden_mult
    )


def tick_contracts(game) -> None:
    """Post offers, honour decisions, retire overdue and stale paper."""
    recent = sorted(ore for ore, day in game._recent_deliveries.items()
                    if game.market.day - day < 1200.0)
    if not recent:
        recent = sorted(game.colony.state.get("logistics", {}).get("lifetime_delivered", {}))
    offer = game.contracts.maybe_offer(recent)
    if offer is not None and not game.headless:
        game.say(
            f"OFFER from {offer.faction}: {offer.tonnes:,.0f} t of {offer.resource} "
            f"by day {offer.deadline_day:,.0f} for {offer.reward_credits:,.0f} cr. "
            "B to accept, V to decline.",
            seconds=9.0,
        )
    if game.headless:
        for pending in list(game.contracts.pending):
            if pending.resource in recent and len(game.contracts.active) < 2:
                game.contracts.accept(pending.id)
    for withdrawn in game.contracts.expire_pending():
        if not game.headless:
            game.say(f"{withdrawn.faction} withdrew its offer for {withdrawn.resource}.")
    for contract in game.contracts.expire_overdue():
        if not game.headless:
            game.say(
                f"{contract.faction} cancelled its order for {contract.resource} "
                f"-- standing {game.contracts.reputation[contract.faction]:+.0f}.",
                seconds=8.0,
            )
