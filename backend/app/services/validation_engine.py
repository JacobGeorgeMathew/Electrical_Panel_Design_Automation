from typing import List, Tuple
from shapely.geometry import box
from app.models.pdm import PhysicalComponent, PhysicalDesignModel, ValidationViolation


class ValidationEngine:
    """Performs 2D computational geometry clearance, boundary containment, and thermal safety checks."""

    def validate_pdm(self, pdm: PhysicalDesignModel) -> List[ValidationViolation]:
        violations = []

        components = pdm.components
        enc_w = pdm.enclosure_width
        enc_h = pdm.enclosure_height

        # 1. Component Overlap & Clearance Checks
        boxes = []
        for c in components:
            poly = box(c.position.x, c.position.y, c.position.x + c.width, c.position.y + c.height)
            boxes.append((c, poly))

        for i in range(len(boxes)):
            c1, poly1 = boxes[i]

            # Boundary containment check
            if c1.position.x < 0 or c1.position.x + c1.width > enc_w or c1.position.y < 0 or c1.position.y + c1.height > enc_h:
                violations.append(ValidationViolation(
                    type="BOUNDARY",
                    severity="CRITICAL",
                    object_a=c1.id,
                    required_value=0,
                    actual_value=-1,
                    unit="mm",
                    message=f"Component {c1.name} ({c1.id}) exceeds panel enclosure boundary."
                ))

            for j in range(i + 1, len(boxes)):
                c2, poly2 = boxes[j]

                # Overlap check
                if poly1.intersects(poly2):
                    inter_area = poly1.intersection(poly2).area
                    if inter_area > 0.01:
                        violations.append(ValidationViolation(
                            type="OVERLAP",
                            severity="CRITICAL",
                            object_a=c1.id,
                            object_b=c2.id,
                            required_value=0.0,
                            actual_value=round(inter_area, 1),
                            unit="mm²",
                            message=f"Collision detected between {c1.name} and {c2.name}."
                        ))

                # Clearance distance check
                dist = poly1.distance(poly2)
                min_req = 15.0 if (c1.category == "MCCB" or c2.category == "MCCB") else 4.0
                if 0 < dist < min_req:
                    violations.append(ValidationViolation(
                        type="CLEARANCE",
                        severity="WARNING",
                        object_a=c1.id,
                        object_b=c2.id,
                        required_value=min_req,
                        actual_value=round(dist, 1),
                        unit="mm",
                        message=f"Clearance between {c1.id} and {c2.id} ({round(dist, 1)}mm) is less than required {min_req}mm."
                    ))

        # 2. Thermal Density Index Check
        vol_liters = (enc_w * enc_h * pdm.enclosure_depth) / 1,000,000.0
        thermal_index = pdm.total_heat_loss_watts / max(1.0, (enc_w * enc_h * pdm.enclosure_depth) / 1000000.0)
        pdm.thermal_density_index = round(thermal_index, 3)

        if thermal_index > 0.45:
            violations.append(ValidationViolation(
                type="THERMAL",
                severity="WARNING",
                object_a="ENCLOSURE",
                required_value=0.45,
                actual_value=round(thermal_index, 3),
                unit="W/L",
                message=f"High thermal load density ({round(thermal_index, 3)} W/L). Forced ventilation louvers recommended."
            ))

        return violations
