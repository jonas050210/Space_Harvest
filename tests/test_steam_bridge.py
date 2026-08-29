"""Regression tests for the Steam soft-bridge.

The Steamworks facade is a safe no-op without a real AppID, but its bookkeeping
still has to be correct: playtime must not be double-counted between the
per-frame ``tick`` and ``shutdown``, and headless runs must persist stats.
"""

from __future__ import annotations

import json
import os

import pytest

from src import steam_bridge


@pytest.fixture
def temp_stats(monkeypatch, tmp_path):
    """Point the stats file at a temp dir so tests never touch real saves."""
    monkeypatch.setattr(steam_bridge, "cloud_root", lambda: str(tmp_path))
    return tmp_path


def test_playtime_is_not_double_counted(temp_stats):
    client = steam_bridge.SteamClient()
    # Windowed loop: tick every frame with the real elapsed delta.
    for _ in range(10):
        client.tick(0.016)
    total_after_ticks = client._playtime_seconds
    # shutdown must only add the small remainder since the last tick, not the
    # whole session wall-time again (that was the double-count bug).
    client.shutdown()
    persisted = json.loads((temp_stats / "steam_stats.json").read_text())
    assert persisted["playtime_seconds"] == pytest.approx(total_after_ticks, abs=0.05)
    # And the whole session is real elapsed time (~0.16s of ticks), not 2x it.
    assert persisted["playtime_seconds"] < 1.0


def test_headless_tick_zero_still_records_wall_clock(temp_stats):
    """The self-test calls tick(0.0); wall-time still accumulates and persists."""
    client = steam_bridge.SteamClient()
    client.tick(0.0)
    client.shutdown()
    data = json.loads((temp_stats / "steam_stats.json").read_text())
    assert data["playtime_seconds"] >= 0.0
    assert os.path.isfile(temp_stats / "steam_stats.json")


def test_playtime_accumulates_across_sessions(temp_stats):
    first = steam_bridge.SteamClient()
    first.tick(0.5)
    first.shutdown()
    saved = json.loads((temp_stats / "steam_stats.json").read_text())["playtime_seconds"]

    second = steam_bridge.SteamClient()  # reloads previous total
    second.tick(0.5)
    second.shutdown()
    total = json.loads((temp_stats / "steam_stats.json").read_text())["playtime_seconds"]
    assert total >= saved + 0.4
