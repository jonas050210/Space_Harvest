#!/usr/bin/env python3
"""game/main.py — Game Logic and 3D Scene."""
import sys, os, time, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ursina import *
from ursina import scene as ursina_scene
from game import config, i18n, settings as st_settings, savegame
from game import state as st_state, entities, drones, mining, economy, scene, events, utils, research, logistics, regions, station_builder
from game.ui import hud, menu, build_menu, automation_menu, mission_board, director_panel

class Game:
    def __init__(self):
        self.lang = st_settings.load().get("language", "en")
        self.paused = False
        self.state = st_state.initial_state()
        self.station = None
        self.stars = []
        self.asteroids = []
        self.drone_vis_map = {}
        self.hud_elements = None
        self.menu_open = None
        self.build_menu_ref = None
        self.conveyor_belts = []
        self.automation_menu = None
        self.mission_board = None
        self.director_panel = None
        self.world_landmarks = {}
        # Economy and machine gameplay; no combat abilities.

    def build_scene(self):
        # Station
        self.station = entities.StationPart(parent=ursina_scene)
        # Keep star references for update-time rotation.
        stars_result = scene.build_scene(self.station)
        self.stars = stars_result
        # This lightweight scene does not currently retain generated nebulae.
        self.nebulae = []
        # Asteroids
        self.asteroids = mining.spawn_asteroid_ring(self.station, count=10, parent=ursina_scene, region=self.state.get("current_region", "inner_belt"))
        # Asteroid click handlers.
        for ast in self.asteroids:
            ast.on_click = lambda a=ast: self.select_asteroid(a)
        # Drones (visuell)
        for d_state in self.state.get("drones", []):
            drone_vis = entities.Drone(d_state["id"], parent=ursina_scene)
            drone_vis.position = self.station.position + Vec3(0, 2, 0)
            drone_vis.on_click = lambda d=drone_vis, s=d_state: self.select_drone(d, s)
            drone_vis.set_role_visual(d_state.get("role", "miner"))
            self.drone_vis_map[d_state["id"]] = drone_vis
        # Camera
        scene.setup_camera()
        # HUD
        self.hud_elements = hud.create_hud(self)
        # Menu Function
        self.menu_open, btn_map, overlay, title_text = menu.create_main_menu(self)
        # Build Menu
        build_menu.create_build_menu(self)
        # Tycoon-style machines menu.
        from .ui import tech_menu
        tech_menu.create_tech_menu(self)
        # Station-design blueprint menu.
        from .ui import blueprint_menu
        blueprint_menu.create_blueprint_menu(self)
        self.automation_menu = automation_menu.create_automation_menu(self)
        self.mission_board = mission_board.create_mission_board(self)
        self.director_panel = director_panel.create_director_panel(self)
        # Automatically save every 60 seconds.
        invoke(self.save_state, delay=60)
        # Atmospheric lighting.
        # Directional light simulates the sun for shadows and depth.
        self.sun_light = DirectionalLight()
        sun_light = self.sun_light
        sun_light.color = color.rgb(1.0, 0.95, 0.9)
        sun_light.position = Vec3(20, 30, 10)
        sun_light.look_at(Vec3(0, 0, 0))
        # Ambient light fills darker areas.
        self.ambient_light = AmbientLight()
        ambient = self.ambient_light
        ambient.color = color.rgb(0.2, 0.2, 0.3)

        # Black Hole Background (Main Sequence Inspiration)
        self.world_landmarks["black_hole"] = entities.BlackHole(position=Vec3(30, -10, 25), parent=ursina_scene)
        self.world_landmarks["gas_giant"] = entities.Planet("Aurelia", Vec3(-42, 13, 44), (0.55, 0.32, 0.75), scale=12, rings=True, parent=ursina_scene)
        self.world_landmarks["ice_moon"] = entities.Planet("Nix", Vec3(38, 18, 58), (0.52, 0.75, 0.9), scale=4.5, parent=ursina_scene)
        # Connect conveyor belts to nearby asteroids.
        for ast in self.asteroids[:3]:
            belt = entities.ConveyorBelt(self.station.position, ast.position, parent=ursina_scene)
            belt.set_resource_visual(ast.res_type)
            self.conveyor_belts.append(belt)
        # Retain any nebulae created by the scene.
        self.nebulae = getattr(scene, 'nebulae', [])

    def add_new_drone(self, drone_id):
        d_state = next((d for d in self.state.get("drones", []) if d.get("id") == drone_id), None)
        if d_state is None:
            return
        drone_vis = entities.Drone(drone_id, parent=ursina_scene)
        drone_vis.position = self.station.position + Vec3(0, 2, 0)
        drone_vis.on_click = lambda d=drone_vis, s=d_state: self.select_drone(d, s)
        drone_vis.set_role_visual(d_state.get("role", "miner"))
        self.drone_vis_map[drone_id] = drone_vis

    def show_placement_grid(self, selected_cell=None):
        """Briefly reveal valid industrial placement pads around the station."""
        occupied = {tuple(cell) for cell in self.state.get("station_layout", {}).get("occupied", [])}
        pads = []
        for z in range(-4, 5):
            for x in range(-4, 5):
                cell = (x, z)
                pad_color = color.red if cell in occupied else color.azure
                if cell == selected_cell:
                    pad_color = color.orange
                pad = Entity(parent=ursina_scene, model="quad", color=color.rgba(pad_color.r, pad_color.g, pad_color.b, 110), scale=0.7, position=Vec3(x * 0.85, 0.02, z * 0.85), rotation_x=90)
                pads.append(pad)
        invoke(lambda: [destroy(pad) for pad in pads], delay=1.2)

    def place_next_module(self):
        """Place the next unplaced built module on the visible station grid."""
        placed = [entry["module"] for entry in self.state.get("station_layout", {}).get("placements", [])]
        module_key = next((item for item in self.state.get("modules", []) if item not in placed), None)
        if module_key is None:
            print("[Station] Every built module is already placed.")
            return False
        occupied = {tuple(cell) for cell in self.state.get("station_layout", {}).get("occupied", [])}
        cell = next(((x, z) for z in range(-4, 5) for x in range(-4, 5) if (x, z) not in occupied), None)
        self.show_placement_grid(cell)
        success, message = station_builder.place_module(self.state, module_key, cell)
        if not success:
            print(f"[Station] {message}")
            return False
        visual = entities.StationModuleUnit(module_key, Vec3(cell[0] * 0.85, 1 + len(placed) * 0.08, cell[1] * 0.85), parent=self.station)
        visual.tooltip = module_key.replace("_", " ").title()
        print(f"[Station] {message}")
        return True

    def change_region_visuals(self, region_key):
        """Refresh asteroid operations and the backdrop after region travel."""
        for asteroid in self.asteroids:
            if asteroid.enabled:
                destroy(asteroid)
        self.asteroids = mining.spawn_asteroid_ring(self.station, count=10, parent=ursina_scene, region=region_key)
        for asteroid in self.asteroids:
            asteroid.on_click = lambda target=asteroid: self.select_asteroid(target)
        scene.set_region_atmosphere(self.stars, region_key)

    def update_world_landmarks(self):
        """Reveal advanced scenery only when the relevant colony research is complete."""
        unlocked = self.state.get("research", {}).get("unlocked", [])
        if "planetary_trade_routes" in unlocked and "freighter" not in self.world_landmarks:
            self.world_landmarks["freighter"] = entities.TradeFreighter(Vec3(-28, 6, -24), self.station.position + Vec3(3, 3, 0), parent=ursina_scene)
        if "artifact_analysis" in unlocked and "rogue_miner" not in self.world_landmarks:
            self.world_landmarks["rogue_miner"] = entities.RogueMiningDrone(Vec3(24, 4, 25), parent=ursina_scene)

    def toggle_director(self):
        """Show or hide the operational guidance panel."""
        if self.director_panel:
            self.director_panel["toggle"]()

    def set_camera_preset(self, preset):
        """Apply readable overview, industry, or deep-space camera framing."""
        presets = {
            "overview": Vec3(0, 22, -28),
            "industry": Vec3(7, 9, -12),
            "deep_space": Vec3(0, 34, -46),
        }
        if preset in presets:
            camera.position = presets[preset]
            self.zoom_target = camera.position.y

    def select_drone(self, drone_entity, drone_state):
        print(f"[Game] Drone {drone_state.get('id')} selected — state: {drone_state.get('state')}")
        original_color = drone_entity.color
        drone_entity.color = color.yellow
        invoke(lambda: setattr(drone_entity, 'color', original_color), delay=0.3)

    def select_asteroid(self, asteroid_entity):
        print(f"[Game] Asteroid selected — {asteroid_entity.res_type}, amount: {int(asteroid_entity.amount)}")
        original_color = asteroid_entity.color
        asteroid_entity.color = color.white
        invoke(lambda: setattr(asteroid_entity, 'color', original_color), delay=0.3)

    def update(self):
        if self.paused:
            return
        # Improved camera controls (WASD, Q/E, scroll).
        # Move the camera relative to the station.
        rot_speed = 30 * time.dt
        pan_speed = 5 * time.dt
        zoom_speed = 15 * time.dt

        # Q/E rotates the camera around the Y axis.
        if held_keys.get('q'):
            camera.rotation_y -= rot_speed
        if held_keys.get('e'):
            camera.rotation_y += rot_speed

        # WASD moves the camera.
        # Pan along the X and Z axes.
        if held_keys.get('w'):
            camera.position += Vec3(0, 0, pan_speed)
        if held_keys.get('s'):
            camera.position += Vec3(0, 0, -pan_speed)
        if held_keys.get('a'):
            camera.position += Vec3(-pan_speed, 0, 0)
        if held_keys.get('d'):
            camera.position += Vec3(pan_speed, 0, 0)

        # Scroll adjusts the camera height for zoom.
        # Ursina sends scroll events through input(), not held_keys.
        # input() stores the desired zoom target.
        if hasattr(self, 'zoom_target'):
            camera.position.y += (self.zoom_target - camera.position.y) * 3 * time.dt
        else:
            self.zoom_target = camera.position.y

        # Keep the camera focused on the station.
        camera.look_at(self.station)

        # Rotate stars and nebulae.
        scene.update_scene(self.stars, getattr(self, 'nebulae', []))

        # Economy and machine gameplay; no combat abilities. (Block Tycoon Style)
        # Machines produce resources automatically.
        st_state.add_machine_output(self.state)
        if self.state.get("tick", 0) % 120 == 0:
            logistics.process_production(self.state)

        # Simple mechanic: left click mines a nearby asteroid.
        if mouse.left:
            nearest = None
            best_d = float('inf')
            for a in self.asteroids:
                if a.enabled and a.amount > 0:
                    d = (self.station.position - a.position).length()
                    if d < best_d:
                        best_d = d
                        nearest = a
            if nearest is not None:
                nearest.amount -= 2
                # Brief visual laser beam.
                beam = entities.LaserBeam(self.station.position, nearest.position, parent=ursina_scene)
                impact = entities.MiningImpact(nearest.position, nearest.res_type, parent=ursina_scene)
                invoke(lambda b=beam: destroy(b), delay=0.3)

        # Economy and machine gameplay; no combat abilities.
        # Legacy defense gameplay is replaced by machine output and basic mining.
        # Drone AI.
        for d_state in self.state.get("drones", []):
            drone_vis = self.drone_vis_map.get(d_state.get("id"))
            if drone_vis:
                drone_vis.set_role_visual(d_state.get("role", "miner"))
                drone_vis.set_cargo_visual(d_state.get("cargo_resource"), d_state.get("cargo", 0))
                delivery = drones.drone_ai_step(drone_vis, d_state, self.asteroids, self.station, dt=time.dt)
                if delivery:
                    stored, overflow = logistics.deliver_drone_cargo(self.state, d_state)
                    if any(overflow.values()):
                        print(f"[Logistics] Storage full. Overflow lost: {overflow}")

        # Replenish depleted asteroids.
        alive = [a for a in self.asteroids if a.enabled and (hasattr(a, 'amount') and a.amount > 0)]
        if len(alive) < 5:
            region = "deep_belt" if research.unlocked(self.state, "deep_space_scanning") else "metallic_belt"
            new_asteroids = mining.spawn_asteroid_ring(self.station, count=2, parent=ursina_scene, region=region)
            for a in new_asteroids:
                a.on_click = lambda ast=a: self.select_asteroid(ast)
                self.asteroids.append(a)

        # Event lighting turns colony alerts into an environmental change.
        event_keys = {event.get("key") for event in self.state.get("events_active", [])}
        if hasattr(self, "ambient_light"):
            self.ambient_light.color = color.rgb(0.35, 0.45, 0.8) if "solar_storm" in event_keys else color.rgb(0.45, 0.12, 0.08) if "meteor_shower" in event_keys else color.rgb(0.2, 0.2, 0.3)

        # Game Logic
        st_state.energy_tick(self.state)
        research.generate_points(self.state, time.dt)
        self.update_world_landmarks()
        trade_message = regions.update_trade_routes(self.state)
        if trade_message:
            print(f"[Trade] {trade_message}")
        regions.milestones(self.state)
        if research.unlocked(self.state, "deep_space_scanning"):
            scene.set_region_atmosphere(self.stars, "deep_belt")
        events.roll_event(self.state, tick_interval=180)
        events.apply_events(self.state)
        self.state["tick"] = self.state.get("tick", 0) + 1
        self.state["time_played"] += time.dt
        self.state["score"] = int(
            self.state.get("resources", {}).get("gold", 0) * 10 +
            self.state.get("resources", {}).get("platinum", 0) * 20 +
            self.state.get("population", 0) * 5
        )

        # HUD
        if self.automation_menu:
            self.automation_menu["update"]()
        if self.director_panel:
            self.director_panel["refresh"]()
        if self.hud_elements:
            hud.update_hud(self.hud_elements, self.state, self.lang)
            # Machine status for the economy-focused game.
            machine_str = ""
            for k, info in config.MACHINES.items():
                count = self.state.get("machines", {}).get(k, 0)
                if count > 0:
                    machine_str += f"{info.get('name', k)}: {count} | "
            if machine_str:
                if self.hud_elements.get("selected_text"):
                    self.hud_elements["selected_text"].text = machine_str

        # Simple game-over condition.
        if self.state.get("resources", {}).get("energy", 0) <= 0 and self.state.get("population", 0) <= 0:
            if self.hud_elements:
                try:
                    self.hud_elements.get("energy_text").text = "GAME OVER"
                    self.hud_elements.get("energy_text").color = color.red
                except:
                    pass

    def load_state(self, data):
        if isinstance(data, dict) and "resources" in data:
            self.state = data
            print("[Game] Save loaded.")

    def save_state(self):
        savegame.save_slot("autosave_" + str(int(time.time())), self.state)
        print("[Game] Saved.")

def run_test():
    print("[run_test] Headless test started...")
    from ursina import Ursina
    test_app = Ursina(title="Test", window_type='none', borderless=True)
    station = entities.StationPart()
    ast = entities.Asteroid("ice", 30, Vec3(5, 0, 5))
    for i in range(5):
        test_app.step()
        ast.rotation += Vec3(1, 1, 0)
    assert station.enabled, "Station is not active"
    assert ast.enabled, "Asteroid is not active"
    print("[run_test] Headless test passed.")
    test_app.destroy()

def game_name(lang="en"):
    return i18n.t("title", lang)
