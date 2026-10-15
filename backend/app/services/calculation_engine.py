import math
from typing import Dict, List
from app.models.cem import CalculationResult


class CalculationEngine:
    """Deterministic Engineering Calculation Service for Distribution Boards."""

    def calculate_db_parameters(self, requirements_dict: Dict[str, float]) -> List[CalculationResult]:
        voltage = float(requirements_dict.get("supply_voltage", 415))
        phases = int(requirements_dict.get("phases", 3))
        incomer_rating = float(requirements_dict.get("incomer_rating", 250))
        num_feeders = int(requirements_dict.get("num_feeders", 12))
        power_factor = 0.85
        spare_capacity = float(requirements_dict.get("spare_capacity_pct", 20)) / 100.0

        results = []

        # 1. Total Panel Apparent Power Capacity (kVA)
        if phases == 3:
            total_capacity_kva = (math.sqrt(3) * voltage * incomer_rating) / 1000.0
        else:
            total_capacity_kva = (voltage * incomer_rating) / 1000.0

        results.append(CalculationResult(
            id="CALC_001",
            type="total_capacity",
            label="Total Panel Capacity",
            value=round(total_capacity_kva, 2),
            unit="kVA",
            formula_used="P = √3 * V * I / 1000" if phases == 3 else "P = V * I / 1000",
            status="VALID",
            notes="Maximum apparent power rating based on main incomer rating"
        ))

        # 2. Design Load Current with Diversity & Spare Factor
        diversity_factor = 0.75  # Standard DB diversity factor
        design_load_current = incomer_rating * diversity_factor * (1.0 + spare_capacity)
        results.append(CalculationResult(
            id="CALC_002",
            type="design_current",
            label="Design Load Current (I_d)",
            value=round(design_load_current, 1),
            unit="A",
            formula_used="I_d = I_incomer * K_diversity * (1 + Spare%)",
            status="VALID"
        ))

        # 3. Minimum Busbar Rating
        busbar_rating = incomer_rating * 1.25  # 125% safety margin rule
        results.append(CalculationResult(
            id="CALC_003",
            type="busbar_rating",
            label="Minimum Busbar Continuous Ampacity",
            value=round(busbar_rating, 0),
            unit="A",
            formula_used="I_busbar >= 1.25 * I_incomer",
            status="VALID"
        ))

        # 4. Average Feeder Current & Sizing
        active_feeders = max(1, num_feeders)
        feeder_current = (incomer_rating * 0.8) / active_feeders
        results.append(CalculationResult(
            id="CALC_004",
            type="feeder_current",
            label="Average Feeder Current Rating",
            value=round(feeder_current, 1),
            unit="A",
            formula_used="I_feeder = (0.8 * I_incomer) / N_feeders",
            status="VALID"
        ))

        # 5. Main Cable Conductor Sizing (Copper)
        # Empirical current density: ~2.5 A/mm2 for heavy copper bus/cable
        conductor_area_mm2 = incomer_rating / 2.2
        results.append(CalculationResult(
            id="CALC_005",
            type="conductor_size",
            label="Main Incomer Cable Conductor Area",
            value=round(conductor_area_mm2, 1),
            unit="mm²",
            formula_used="A_mm2 = I_incomer / Current_Density",
            status="VALID"
        ))

        # 6. Estimated Internal Voltage Drop %
        # Standard internal DB drop across MCCB + Busbar + Terminals (~15 meters equivalent run)
        length_m = 15.0
        r_per_km = 0.193  # 95mm2 Cu resistance
        v_drop = (math.sqrt(3) * design_load_current * length_m * r_per_km / 1000.0) if phases == 3 else (2 * design_load_current * length_m * r_per_km / 1000.0)
        v_drop_pct = (v_drop / voltage) * 100.0
        results.append(CalculationResult(
            id="CALC_006",
            type="voltage_drop",
            label="Internal Voltage Drop",
            value=round(v_drop_pct, 2),
            unit="%",
            formula_used="ΔV% = (√3 * I * L * R / V_nom) * 100",
            status="VALID" if v_drop_pct <= 3.0 else "WARNING",
            notes="Simplified estimate only; this is not a standards compliance determination."
        ))

        # 7. Estimated Heat Loss Dissipation (Watts)
        # Base loss: MCCB ~35W, Busbars ~15W, Feeders ~2W each
        total_heat_loss = 35.0 + 15.0 + (num_feeders * 2.5)
        results.append(CalculationResult(
            id="CALC_007",
            type="total_heat_loss",
            label="Total Thermal Heat Loss",
            value=round(total_heat_loss, 1),
            unit="W",
            formula_used="Q_total = Q_mccb + Q_busbar + ∑(Q_mcb)",
            status="VALID"
        ))

        return results
