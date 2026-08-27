#!/usr/bin/env python3
"""Start the game or run its self-test."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the game module early so Ursina can discover it.
from game import main as gm
from ursina import camera

# Global game-object reference, recognized by Ursina as a module symbol.
_game_obj = None

def update():
    global _game_obj
    if _game_obj is not None:
        _game_obj.update()

def input(key):
    global _game_obj
    if _game_obj is None:
        return
    if key == 'escape':
        # Toggle the menu.
        if _game_obj.menu_open is not None:
            _game_obj.menu_open()
            _game_obj.paused = not _game_obj.paused
        else:
            _game_obj.paused = not _game_obj.paused
    if key == 'tab':
        _game_obj.toggle_director()
    if key == '1':
        _game_obj.set_camera_preset("overview")
    if key == '2':
        _game_obj.set_camera_preset("industry")
    if key == '3':
        _game_obj.set_camera_preset("deep_space")
    if key == 's':
        _game_obj.save_state()
    if key == 'l':
        from game import savegame
        saves = savegame.list_saves()
        if saves:
            data = savegame.load_slot(saves[0].replace(".json", ""))
            if data:
                _game_obj.load_state(data)
    # Scroll-wheel zoom controls.
    if key == 'scroll up':
        if _game_obj is not None:
            if not hasattr(_game_obj, 'zoom_target'):
                _game_obj.zoom_target = camera.position.y
            _game_obj.zoom_target += 3
    if key == 'scroll down':
        if _game_obj is not None:
            if not hasattr(_game_obj, 'zoom_target'):
                _game_obj.zoom_target = camera.position.y
            _game_obj.zoom_target -= 3
    # Entity on_click handlers process mouse clicks.

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="run the headless self-test only")
    args = parser.parse_args()
    if args.test:
        gm.run_test()
        return
    # Create the Ursina application.
    from ursina import Ursina, window
    import game.settings as st_settings
    lang = st_settings.load().get("language", "en")
    # Create Ursina once per process.
    from ursina import Ursina
    # Ursina is initialized here as the application singleton.
    # Ursina is a singleton, so create it here.
    # start.py is the application entry point, so initialize it directly.
    # Provide the localized title with standard window options.
    # Ursina creates a window automatically unless window_type is 'none'.
    app_obj = Ursina(title=gm.game_name(lang=lang), borderless=False)
    window.color = (0, 0, 0)
    # Create the game object and build the scene.
    global _game_obj
    _game_obj = gm.Game()
    _game_obj.lang = lang
    _game_obj.build_scene()
    _game_obj.paused = False
    # Start the application.
    app_obj.run()

if __name__ == "__main__":
    main()
