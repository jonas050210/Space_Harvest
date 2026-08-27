"""Grid-based station placement validation and persistent layout data."""

GRID_LIMIT = 4


def valid_cell(cell):
    return isinstance(cell, (tuple, list)) and len(cell) == 2 and all(isinstance(value, int) and -GRID_LIMIT <= value <= GRID_LIMIT for value in cell)


def place_module(state, module_key, cell):
    """Place an owned module onto an unoccupied station-grid cell."""
    layout = state.setdefault("station_layout", {"occupied": [], "placements": []})
    cell = list(cell)
    if not valid_cell(cell):
        return False, "Choose a grid cell between -4 and 4."
    if cell in layout["occupied"]:
        return False, "That station cell is already occupied."
    if module_key not in state.get("modules", []):
        return False, "Build the module before placing it."
    layout["occupied"].append(cell)
    layout["placements"].append({"module": module_key, "cell": cell})
    return True, f"Placed {module_key.replace('_', ' ').title()} at {tuple(cell)}."


def placement_bonus(state):
    """Reward compact layouts with adjacent placed modules."""
    cells = [tuple(cell) for cell in state.get("station_layout", {}).get("occupied", [])]
    adjacent_pairs = sum(1 for x, y in cells for nx, ny in cells if (nx, ny) > (x, y) and abs(nx - x) + abs(ny - y) == 1)
    return min(0.25, adjacent_pairs * 0.02)
