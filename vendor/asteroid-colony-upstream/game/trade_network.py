# Orbital Trade Network.
# Trade network with fluctuating prices and route planning.
from .. import config, state as st_mod

def get_trade_prices():
    # Simulated price fluctuations.
    return {
        "ice": 1.2,
        "iron": 2.1,
        "gold": 7.5,
        "silver": 4.8,
        "platinum": 11.0,
    }

def apply_trade(state, resource_key, amount):
    prices = get_trade_prices()
    price = prices.get(resource_key, 1)
    value = int(amount * price)
    state["resources"][resource_key] = state.get("resources", {}).get(resource_key, 0) - amount
    state["resources"]["ice"] = state.get("resources", {}).get("ice", 0) + value
