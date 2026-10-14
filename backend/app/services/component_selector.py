from typing import Dict, List, Optional
from app.models.cem import ComponentRef
from app.repositories.component_repository import ComponentRepository


class ComponentSelector:
    """Selects physical electrical components based on engineering calculations."""

    def __init__(self, comp_repo: Optional[ComponentRepository] = None):
        self.comp_repo = comp_repo or ComponentRepository()

    def select_components(self, incomer_rating: float, num_feeders: int, phases: int = 3) -> List[ComponentRef]:
        selected = []

        # 1. Select Incomer MCCB
        mccb_candidates = self.comp_repo.filter_candidates(
            category="MCCB", min_current=incomer_rating, min_breaking_capacity=25, poles=3 if phases == 3 else 1
        )
        if not mccb_candidates:
            mccb_candidates = self.comp_repo.filter_candidates(category="MCCB")
        selected_mccb = mccb_candidates[0] if mccb_candidates else None

        if selected_mccb:
            selected.append(ComponentRef(
                id="QF001",
                catalog_id=selected_mccb["id"],
                name=selected_mccb["name"],
                category="MCCB",
                current_rating=selected_mccb["current_rating"],
                breaking_capacity=selected_mccb["breaking_capacity"],
                poles=selected_mccb["poles"],
                width=selected_mccb["width"],
                height=selected_mccb["height"],
                depth=selected_mccb["depth"],
                mounting=selected_mccb["mounting"],
                heat_loss=selected_mccb["heat_loss"],
                cad_model=selected_mccb["cad_model"],
                quantity=1,
                terminals=selected_mccb.get("terminals", [])
            ))

        # 2. Select Surge Protection Device (SPD)
        spd_candidates = self.comp_repo.filter_candidates(category="SPD")
        if spd_candidates:
            spd = spd_candidates[0]
            selected.append(ComponentRef(
                id="SPD001",
                catalog_id=spd["id"],
                name=spd["name"],
                category="SPD",
                current_rating=spd["current_rating"],
                breaking_capacity=spd["breaking_capacity"],
                poles=spd["poles"],
                width=spd["width"],
                height=spd["height"],
                depth=spd["depth"],
                mounting=spd["mounting"],
                heat_loss=spd["heat_loss"],
                cad_model=spd["cad_model"],
                quantity=1,
                terminals=spd.get("terminals", [])
            ))

        # 3. Select Busbar System
        busbar_candidates = self.comp_repo.filter_candidates(category="BUSBAR", min_current=incomer_rating)
        if not busbar_candidates:
            busbar_candidates = self.comp_repo.filter_candidates(category="BUSBAR")
        selected_busbar = busbar_candidates[0] if busbar_candidates else None

        if selected_busbar:
            selected.append(ComponentRef(
                id="BUS001",
                catalog_id=selected_busbar["id"],
                name=selected_busbar["name"],
                category="BUSBAR",
                current_rating=selected_busbar["current_rating"],
                breaking_capacity=selected_busbar["breaking_capacity"],
                poles=selected_busbar["poles"],
                width=selected_busbar["width"],
                height=selected_busbar["height"],
                depth=selected_busbar["depth"],
                mounting=selected_busbar["mounting"],
                heat_loss=selected_busbar["heat_loss"],
                cad_model=selected_busbar["cad_model"],
                quantity=1,
                terminals=selected_busbar.get("terminals", [])
            ))

        # 4. Select Outgoing Feeders (MCBs)
        mcb_16a = self.comp_repo.get_by_id("MCB_16A_1P_10KA") or self.comp_repo.filter_candidates("MCB")[0]
        mcb_32a = self.comp_repo.get_by_id("MCB_32A_1P_10KA") or mcb_16a
        mcb_40a_3p = self.comp_repo.get_by_id("MCB_40A_3P_10KA") or mcb_16a

        for i in range(1, num_feeders + 1):
            # Mix 1P and 3P MCBs realistically across feeders
            if i % 4 == 0 and phases == 3:
                template_mcb = mcb_40a_3p
            elif i % 2 == 0:
                template_mcb = mcb_32a
            else:
                template_mcb = mcb_16a

            selected.append(ComponentRef(
                id=f"QF{i+1:03d}",
                catalog_id=template_mcb["id"],
                name=f"Feeder Breaker {i} ({template_mcb['current_rating']}A)",
                category="MCB",
                current_rating=template_mcb["current_rating"],
                breaking_capacity=template_mcb["breaking_capacity"],
                poles=template_mcb["poles"],
                width=template_mcb["width"],
                height=template_mcb["height"],
                depth=template_mcb["depth"],
                mounting=template_mcb["mounting"],
                heat_loss=template_mcb["heat_loss"],
                cad_model=template_mcb["cad_model"],
                quantity=1,
                terminals=template_mcb.get("terminals", [])
            ))

        # 5. Select Neutral and Earth Bars
        n_bar = self.comp_repo.get_by_id("NEUTRAL_BAR_24WAY")
        if n_bar:
            selected.append(ComponentRef(
                id="NBAR01",
                catalog_id=n_bar["id"],
                name=n_bar["name"],
                category="NEUTRAL_BAR",
                current_rating=n_bar["current_rating"],
                breaking_capacity=0,
                poles=1,
                width=n_bar["width"],
                height=n_bar["height"],
                depth=n_bar["depth"],
                mounting=n_bar["mounting"],
                heat_loss=n_bar["heat_loss"],
                cad_model=n_bar["cad_model"],
                quantity=1,
                terminals=n_bar.get("terminals", [])
            ))

        pe_bar = self.comp_repo.get_by_id("EARTH_BAR_24WAY")
        if pe_bar:
            selected.append(ComponentRef(
                id="PEBAR01",
                catalog_id=pe_bar["id"],
                name=pe_bar["name"],
                category="EARTH_BAR",
                current_rating=pe_bar["current_rating"],
                breaking_capacity=0,
                poles=1,
                width=pe_bar["width"],
                height=pe_bar["height"],
                depth=pe_bar["depth"],
                mounting=pe_bar["mounting"],
                heat_loss=pe_bar["heat_loss"],
                cad_model=pe_bar["cad_model"],
                quantity=1,
                terminals=pe_bar.get("terminals", [])
            ))

        # 6. Select Terminal Blocks
        term = self.comp_repo.get_by_id("TERMINAL_BLOCKS_6MM") or self.comp_repo.filter_candidates("TERMINAL")[0]
        for i in range(1, num_feeders + 1):
            selected.append(ComponentRef(
                id=f"X{i:03d}",
                catalog_id=term["id"],
                name=f"Outgoing Terminal Strip X{i}",
                category="TERMINAL",
                current_rating=term["current_rating"],
                breaking_capacity=0,
                poles=1,
                width=term["width"],
                height=term["height"],
                depth=term["depth"],
                mounting=term["mounting"],
                heat_loss=term["heat_loss"],
                cad_model=term["cad_model"],
                quantity=1,
                terminals=term.get("terminals", [])
            ))

        return selected
