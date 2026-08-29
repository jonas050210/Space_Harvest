"""Research progression: unlock bookkeeping for the colony bridge."""

from __future__ import annotations


def unlocked(state: dict, research_key: str) -> bool:
    """Return whether a research item has been completed."""
    return research_key in state.get("research", {}).get("unlocked", [])


def unlock(state: dict, research_key: str) -> bool:
    """Unlock a research item, return True if newly unlocked."""
    lst = state.setdefault("research", {}).setdefault("unlocked", [])
    if research_key in lst:
        return False
    lst.append(research_key)
    return True


def unlocked_all(state: dict) -> list[str]:
    return list(state.get("research", {}).get("unlocked", []))
