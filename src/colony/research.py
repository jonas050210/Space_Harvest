"""Research progression: unlock bookkeeping for the colony bridge."""


def unlocked(state, research_key):
    """Return whether a research item has been completed."""
    return research_key in state.get("research", {}).get("unlocked", [])
