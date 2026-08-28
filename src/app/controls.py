"""Play-mode control table — the single source of truth for keys and how-to.

Menus, the HUD help line, the command bar and ``Game.handle_action`` all read
this module. If a key is not listed here it is not a game control.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Binding:
    key: str
    action: str
    label: str
    group: str
    help: str


# Live-play bindings. Title / pause screens are handled by MenuOverlay.
PLAY_BINDINGS: tuple[Binding, ...] = (
    Binding("enter", "dispatch", "ENTER", "flight", "Dispatch the selected ship (twice to confirm)"),
    Binding("space", "cycle_ship", "SPACE", "flight", "Cycle the selected idle ship"),
    Binding("tab", "cycle_target", "TAB", "flight", "Cycle the target field"),
    Binding("d", "swarm", "D", "flight", "Launch a harvest swarm while the window is GO"),
    Binding(";", "toggle_hops", ";", "flight", "Toggle multi-stop refuel hops"),
    Binding("j", "jump", "J", "flight", "Jump warp to the next event"),
    Binding("[", "warp_down", "[", "flight", "Slow time warp"),
    Binding("]", "warp_up", "]", "flight", "Speed time warp"),
    Binding(",", "cycle_view", ",", "view", "Cycle network / map / surface"),
    Binding("/", "view_map", "/", "view", "System chart (top-down)"),
    Binding(".", "view_surface", ".", "view", "Land on the selected field"),
    Binding("backspace", "view_network", "BACKSPACE", "view", "Return to network 3-D"),
    Binding("o", "toggle_orbits", "O", "view", "Toggle orbit rings"),
    Binding("f", "follow", "F", "view", "Follow next ship"),
    Binding("c", "camera_network", "C", "view", "Free network camera"),
    Binding("s", "sell", "S", "market", "Sell all marketable ore (ice reserve held)"),
    Binding("5", "sell_50", "5", "market", "Sell 50% of stock"),
    Binding("6", "sell_25", "6", "market", "Sell 25% of stock"),
    Binding("b", "accept_contract", "B", "market", "Accept the oldest Earth offer"),
    Binding("v", "decline_contract", "V", "market", "Decline the oldest Earth offer"),
    Binding("r", "depot", "R", "build", "Build or upgrade a refuel barn"),
    Binding("e", "refinery", "E", "build", "Build a refinery"),
    Binding("p", "drones", "P", "build", "Install a depot drone bay"),
    Binding("=", "survey", "=", "build", "Surface survey (+yield for a season)"),
    Binding("-", "isru", "-", "build", "Plant an ISRU spike (barn boost)"),
    Binding("7", "mod_observatory", "7", "build", "Build a field observatory"),
    Binding("8", "mod_warehouse", "8", "build", "Build an orbital warehouse"),
    Binding("9", "mod_drill_yard", "9", "build", "Build a drill yard"),
    Binding("'", "mod_shield_mast", "'", "build", "Build a shield mast"),
    Binding("x", "toggle_drill", "X", "fleet", "Toggle scrape / core drilling"),
    Binding("m", "toggle_repair", "M", "fleet", "Toggle automatic hull maintenance"),
    Binding("1", "buy_scout", "1", "fleet", "Commission a scout"),
    Binding("2", "buy_freighter", "2", "fleet", "Commission a freighter"),
    Binding("3", "buy_refinery", "3", "fleet", "Commission a refinery-ship"),
    Binding("4", "buy_hauler", "4", "fleet", "Commission a hauler"),
    Binding("0", "buy_tanker", "0", "fleet", "Commission a tanker"),
    Binding("t", "part_tank", "T", "fleet", "Install drop tanks"),
    Binding("y", "part_drill", "Y", "fleet", "Install a deep drill"),
    Binding("u", "part_quarters", "U", "fleet", "Install crew quarters"),
    Binding("i", "part_navsuite", "I", "fleet", "Install a navigation suite (aurellium)"),
    Binding("f6", "part_scanner", "F6", "fleet", "Install an ore scanner"),
    Binding("f7", "part_shield", "F7", "fleet", "Install shield weave"),
    Binding("f8", "part_magclamp", "F8", "fleet", "Install mag-clamps"),
    Binding("g", "hire_miner", "G", "crew", "Hire a miner"),
    Binding("z", "hire_botanist", "Z", "crew", "Hire a colony botanist"),
    Binding("h", "fire", "H", "crew", "Dismiss the unhappiest crew member"),
    Binding("l", "tech", "L", "science", "Commission the next technology"),
    Binding("k", "quality", "K", "meta", "Cycle graphics quality"),
    Binding("n", "mute", "N", "meta", "Mute audio"),
    Binding("f5", "save", "F5", "meta", "Quick-save"),
    Binding("f9", "load", "F9", "meta", "Quick-load (blocked on Ironman)"),
    Binding("f1", "report", "F1", "meta", "Year report"),
)

# Bottom command bar — mouse-first, same actions as the keys.
COMMAND_BAR: tuple[tuple[str, str], ...] = (
    ("GO", "dispatch"),
    ("SHIP", "cycle_ship"),
    ("SELL", "sell"),
    ("SWARM", "swarm"),
    ("BARN", "depot"),
    ("VIEW", "cycle_view"),
)

_KEY_TO_ACTION = {b.key: b.action for b in PLAY_BINDINGS}


def action_for_key(key: str) -> str | None:
    """Map a raw Ursina key to an action token, or None."""
    return _KEY_TO_ACTION.get(key)


def help_line() -> str:
    return "SPACE ship  TAB field  ENTER go  D swarm  , view  S sell  R barn  [ ] warp  F5 save  ESC pause"


def bindings_by_group() -> dict[str, list[Binding]]:
    groups: dict[str, list[Binding]] = {}
    for binding in PLAY_BINDINGS:
        groups.setdefault(binding.group, []).append(binding)
    return groups


HOWTO_PAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("THE HARVEST", (
        "Asteroids are fields. Launch windows are the season.",
        "TAB or click a rock. SPACE picks which idle ship flies.",
        "Watch NEXT WINDOWS. When the banner says GO, ENTER (twice).",
        "Click GO on the bar if you would rather not hunt for keys.",
        "",
        "Warp with [ and ]. Sell with S — or 5 / 6 to drip-feed Earth.",
        "Dump one market and its price floods. Stagger sales.",
    )),
    ("BARNS AND THE FAR RING", (
        "Every burn costs delta-v from a finite tank. R builds a barn",
        "(refuel depot) at the selected body. ISRU cooks propellant",
        "from local ice so deep freighters can top up for the ride home.",
        "",
        "E builds a mill (refinery). D launches a drone swarm on GO —",
        "build drone bays with P first. ; toggles multi-stop hops.",
    )),
    ("CREWS AND TOOLS", (
        "Crews get tired and sullen. Tired crews refuse to fly.",
        "They earn morale from captures and payday (S).",
        "",
        "T tanks, Y drill, U quarters, I nav suite (needs aurellium).",
        "F6 scanner, F7 shield, F8 mag-clamps. L spends research.",
        "1-4 and 0 commission hulls. G hire miner, Z botanist, H fire.",
    )),
    ("SURFACE AND MAP", (
        "Three views: network 3-D, system chart, surface survey.",
        "Comma (,) cycles. Slash (/) map. Period (.) lands. Backspace home.",
        "",
        "On the surface: = surveys veins (+yield), - plants an ISRU spike",
        "(permanent barn boost). Click a ship mesh to select it.",
    )),
    ("CAMPAIGN", (
        "SETTINGS picks difficulty (Director / Tight / Ironman) and a",
        "victory (Endless / Charter / Legacy) before NEW HARVEST.",
        "Ironman: one save, no mid-run loads, critical hulls can wreck.",
        "",
        "K cycles Low / Medium / High / Ultra. F1 year report. F5 save.",
        "The belt keeps moving. Wait for the window.",
    )),
)
