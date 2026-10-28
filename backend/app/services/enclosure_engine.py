from typing import Any, Dict, List, Optional
from app.repositories.enclosure_repository import EnclosureRepository
from app.models.pdm import EnclosureSpec


class EnclosureEngine:
    """Selects the minimum viable standard enclosure for the DB design."""

    def __init__(self, repo: Optional[EnclosureRepository] = None):
        self.repo = repo or EnclosureRepository()

    def candidates(self, total_components_width: float, total_heat_loss: float, ip_rating: str = "IP54",
                   thermal_density_limit_w_per_l: float = 0.45) -> List[EnclosureSpec]:
        # Estimate required panel dimensions
        # Estimate total DIN rail length required: total width + 30% margin for ducts/end stops
        required_width = max(500, total_components_width * 0.45)
        required_height = 700 if total_components_width < 800 else (900 if total_components_width < 1400 else 1100)

        ip_order={'IP31':1,'IP42':2,'IP54':3,'IP65':4}
        required_ip=ip_order.get(ip_rating,99)
        feasible=[]
        for row in self.repo.get_all():
            litres=row['width']*row['height']*row['depth']/1_000_000
            if (row['mounting_plate_width']>=required_width and row['mounting_plate_height']>=required_height
                and row.get('max_thermal_dissipation',0)>=total_heat_loss
                and ip_order.get(row.get('ip_rating'),0)>=required_ip
                and total_heat_loss/max(litres,1)<=thermal_density_limit_w_per_l+1e-9):
                feasible.append(EnclosureSpec(**row))
        return sorted(feasible,key=lambda e:(e.width*e.height,e.width*e.height*e.depth,e.id))

    def select_enclosure(self, total_components_width: float, total_heat_loss: float, ip_rating: str = "IP54",
                         thermal_density_limit_w_per_l: float = 0.45) -> Optional[EnclosureSpec]:
        feasible=self.candidates(total_components_width,total_heat_loss,ip_rating,thermal_density_limit_w_per_l)
        return feasible[0] if feasible else None
