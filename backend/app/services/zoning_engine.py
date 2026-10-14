from typing import List
from app.models.pdm import PhysicalZone


class ZoningEngine:
    """Assigns components to functional panel zones based on category rules."""

    def get_default_zones(self, width: float, height: float) -> List[PhysicalZone]:
        return [
            PhysicalZone(name="INCOMING", x_min=30, x_max=width-30, y_min=height*0.75, y_max=height-30),
            PhysicalZone(name="PROTECTION", x_min=30, x_max=width-30, y_min=height*0.60, y_max=height*0.75),
            PhysicalZone(name="BUSBAR", x_min=30, x_max=width-30, y_min=height*0.50, y_max=height*0.60),
            PhysicalZone(name="DISTRIBUTION", x_min=30, x_max=width-30, y_min=height*0.25, y_max=height*0.50),
            PhysicalZone(name="TERMINAL", x_min=30, x_max=width-30, y_min=height*0.08, y_max=height*0.25),
            PhysicalZone(name="CABLE_ENTRY", x_min=30, x_max=width-30, y_min=30, y_max=height*0.08)
        ]

    def classify_zone(self, category: str) -> str:
        if category == "MCCB":
            return "INCOMING"
        elif category == "SPD":
            return "PROTECTION"
        elif category == "BUSBAR":
            return "BUSBAR"
        elif category == "MCB":
            return "DISTRIBUTION"
        elif category in ["TERMINAL", "NEUTRAL_BAR", "EARTH_BAR"]:
            return "TERMINAL"
        else:
            return "DISTRIBUTION"
