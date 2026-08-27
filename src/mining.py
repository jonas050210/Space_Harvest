"""Procedural ore bodies, depletion ledgers and extraction planning.

Every trade body gets a deterministic ore *fingerprint*: the same mix of
upstream-known resources every time, but unique per rock, derived from the
body key and ``MINING_SEED``. Extraction draws down a per-body ledger, so rich
veins thin out over a campaign and the fleet is pushed outward to fresh rocks
(veins recover only on a multi-year timescale, see ``MINING_RECOVERY_TAU_DAYS``).

Only resources the vendored ``asteroid-colony`` economy already understands are
ever produced, so a delivery stores cleanly through ``logistics.store()``.

This module has no graphics imports; it is pure model code covered by tests.
"""

from __future__ import annotations

import math
import random
import zlib

from .config import (
    MINING_DRILL_YIELD_BONUS,
    MINING_LOW_HULL_YIELD_PCT,
    MINING_ORES,
    MINING_RECOVERY_TAU_BY_ORE,
    MINING_SEED,
    MINING_VEIN_SIZE_T,
)
from .simulation.bodies import BODIES

# Weight seeds by position in a body's declared resource tuple: earlier
# entries are the body's staple ores, later ones its bonus ores.
_POSITION_WEIGHTS = (1.0, 0.6, 0.35, 0.2)
_JITTER = 0.45  # fingerprint variation applied to each weight

_fingerprint_cache: dict[str, dict[str, float]] = {}


def _body_ores(body_key: str) -> tuple[str, ...]:
    """The minable ores a body offers, filtered to known upstream resources."""
    body = BODIES[body_key]
    ores = tuple(ore for ore in body.resources if ore in MINING_ORES)
    return ores or ("iron",)


def body_fingerprint(body_key: str, seed: int = MINING_SEED) -> dict[str, float]:
    """Deterministic ore mix for a body; shares sum to 1.

    The same body key always yields the same fingerprint, independent of
    process start order (a CRC is used rather than ``hash()``, which is
    randomised between interpreter runs).
    """
    cached = _fingerprint_cache.get(body_key)
    if cached is not None and seed == MINING_SEED:
        return dict(cached)

    ores = _body_ores(body_key)
    rng = random.Random(seed + zlib.crc32(body_key.encode("utf-8")))
    weights = [
        max(0.05, _POSITION_WEIGHTS[min(i, len(_POSITION_WEIGHTS) - 1)]
            * (1.0 + rng.uniform(-_JITTER, _JITTER)))
        for i in range(len(ores))
    ]
    total = sum(weights)
    fingerprint = {ore: weight / total for ore, weight in zip(ores, weights)}
    if seed == MINING_SEED:
        _fingerprint_cache[body_key] = dict(fingerprint)
    return fingerprint


def vein_size(body_key: str, ore: str) -> float:
    """How many tonnes of ``ore`` a body's field yields before thinning out.

    Bodies rich in an ore have proportionally larger veins of it.
    """
    share = body_fingerprint(body_key).get(ore, 0.0)
    return MINING_VEIN_SIZE_T[ore] * (0.6 + 0.8 * share)


class YieldLedger:
    """Bookkeeping of how much ore has been pulled out of each body."""

    def __init__(self) -> None:
        #: body key -> ore -> tonnes extracted so far
        self.extracted: dict[str, dict[str, float]] = {}

    def extracted_at(self, body_key: str, ore: str) -> float:
        return self.extracted.get(body_key, {}).get(ore, 0.0)

    def remaining_fraction(self, body_key: str, ore: str) -> float:
        """Depletion curve: exp(-extracted / vein). 1.0 = virgin field."""
        size = vein_size(body_key, ore)
        if size <= 0.0:
            return 0.0
        return math.exp(-self.extracted_at(body_key, ore) / size)

    def commit(self, body_key: str, payload: dict[str, float]) -> None:
        """Register ore actually mined (called when a run captures)."""
        slot = self.extracted.setdefault(body_key, {})
        for ore, tonnes in payload.items():
            slot[ore] = slot.get(ore, 0.0) + max(0.0, tonnes)

    def recover(self, dt_days: float, tau_days: float) -> None:
        """Veins slowly recharge as the fields drift and replenish.

        Per-ore overrides win over the global tau: volatile ices replenish on
        a much shorter timescale than metal deposits (see
        ``MINING_RECOVERY_TAU_BY_ORE``).
        """
        if dt_days <= 0.0 or tau_days <= 0.0:
            return
        for slot in self.extracted.values():
            for ore in list(slot):
                tau = MINING_RECOVERY_TAU_BY_ORE.get(ore, tau_days)
                slot[ore] *= math.exp(-dt_days / tau)

    def to_json(self) -> dict:
        return {"extracted": {body: dict(slot) for body, slot in self.extracted.items()}}

    @classmethod
    def from_json(cls, data: dict) -> "YieldLedger":
        ledger = cls()
        for body, slot in (data or {}).get("extracted", {}).items():
            ledger.extracted[body] = {ore: float(t) for ore, t in slot.items()}
        return ledger


def mining_hull_factor(hull_pct: float) -> float:
    """Damaged machinery mines poorly: below the low-hull threshold the yield
    scales linearly with hull, floored so a limping ship still earns something."""
    if hull_pct >= MINING_LOW_HULL_YIELD_PCT:
        return 1.0
    return max(0.2, hull_pct / MINING_LOW_HULL_YIELD_PCT)


def plan_extraction(
    body_key: str,
    ledger: YieldLedger,
    reserved: dict[str, float] | None,
    capacity_t: float,
    mode: str = "scrape",
    mine_bonus: float = 1.0,
    hull_pct: float = 100.0,
) -> dict[str, float]:
    """Plan one hold's worth of mining at ``body_key``.

    ``reserved`` carries tonnes already promised to ships currently inbound to
    the same body, so two concurrent runs cannot sell the same vein twice.
    Depleted components of the fingerprint simply yield less; the payload
    shrinks rather than being topped up from another ore.

    Modes: ``scrape`` (cheap, baseline) or ``drill`` (core drilling: a larger
    haul that costs hull wear and carries incident risk, billed by the caller).
    """
    fingerprint = body_fingerprint(body_key)
    budget = capacity_t * mine_bonus
    if mode == "drill":
        budget *= MINING_DRILL_YIELD_BONUS
    budget *= mining_hull_factor(hull_pct)

    spoken = reserved or {}
    payload: dict[str, float] = {}
    for ore, share in fingerprint.items():
        taken = ledger.extracted_at(body_key, ore) + spoken.get(ore, 0.0)
        size = vein_size(body_key, ore)
        remaining = math.exp(-taken / size) if size > 0.0 else 0.0
        amount = budget * share * remaining
        if amount > 0.05:
            payload[ore] = amount
    # The hold is a hard limit: drilling and refinery bonuses let a ship *fill*
    # its hold even from thinning veins, never exceed it.
    total = sum(payload.values())
    if total > capacity_t > 0.0:
        scale = capacity_t / total
        payload = {ore: tonnes * scale for ore, tonnes in payload.items()}
    return payload


def assay_lines(body_key: str, ledger: YieldLedger, reserved: dict[str, float] | None = None) -> str:
    """One-line HUD assay of a body: shares plus what is left in the veins."""
    fingerprint = body_fingerprint(body_key)
    spoken = reserved or {}
    parts = []
    for ore, share in sorted(fingerprint.items(), key=lambda kv: -kv[1]):
        taken = ledger.extracted_at(body_key, ore) + spoken.get(ore, 0.0)
        size = vein_size(body_key, ore)
        left = math.exp(-taken / size) if size > 0.0 else 0.0
        parts.append(f"{ore} {share * 100:.0f}% ({left * 100:.0f}% left)")
    return "  ".join(parts)
