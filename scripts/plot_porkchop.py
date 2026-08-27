#!/usr/bin/env python3
"""Plot a departure-time x time-of-flight delta-v (porkchop) map.

    python scripts/plot_porkchop.py metallic_belt out.png

Uses the same grid the game's window search scores, so the contours you see
are exactly what the planner searches.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.config import AU_PER_YEAR_TO_KM_S, SIM_SECONDS_PER_DAY
from src.simulation.bodies import BODIES
from src.simulation.orbital_sim import OrbitalSimulation


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "metallic_belt"
    out = sys.argv[2] if len(sys.argv) > 2 else "logs/porkchop.png"

    sim = OrbitalSimulation()
    grid = sim.porkchop("colony", target)
    dv = grid["dv"] * AU_PER_YEAR_TO_KM_S * 1000.0  # m/s
    depart = np.array(grid["depart"]) / SIM_SECONDS_PER_DAY
    tof = np.array(grid["tof"]) / SIM_SECONDS_PER_DAY

    masked = np.ma.masked_invalid(dv)
    fig, ax = plt.subplots(figsize=(9, 6))
    levels = np.linspace(np.nanmin(dv), np.nanpercentile(dv, 92), 24)
    plot = ax.contourf(depart, tof, masked.T, levels=levels, cmap="viridis")
    fig.colorbar(plot, ax=ax, label="total delta-v (m/s)")
    if grid["best"] is not None:
        ax.plot(
            grid["best"].departure_time / SIM_SECONDS_PER_DAY,
            grid["best"].tof / SIM_SECONDS_PER_DAY,
            marker="*", color="red", markersize=14,
        )
    ax.set_xlabel("departure (sim days)")
    ax.set_ylabel("time of flight (sim days)")
    ax.set_title(f"Colony Hub -> {BODIES[target].name}: launch windows")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    fig.savefig(out, dpi=130)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
