from typing import Any, Dict, List, Optional
from app.repositories.enclosure_repository import EnclosureRepository


class EnclosureEngine:
    """Selects the minimum viable standard enclosure for the DB design."""

    def __init__(self, repo: Optional[EnclosureRepository] = None):
        self.repo = repo or EnclosureRepository()

    def select_enclosure(self, total_components_width: float, total_heat_loss: float, ip_rating: str = "IP54") -> Dict[str, Any]:
        # Estimate required panel dimensions
        # Estimate total DIN rail length required: total width + 30% margin for ducts/end stops
        required_width = max(500, total_components_width * 0.45)
        required_height = 700 if total_components_width < 800 else (900 if total_components_width < 1400 else 1100)

        enclosure = self.repo.find_best_fit(
            min_width=required_width,
            min_height=required_height,
            min_thermal_dissipation=total_heat_loss,
            ip_rating=ip_rating
        )
        return enclosure
