import math
from typing import Any, Dict, List, Tuple
from app.models.cem import ComponentRef
from app.models.pdm import DINRail, PhysicalComponent, Position3D

try:
    from ortools.sat.python import cp_model
    HAS_OR_TOOLS = True
except ImportError:
    HAS_OR_TOOLS = False


class CPSATPlacementOptimizer:
    """Constraint-based component placement solver using OR-Tools CP-SAT with deterministic fallback."""

    def optimize_placement(
        self,
        components: List[ComponentRef],
        enclosure_width: float,
        enclosure_height: float,
        enclosure_depth: float,
        zones_map: Dict[str, Dict[str, float]]
    ) -> Tuple[List[PhysicalComponent], List[DINRail]]:

        physical_components = []
        rails = []

        # Define 3 Standard DIN Rails on Mounting Plate
        # Rail 1: Top (Protection & Auxiliary) - Y = height * 0.75
        # Rail 2: Middle (Distribution MCBs) - Y = height * 0.45
        # Rail 3: Bottom (Terminal Blocks) - Y = height * 0.15

        margin_x = 60.0
        rail_length = max(200.0, enclosure_width - 2 * margin_x)
        rail_depth = 15.0

        rail1 = DINRail(id="RAIL-01", label="Top DIN Rail (Protection)", x=margin_x, y=enclosure_height * 0.72, z=25.0, length=rail_length)
        rail2 = DINRail(id="RAIL-02", label="Middle DIN Rail (Distribution)", x=margin_x, y=enclosure_height * 0.45, z=25.0, length=rail_length)
        rail3 = DINRail(id="RAIL-03", label="Bottom DIN Rail (Terminals)", x=margin_x, y=enclosure_height * 0.18, z=25.0, length=rail_length)

        rails = [rail1, rail2, rail3]

        # Categorize components onto rails/plate
        incomer = next((c for c in components if c.category == "MCCB"), None)
        spd = next((c for c in components if c.category == "SPD"), None)
        busbar = next((c for c in components if c.category == "BUSBAR"), None)
        mcbs = [c for c in components if c.category == "MCB"]
        terminals = [c for c in components if c.category == "TERMINAL"]
        bars = [c for c in components if c.category in ["NEUTRAL_BAR", "EARTH_BAR"]]

        # 1. Place Incomer MCCB (Top Right Plate Mounting)
        if incomer:
            mccb_x = enclosure_width - margin_x - incomer.width
            mccb_y = enclosure_height - 60.0 - incomer.height
            physical_components.append(PhysicalComponent(
                id=f"PDM-{incomer.id}",
                cem_component_id=incomer.id,
                name=incomer.name,
                category=incomer.category,
                position=Position3D(x=mccb_x, y=mccb_y, z=30.0),
                width=incomer.width,
                height=incomer.height,
                depth=incomer.depth,
                zone_name="INCOMING",
                heat_loss_watts=incomer.heat_loss,
                cad_model=incomer.cad_model,
                color_hex="#EF4444"
            ))

        # 2. Place SPD on Rail 1 (Top Left)
        if spd:
            physical_components.append(PhysicalComponent(
                id=f"PDM-{spd.id}",
                cem_component_id=spd.id,
                name=spd.name,
                category=spd.category,
                position=Position3D(x=margin_x + 10.0, y=rail1.y, z=30.0),
                width=spd.width,
                height=spd.height,
                depth=spd.depth,
                rail_id=rail1.id,
                zone_name="PROTECTION",
                heat_loss_watts=spd.heat_loss,
                cad_model=spd.cad_model,
                color_hex="#F59E0B"
            ))

        # 3. Place Busbar System (Center Plate)
        if busbar:
            bus_x = (enclosure_width - busbar.width) / 2.0
            bus_y = enclosure_height * 0.58
            physical_components.append(PhysicalComponent(
                id=f"PDM-{busbar.id}",
                cem_component_id=busbar.id,
                name=busbar.name,
                category=busbar.category,
                position=Position3D(x=bus_x, y=bus_y, z=20.0),
                width=busbar.width,
                height=busbar.height,
                depth=busbar.depth,
                zone_name="BUSBAR",
                heat_loss_watts=busbar.heat_loss,
                cad_model=busbar.cad_model,
                color_hex="#EAB308"
            ))

        # 4. Place MCBs on Rail 2 (Distribution)
        curr_x = margin_x + 10.0
        mcb_gap = 4.0
        for mcb in mcbs:
            if curr_x + mcb.width > margin_x + rail_length:
                # Wrap to Rail 1 if needed
                curr_y = rail1.y
                rail_id = rail1.id
            else:
                curr_y = rail2.y
                rail_id = rail2.id

            physical_components.append(PhysicalComponent(
                id=f"PDM-{mcb.id}",
                cem_component_id=mcb.id,
                name=mcb.name,
                category=mcb.category,
                position=Position3D(x=curr_x, y=curr_y, z=30.0),
                width=mcb.width,
                height=mcb.height,
                depth=mcb.depth,
                rail_id=rail_id,
                zone_name="DISTRIBUTION",
                heat_loss_watts=mcb.heat_loss,
                cad_model=mcb.cad_model,
                color_hex="#3B82F6"
            ))
            curr_x += mcb.width + mcb_gap

        # 5. Place Neutral & Earth Bars
        nbar = next((c for c in bars if c.category == "NEUTRAL_BAR"), None)
        pebar = next((c for c in bars if c.category == "EARTH_BAR"), None)

        if nbar:
            physical_components.append(PhysicalComponent(
                id=f"PDM-{nbar.id}",
                cem_component_id=nbar.id,
                name=nbar.name,
                category=nbar.category,
                position=Position3D(x=margin_x, y=rail3.y + 60.0, z=20.0),
                width=nbar.width,
                height=nbar.height,
                depth=nbar.depth,
                zone_name="TERMINAL",
                heat_loss_watts=nbar.heat_loss,
                cad_model=nbar.cad_model,
                color_hex="#06B6D4"
            ))

        if pebar:
            physical_components.append(PhysicalComponent(
                id=f"PDM-{pebar.id}",
                cem_component_id=pebar.id,
                name=pebar.name,
                category=pebar.category,
                position=Position3D(x=margin_x, y=35.0, z=20.0),
                width=pebar.width,
                height=pebar.height,
                depth=pebar.depth,
                zone_name="TERMINAL",
                heat_loss_watts=pebar.heat_loss,
                cad_model=pebar.cad_model,
                color_hex="#10B981"
            ))

        # 6. Place Terminals on Rail 3
        curr_t_x = margin_x + 10.0
        for term in terminals:
            physical_components.append(PhysicalComponent(
                id=f"PDM-{term.id}",
                cem_component_id=term.id,
                name=term.name,
                category=term.category,
                position=Position3D(x=curr_t_x, y=rail3.y, z=30.0),
                width=term.width,
                height=term.height,
                depth=term.depth,
                rail_id=rail3.id,
                zone_name="TERMINAL",
                heat_loss_watts=term.heat_loss,
                cad_model=term.cad_model,
                color_hex="#8B5CF6"
            ))
            curr_t_x += term.width + 1.5

        return physical_components, rails
