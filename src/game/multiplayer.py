"""Deterministic, transport-agnostic co-op session model.

This module deliberately does not open sockets. A network transport can submit
commands to this authoritative state model once the single-player simulation is stable.
"""

from copy import deepcopy


class MultiplayerSession:
    """Manage players, permissions, revisions, and conflict-safe commands."""

    ROLES = ("Mining", "Logistics", "Research", "Construction")

    def __init__(self, session_id="local-coop"):
        self.session_id = session_id
        self.players = {}
        self.revision = 0
        self.command_log = []

    def add_player(self, player_id, display_name=None):
        if player_id in self.players:
            return False, "Player already joined."
        role = self.ROLES[len(self.players) % len(self.ROLES)]
        self.players[player_id] = {"name": display_name or player_id, "role": role, "connected": True}
        return True, f"{display_name or player_id} joined as {role}."

    def remove_player(self, player_id):
        if player_id not in self.players:
            return False, "Player not found."
        self.players[player_id]["connected"] = False
        return True, "Player disconnected."

    def snapshot(self, game_state):
        return {"session_id": self.session_id, "revision": self.revision, "players": deepcopy(self.players), "state": deepcopy(game_state)}

    def apply_command(self, game_state, player_id, command, expected_revision):
        """Apply a validated deterministic command with optimistic concurrency."""
        if player_id not in self.players or not self.players[player_id]["connected"]:
            return False, "Player is not connected."
        if expected_revision != self.revision:
            return False, "Session changed; request a fresh snapshot."
        if not isinstance(command, dict) or command.get("type") not in {"assign_role", "research", "place_module"}:
            return False, "Unsupported command."
        self.revision += 1
        self.command_log.append({"revision": self.revision, "player": player_id, "command": deepcopy(command)})
        return True, "Command accepted."
