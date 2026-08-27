# Code-based economy AI (Step 1: no machine learning).
# Simulates intelligent decisions for machine buying, resource management
from . import config, state as st_state

class AIEconomyEngine:
    """Simple code-based AI for economy decisions — no real machine learning."""
    def __init__(self, state):
        self.state = state

    def recommend_next_machine(self):
        """Recommend next machine based on current resources and efficiency."""
        resources = self.state.get("resources", {})
        machines = self.state.get("machines", {})
        # Simple logic: If iron is high, recommend mining drill; if gold is high, recommend refinery
        if resources.get("iron", 0) > 100 and machines.get("mining_drill", 0) < 3:
            return "mining_drill"
        elif resources.get("gold", 0) > 50 and machines.get("refinery", 0) < 2:
            return "refinery"
        elif resources.get("iron", 0) > 80 and machines.get("auto_transporter", 0) < 2:
            return "auto_transporter"
        return None

    def calculate_efficiency_score(self):
        """Calculate a simple efficiency score for the colony."""
        total_output = 0
        for key, info in config.MACHINES.items():
            count = self.state.get("machines", {}).get(key, 0)
            for res, val in info.get("output_per_tick", {}).items():
                total_output += val * count
        population = self.state.get("population", 1)
        return total_output / max(population, 1)
