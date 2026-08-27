"""Dynamic Earth-market pricing for the colony's ore.

Three overlapping effects make prices a game rather than a lookup table:

* a **seasonal sine** per resource with a distinct period, so patient players
  can ride predictable swings;
* a **mean-reverting random walk** on demand, so no cycle repeats exactly;
* **flooding**: every tonne sold depresses the price, with rare ores absorbed
  far more slowly than bulk ice, so dumping a big haul crashes its own value
  and staggered sales win.

Prices are always positive and floored at a fraction of base. The module is
deterministic for a given seed and fully JSON-serialisable, which is what the
savegame and the test suite rely on.
"""

from __future__ import annotations

import math
import random

from .config import (
    MARKET_ABSORPTION_T,
    MARKET_BASE_PRICES,
    MARKET_FLOOD_HALF_LIFE_DAYS,
    MARKET_HISTORY_POINTS,
    MARKET_HISTORY_SAMPLE_DAYS,
    MARKET_NOISE_MEAN_REVERSION,
    MARKET_NOISE_SIGMA,
    MARKET_PRICE_FLOOR_FRACTION,
    MARKET_SEASONAL_AMPLITUDE,
    MARKET_SEASONAL_PERIOD_DAYS,
)


def rng_to_json(rng: random.Random) -> dict:
    """Serialise a ``random.Random`` (Mersenne Twister state is JSON-safe)."""
    state = rng.getstate()
    return {"version": state[0], "state": [int(x) for x in state[1]], "gauss": state[2]}


def rng_from_json(data: dict) -> random.Random:
    rng = random.Random()
    rng.setstate((int(data["version"]), tuple(int(x) for x in data["state"]), data["gauss"]))
    return rng


class Market:
    """Earth demand for colony ore: prices, flooding and sale execution."""

    def __init__(self, seed: int = 7, day: float = 0.0):
        self.rng = random.Random(seed)
        self.day = float(day)
        self.demand = {res: 1.0 for res in MARKET_BASE_PRICES}
        self.phase = {res: self.rng.uniform(0.0, 2.0 * math.pi) for res in MARKET_BASE_PRICES}
        #: tonnes recently dumped per resource; decays with the flood half-life
        self.flood = {res: 0.0 for res in MARKET_BASE_PRICES}
        #: (day, {resource: price}) samples for HUD sparklines / trend arrows
        self.history: list[tuple[float, dict[str, float]]] = []
        self._since_sample = float("inf")

    # -- simulation ----------------------------------------------------------
    def update(self, dt_days: float) -> None:
        if dt_days <= 0.0:
            return
        self.day += dt_days
        decay = 0.5 ** (dt_days / MARKET_FLOOD_HALF_LIFE_DAYS)
        step = math.sqrt(dt_days)
        for res in self.demand:
            # Mean-reverting walk keeps demand lively but bounded.
            self.demand[res] += (1.0 - self.demand[res]) * MARKET_NOISE_MEAN_REVERSION * dt_days
            self.demand[res] += self.rng.gauss(0.0, MARKET_NOISE_SIGMA) * step
            self.demand[res] = min(1.35, max(0.7, self.demand[res]))
            self.flood[res] *= decay
        self._since_sample += dt_days
        if self._since_sample >= MARKET_HISTORY_SAMPLE_DAYS:
            self._since_sample = 0.0
            self.history.append((self.day, {res: self.price(res) for res in self.demand}))
            if len(self.history) > MARKET_HISTORY_POINTS:
                del self.history[: len(self.history) - MARKET_HISTORY_POINTS]

    # -- quotes --------------------------------------------------------------
    def price(self, res: str) -> float:
        """Current credits per tonne."""
        base = MARKET_BASE_PRICES.get(res)
        if base is None:
            return 0.0
        seasonal = 1.0 + MARKET_SEASONAL_AMPLITUDE * math.sin(
            2.0 * math.pi * self.day / MARKET_SEASONAL_PERIOD_DAYS[res] + self.phase[res]
        )
        absorb = MARKET_ABSORPTION_T[res]
        flood_mult = 1.0 / (1.0 + self.flood[res] / absorb)
        price = base * self.demand[res] * seasonal * flood_mult
        return max(MARKET_PRICE_FLOOR_FRACTION * base, price)

    def trend(self, res: str, lookback_days: float = 20.0) -> str:
        """'^' rising, 'v' falling, '=' flat versus ``lookback_days`` ago."""
        target_day = self.day - lookback_days
        reference = None
        for day, prices in reversed(self.history):
            if day <= target_day:
                reference = prices.get(res)
                break
        if reference is None:
            return "="
        now = self.price(res)
        if now > reference * 1.02:
            return "^"
        if now < reference * 0.98:
            return "v"
        return "="

    def quote(self, res: str, tonnes: float) -> float:
        """Proceeds for selling ``tonnes`` now, flooding priced in.

        The lot is sold in slices so a big sale walks its own price down the
        absorption curve instead of getting the pre-sale price on every tonne.
        """
        if tonnes <= 0.0:
            return 0.0
        absorb = MARKET_ABSORPTION_T[res]
        slices = min(10, max(1, int(tonnes / absorb) + 1))
        per_slice = tonnes / slices
        proceeds = 0.0
        for _ in range(slices):
            proceeds += self.price(res) * per_slice
            self.flood[res] += per_slice
        # Undo the probe so quote() stays a quote; sell() applies it for real.
        for _ in range(slices):
            self.flood[res] -= per_slice
        return proceeds

    def sell(self, lots: dict[str, float]) -> tuple[float, dict[str, float]]:
        """Execute a sale; returns ``(proceeds, sold)``. Prices flood as sold."""
        proceeds = 0.0
        sold: dict[str, float] = {}
        for res, tonnes in lots.items():
            tonnes = float(tonnes)
            if tonnes <= 0.0 or res not in MARKET_BASE_PRICES:
                continue
            proceeds += self.quote(res, tonnes)
            self.flood[res] += tonnes
            sold[res] = tonnes
        return proceeds, sold

    # -- persistence ---------------------------------------------------------
    def to_json(self) -> dict:
        return {
            "day": self.day,
            "demand": dict(self.demand),
            "phase": dict(self.phase),
            "flood": dict(self.flood),
            "history": [[day, prices] for day, prices in self.history],
            "since_sample": self._since_sample,
            "rng": rng_to_json(self.rng),
        }

    @classmethod
    def from_json(cls, data: dict) -> "Market":
        market = cls.__new__(cls)
        market.rng = rng_from_json(data["rng"])
        market.day = float(data["day"])
        market.demand = {res: float(v) for res, v in data["demand"].items()}
        market.phase = {res: float(v) for res, v in data["phase"].items()}
        market.flood = {res: float(v) for res, v in data["flood"].items()}
        market.history = [[float(day), {res: float(p) for res, p in prices.items()}]
                          for day, prices in data["history"]]
        market._since_sample = float(data["since_sample"])
        return market
