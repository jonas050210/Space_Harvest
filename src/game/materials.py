# game/materials.py — PBR Material Framework (Step 5: Texture/Shader structure)
# No real PBR textures included — pure code framework for material management
from . import config

class PBMaterial:
    """PBR Material framework — ready for future texture/shader integration."""
    def __init__(self, name, base_color, roughness=0.5, metallic=0.0):
        self.name = name
        self.base_color = base_color
        self.roughness = roughness
        self.metallic = metallic

    def apply_to_entity(self, entity):
        """Apply material properties to Ursina entity (simulated)."""
        # In full implementation: load texture maps, set shader parameters
        entity.color = base_color
        print(f"[Materials] Applied {self.name} to entity (PBR framework).")

# Predefined materials for the colony
MATERIALS = {
    "ice": PBMaterial("Ice", config.RESOURCES["ice"]["color"], roughness=0.9, metallic=0.0),
    "iron": PBMaterial("Iron", config.RESOURCES["iron"]["color"], roughness=0.4, metallic=0.8),
    "gold": PBMaterial("Gold", config.RESOURCES["gold"]["color"], roughness=0.2, metallic=1.0),
    "silver": PBMaterial("Silver", config.RESOURCES["silver"]["color"], roughness=0.3, metallic=0.9),
    "platinum": PBMaterial("Platinum", config.RESOURCES["platinum"]["color"], roughness=0.15, metallic=0.95),
    "station_metal": PBMaterial("Station Metal", (60, 65, 75), roughness=0.5, metallic=0.7),
    "black_hole": PBMaterial("Black Hole", (0, 0, 0), roughness=1.0, metallic=0.0),
}
