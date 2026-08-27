"""English-language strings for the Asteroid Colony interface."""

TR = {
    "en": {
        "title": "Asteroid Colony",
        "start": "Start", "load": "Load", "settings": "Settings", "quit": "Quit",
        "save": "Save", "new": "New", "resume": "Resume",
        "resources": "Resources", "energy": "Energy", "population": "Population",
        "build_drone": "Build Drone", "build_module": "Build Module", "upgrade": "Upgrade",
        "pause": "Pause", "difficulty": "Difficulty", "language": "Language",
        "easy": "Easy", "medium": "Medium", "hard": "Hard",
        "drones": "Drones", "modules": "Modules", "station": "Station",
        "click_asteroid": "Select Asteroid", "click_station": "Select Station",
        "event": "Event", "shield_active": "Shield Active", "meteor_shower": "Meteor Shower",
        "solar_storm": "Solar Storm", "trade_fleet": "Trade Fleet", "gold_rush": "Gold Rush",
        "mission_complete": "Mission Complete", "game_over": "Game Over", "victory": "Victory",
        "highscore": "High Score", "en": "English",
    },
}

def t(key, lang="en"):
    """Return an English interface label, falling back to the key when absent."""
    return TR["en"].get(key, key)
