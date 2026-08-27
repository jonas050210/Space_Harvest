"""The bodies the colony ships trade between.

Each body is a real Keplerian orbit around the sun, keyed by the same
identifiers the existing ``asteroid-colony`` economy already uses for its
regions. That mapping is deliberate: ``regions.travel()`` stays in place as
the economic rulebook, while ``orbital_sim`` decides *when* and *at what
cost* a freighter can actually make the trip.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..config import MU_SUN
from ..maths.elements import OrbitalElements


@dataclass(frozen=True)
class Body:
    """A trade destination on a heliocentric orbit."""

    key: str
    name: str
    elements: OrbitalElements
    radius_km: float
    soi_km: float              # sphere of influence, used for capture burns
    palette: tuple[float, float, float]
    resources: tuple[str, ...] = ()
    description: str = ""
    render_scale: float = 1.0  # relative body size in the scene
    moons: tuple["Body", ...] = field(default_factory=tuple)


def _el(a: float, e: float, i_deg: float, raan_deg: float, argp_deg: float, nu_deg: float) -> OrbitalElements:
    return OrbitalElements(
        a=a, e=e,
        i=math.radians(i_deg),
        raan=math.radians(raan_deg),
        argp=math.radians(argp_deg),
        nu=math.radians(nu_deg),
    )


def build_bodies() -> dict[str, Body]:
    """Construct the trade network. Keys match ``game.config.REGIONS``."""
    nix = Body(
        key="nix", name="Nix",
        elements=_el(0.012, 0.02, 2.0, 0.0, 0.0, 90.0),
        radius_km=1100.0, soi_km=24000.0,
        palette=(0.52, 0.75, 0.90),
        resources=("ice",),
        description="Ice moon in a tight orbit around Aurelia.",
        render_scale=0.45,
    )
    aurelia = Body(
        key="gas_giant_orbit", name="Aurelia",
        elements=_el(2.80, 0.055, 1.5, 40.0, 20.0, 210.0),
        radius_km=58000.0, soi_km=4.5e6,
        palette=(0.64, 0.40, 0.82),
        resources=("silver", "gold"),
        description="Ringed gas giant; premium freight contracts in orbit.",
        render_scale=2.4,
        moons=(nix,),
    )
    bodies = {
        "colony": Body(
            key="colony", name="Colony Hub",
            elements=_el(1.20, 0.015, 0.0, 0.0, 0.0, 0.0),
            radius_km=9.0, soi_km=35000.0,
            palette=(0.85, 0.92, 1.0),
            resources=("ice", "iron"),
            description="Home station in the inner belt. All runs start and end here.",
            render_scale=0.5,
        ),
        "inner_belt": Body(
            key="inner_belt", name="Inner Belt Field",
            elements=_el(1.45, 0.07, 1.0, 90.0, 45.0, 120.0),
            radius_km=12.0, soi_km=30000.0,
            palette=(0.90, 0.95, 1.0),
            resources=("ice", "iron", "silver"),
            description="Reliable starter mining close to the colony.",
            render_scale=0.6,
        ),
        "metallic_belt": Body(
            key="metallic_belt", name="Metallic Belt Field",
            elements=_el(2.00, 0.12, 2.0, 150.0, 80.0, 300.0),
            radius_km=26.0, soi_km=48000.0,
            palette=(0.72, 0.80, 0.96),
            resources=("iron", "silver", "gold"),
            description="Dense metal fields with stronger trade opportunities.",
            render_scale=0.9,
        ),
        "gas_giant_orbit": aurelia,
        "deep_belt": Body(
            key="deep_belt", name="Deep Belt Outpost",
            elements=_el(3.40, 0.18, 4.0, 260.0, 130.0, 60.0),
            radius_km=19.0, soi_km=41000.0,
            palette=(0.62, 0.43, 0.92),
            resources=("gold", "silver", "platinum"),
            description="Rare metals, distant operations, and anomalous machinery.",
            render_scale=0.75,
        ),
        "derelict_zone": Body(
            key="derelict_zone", name="Derelict Zone",
            elements=_el(3.95, 0.24, 6.0, 310.0, 200.0, 15.0),
            radius_km=8.0, soi_km=26000.0,
            palette=(0.48, 0.20, 0.34),
            resources=("components", "electronics"),
            description="Abandoned industrial ruins containing recoverable artifacts.",
            render_scale=0.4,
        ),
    }
    bodies["nix"] = nix
    return bodies


BODIES: dict[str, Body] = build_bodies()

#: Bodies a freighter can actually be dispatched to (the colony is the hub).
TRADE_TARGETS: tuple[str, ...] = (
    "inner_belt", "metallic_belt", "gas_giant_orbit", "deep_belt", "derelict_zone",
)


def orbit_points(key: str, samples: int = 256) -> np.ndarray:
    """Sample a body's heliocentric orbit as an ``(samples + 1, 3)`` array in AU.

    The sweep covers a full 2 pi of true anomaly *inclusive*, so the first and
    last rows coincide and the result can be drawn as a closed line strip.
    """
    from ..maths.elements import elements_to_state

    el = BODIES[key].elements
    pts = np.empty((samples + 1, 3), dtype=float)
    for idx in range(samples + 1):
        nu = el.nu + 2.0 * math.pi * idx / samples
        swapped = OrbitalElements(a=el.a, e=el.e, i=el.i, raan=el.raan, argp=el.argp, nu=nu)
        pts[idx] = elements_to_state(swapped, MU_SUN)[0]
    return pts


def orbital_speed_km_s(key: str) -> float:
    """Mean orbital speed of a body in km/s, for HUD readouts."""
    from ..config import AU_PER_YEAR_TO_KM_S

    el = BODIES[key].elements
    return math.sqrt(MU_SUN / el.a) * AU_PER_YEAR_TO_KM_S
