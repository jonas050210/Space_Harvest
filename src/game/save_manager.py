"""Save/load management - extracted from main.py."""

from __future__ import annotations

import os

from src.campaign import campaign_blob
from src.colony import savegame as colony_savegame
from src.config import GAME_VERSION


SAVE_VERSION = 3


def save_game(game, slot: str = "quick") -> None:
    payload = {
        "version": game.SAVE_VERSION,
        "credits": game.credits,
        "auto_repair": game.auto_repair,
        "market": game.market.to_json(),
        "contracts": game.contracts.to_json(),
        "firsts": dict(game.firsts),
        "techs": sorted(game.techs),
        "colony": game.colony.state,
        "sim": game.sim.to_json(),
        "campaign": campaign_blob(game),
        "game_version": GAME_VERSION,
    }
    path = colony_savegame.save_slot(slot, payload)
    game._tut["saved"] = True
    game.say(f"Game saved ({os.path.basename(path)}).")


def load_game(game, slot: str = "quick") -> None:
    from src.market import Contracts, Market
    from src.ops.simulation import OpsSimulation

    data = colony_savegame.load_slot(slot)
    if not data:
        game.say(f"No save found in slot '{slot}'.")
        return

    # Version gate
    version = int(data.get("version", 0) or 0)
    if version > game.SAVE_VERSION:
        game.say(f"Save version {version} newer than game {game.SAVE_VERSION} - update required.")
        return
    if version < 2:
        game.say(f"Save version {version} too old - pre-1.5 saves not supported.")
        return
    if version == 2:
        game.say("Save version 2 (pre-1.5) - refusing to misload. Start new harvest.")

    try:
        game.credits = float(data.get("credits", game.credits))
        game.auto_repair = bool(data.get("auto_repair", True))
        game.firsts = dict(data.get("firsts", {}))
        game.techs = set(data.get("techs", []))

        colony_data = data.get("colony")
        if colony_data:
            game.colony.state = colony_data

        sim_data = data.get("sim")
        if sim_data:
            game.sim = OpsSimulation.from_json(sim_data)

        market_data = data.get("market")
        if market_data:
            game.market = Market.from_json(market_data)

        contracts_data = data.get("contracts")
        if contracts_data:
            game.contracts = Contracts.from_json(contracts_data, game.market)

        campaign_data = data.get("campaign", {})
        if campaign_data:
            game.difficulty = campaign_data.get("difficulty", game.difficulty)
            game.victory_mode = campaign_data.get("victory", game.victory_mode)
            game.victory_achieved = campaign_data.get("victory_achieved")
            game.clean_run_streak = int(campaign_data.get("clean_run_streak", 0))
            game.ironman_days = float(campaign_data.get("ironman_days", 0.0))

        game._apply_techs()
        game._apply_campaign_rules()
        game.say(f"Game loaded from slot '{slot}'.")
    except Exception as exc:
        game.say(f"Failed to load save '{slot}': {exc}")


def load_settings(game) -> dict:
    from src.colony import savegame as colony_savegame
    from src.config import DEFAULT_SETTINGS, QUALITY_ORDER

    data = colony_savegame.load_slot(game.SETTINGS_SLOT)
    settings = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        for key in settings:
            if key in data:
                settings[key] = data[key]
    if settings.get("quality") not in QUALITY_ORDER:
        settings["quality"] = "medium"
    return settings


def save_settings(game) -> None:
    from src.colony import savegame as colony_savegame
    colony_savegame.save_slot(game.SETTINGS_SLOT, dict(game.settings))
