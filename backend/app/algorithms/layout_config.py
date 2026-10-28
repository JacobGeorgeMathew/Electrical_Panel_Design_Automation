"""Configuration for the layout (placement) layer.

Everything the solver needs to be tuned lives here, so the algorithm itself
contains no magic numbers and can later be fed from rules.json / the DB.
All lengths are in millimetres. Origin = lower-left-front of the enclosure.
"""
from dataclasses import dataclass, field
from typing import Dict, Set


@dataclass
class LayoutWeights:
    # Each term is normalised to "average deviation in grid cells", so the
    # weights are directly comparable (Pllana-style weighted multi-objective).
    wire_length: float = 1.0
    thermal: float = 0.8
    zone: float = 3.0


@dataclass
class LayoutConfig:
    grid_mm: int = 5                 # snap grid (bigger = faster solve)
    margin_x: float = 60.0
    margin_bottom: float = 40.0
    margin_top: float = 40.0
    device_gap_x: float = 4.0        # side clearance between DIN devices
    duct_gap_y: float = 50.0         # wiring-duct space between DIN rows
    plate_clearance: float = 20.0    # clearance around plate-mounted items
    wire_clearance: float = 5.0      # route obstacle buffer, independent of plate spacing
    thermal_density_limit_w_per_l: float = 0.45
    fill_factor: float = 0.85        # max rail utilisation when sizing rows
    z_din: float = 30.0
    z_plate: float = 20.0
    rail_z: float = 25.0
    duct_width_mm: float = 0.0  # zero keeps the standalone legacy placement API
    duct_edge_mm: float = 5.0
    duct_device_clearance_mm: float = 15.0

    solver_time_s: float = 5.0
    solver_deterministic_time: float = 0.5
    workers: int = 1                 # 1 = reproducible; raise for speed
    seed: int = 0

    weights: LayoutWeights = field(default_factory=LayoutWeights)

    din_categories: Set[str] = field(default_factory=lambda: {
        "MCB", "SPD", "TERMINAL", "CONTACTOR", "RELAY", "OVERLOAD",
        "MOTOR_STARTER"})
    plate_categories: Set[str] = field(default_factory=lambda: {
        "MCCB", "BUSBAR", "NEUTRAL_BAR", "EARTH_BAR"})

    # 0.0 = bottom of panel (cable entry side), 1.0 = top (hot / incoming)
    preferred_height: Dict[str, float] = field(default_factory=lambda: {
        "MCCB": 0.95, "SPD": 0.90, "BUSBAR": 0.60, "MCB": 0.50,
        "CONTACTOR": 0.65, "RELAY": 0.55, "OVERLOAD": 0.45,
        "NEUTRAL_BAR": 0.30, "EARTH_BAR": 0.05, "TERMINAL": 0.0})

    zone_names: Dict[str, str] = field(default_factory=lambda: {
        "MCCB": "INCOMING", "SPD": "PROTECTION", "BUSBAR": "BUSBAR",
        "MCB": "DISTRIBUTION", "CONTACTOR": "SWITCHING",
        "RELAY": "SWITCHING", "OVERLOAD": "SWITCHING",
        "TERMINAL": "TERMINAL", "NEUTRAL_BAR": "TERMINAL",
        "EARTH_BAR": "TERMINAL"})

    # Presentation only - ideally move to the frontend later.
    colors: Dict[str, str] = field(default_factory=lambda: {
        "MCCB": "#EF4444", "SPD": "#F59E0B", "BUSBAR": "#EAB308",
        "MCB": "#3B82F6", "CONTACTOR": "#A78BFA", "RELAY": "#22C55E",
        "OVERLOAD": "#F97316", "TERMINAL": "#8B5CF6",
        "NEUTRAL_BAR": "#06B6D4", "EARTH_BAR": "#10B981"})

    # ---- helpers -------------------------------------------------------
    def is_din(self, comp) -> bool:
        mounting = (getattr(comp, "mounting", "") or "").upper()
        if mounting in ("DIN", "DIN_RAIL", "RAIL"):
            return True
        if mounting == "PLATE":
            return False
        return comp.category in self.din_categories

    def pref_height(self, comp) -> float:
        return self.preferred_height.get(comp.category, 0.5)

    def zone_of(self, comp) -> str:
        return self.zone_names.get(comp.category, "GENERAL")

    def color_of(self, comp) -> str:
        return self.colors.get(comp.category, "#9CA3AF")
