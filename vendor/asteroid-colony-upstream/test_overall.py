#!/usr/bin/env python3
"""Project-wide tests for Asteroid Colony."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0

def test(name, cond):
    global PASS, FAIL
    if cond:
        print(f"✓ {name}")
        PASS += 1
    else:
        print(f"✗ {name}")
        FAIL += 1

def main():
    global PASS, FAIL
    print("=== Asteroid Colony Tests ===")

    # Import tests.
    try:
        import game.config
        test("Import game.config", True)
    except Exception as e:
        test("Import game.config", False)
        print("  Error:", e)

    try:
        import game.i18n
        test("Import game.i18n", True)
        test("English translations available", "en" in game.i18n.TR)
        test("Translation catalog is English-only", set(game.i18n.TR) == {"en"})
    except Exception as e:
        test("Import game.i18n", False)
        print("  Error:", e)

    try:
        import game.settings
        s = game.settings.load()
        test("Load settings", isinstance(s, dict))
        s["language"] = "en"
        game.settings.save(s)
        s2 = game.settings.load()
        test("Save settings", s2.get("language") == "en")
    except Exception as e:
        test("Settings", False)
        print("  Error:", e)

    try:
        import game.savegame
        game.savegame.ensure_dir()
        import time
        data = {"test": 123, "time": time.time()}
        path = game.savegame.save_slot("test", data)
        loaded = game.savegame.load_slot("test")
        test("Savegame save/load", loaded == data)
    except Exception as e:
        test("Savegame", False)
        print("  Error:", e)

    try:
        import game.state
        st = game.state.initial_state()
        test("Initialize state", isinstance(st, dict) and "resources" in st)
        test("State resources", st["resources"].get("ice", 0) > 0)
        game.state.add_resources(st, {"gold": 10})
        test("Add state resources", st["resources"]["gold"] == 20)
    except Exception as e:
        test("State", False)
        print("  Error:", e)

    try:
        import game.economy
        test("Economy: drone_cost", isinstance(game.economy.drone_cost({"id": 1}), dict))
        test("Economy: upgrade_cost", isinstance(game.economy.upgrade_cost("speed", 0), dict))
    except Exception as e:
        test("Economy", False)
        print("  Error:", e)

    try:
        from game import research, logistics, drones
        research_state = game.state.initial_state()
        research_state["research_points"] = 100
        completed, _ = research.unlock(research_state, "drone_specialization")
        test("Research unlock", completed and research.unlocked(research_state, "drone_specialization"))
        assigned, _ = drones.assign_role(research_state, 1, "hauler")
        test("Drone role assignment", assigned and research_state["drones"][0]["role"] == "hauler")
        stored, overflow = logistics.store(research_state, {"iron": 10})
        test("Logistics storage", stored["iron"] == 10 and overflow["iron"] == 0)
        from game import station_builder, contracts, events, multiplayer
        placed, _ = station_builder.place_module(research_state, "drone_bay", (0, 0))
        test("Station placement", placed and research_state["station_layout"]["occupied"] == [[0, 0]])
        offered, _ = contracts.offer_contract(research_state)
        test("Contract offer", offered and research_state["contracts"]["active"])
        research_state["events_active"].append({"key": "trade_fleet"})
        decision, _ = events.resolve_event_choice(research_state, "trade_fleet", "decline")
        test("Event decision", decision)
        session = multiplayer.MultiplayerSession()
        joined, _ = session.add_player("pilot", "Pilot")
        test("Multiplayer session model", joined and session.snapshot(research_state)["revision"] == 0)
        from game import regions
        research_state["research"]["unlocked"].extend(["logistics_protocols", "deep_space_scanning", "artifact_analysis"])
        research_state["energy"] = 20
        research_state["resources"]["energy"] = 30
        traveled, _ = regions.travel(research_state, "derelict_zone")
        research_state["drones"][0]["role"] = "scout"
        recovered, _ = regions.scan_derelict(research_state)
        test("Derelict exploration", traveled and recovered and research_state["derelict_scanned"])
        research_state["milestones"] = ["artifact_recovery"]
        claimed, _ = regions.claim_milestone(research_state, "artifact_recovery")
        test("Milestone reward", claimed and "artifact_recovery" in research_state["claimed_milestones"])
        from game import director
        director_snapshot = director.snapshot(research_state)
        test("Colony Director guidance", bool(director_snapshot["objective"]) and bool(director_snapshot["recommendation"]))

    except Exception as e:
        test("Automation systems", False)
        print("  Error:", e)

    try:
        import game.entities
        test("Entities import", True)
    except Exception as e:
        test("Entities import", False)
        print("  Error:", e)

    # Headless Ursina boot test.
    try:
        import ursina
        app = ursina.Ursina(window_type='none', borderless=True)
        from game.entities import Asteroid, Drone, StationPart
        from ursina import Vec3
        a = Asteroid(res_type="ice", amount=30, position=Vec3(5, 0, 5), parent=None)
        visual_drone = Drone(99)
        visual_drone.set_role_visual("hauler")
        visual_drone.set_cargo_visual("gold", 5)
        station = StationPart()
        animated_module = __import__("game.entities", fromlist=["StationModuleUnit"]).StationModuleUnit("refinery", Vec3(0, 0, 0))
        # Run a brief three-frame simulation.
        for _ in range(3):
            app.step()
        test("Headless visual systems", visual_drone.cargo_pod.enabled and len(a.veins) == 6 and animated_module.exhaust.enabled)
        test("Headless Ursina Boot", True)
        app.destroy()
    except Exception as e:
        test("Headless Ursina Boot", False)
        print("  Error:", e)

    # Summary.
    print(f"\n=== Result: {PASS} passed, {FAIL} failed ===")
    if FAIL > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
