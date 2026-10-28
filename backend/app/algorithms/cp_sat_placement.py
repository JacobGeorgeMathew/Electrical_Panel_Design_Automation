"""Constraint-based component placement (OR-Tools CP-SAT).

Model
-----
* DIN-mounted devices  -> choose a rail row (one-hot) + x position.
  Per-row NoOverlap on x-intervals (inflated by the side gap).
* Plate-mounted items  -> free (x, y) rectangles, NoOverlap2D with clearance,
  and each must lie entirely above or below every rail band.
HARD constraints: inside enclosure, no overlap, clearance, mounting type.
SOFT objective (weights in LayoutConfig): wire length (from real connections),
thermal (hot items high), zone/height preference.
The solver tries the fewest rails first and adds rails only if infeasible, so
the result is the most compact layout for the given enclosure.
"""
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from app.algorithms.layout_config import LayoutConfig
from app.models.cem import ComponentRef
from app.models.pdm import DINRail, PhysicalComponent, Position3D

try:
    from ortools.sat.python import cp_model
except ImportError:  # pragma: no cover
    cp_model = None

Connection = Tuple[str, str]


@dataclass
class LayoutResult:
    feasible: bool
    status: str                       # OPTIMAL / FEASIBLE / INFEASIBLE / ...
    message: str = ""
    components: List[PhysicalComponent] = field(default_factory=list)
    rails: List[DINRail] = field(default_factory=list)
    n_rows: int = 0
    objective: Optional[float] = None
    best_bound: Optional[float] = None
    solve_time_s: float = 0.0
    violations: List[dict] = field(default_factory=list)


def derive_default_connections(components: Sequence[ComponentRef]) -> List[Connection]:
    """Fallback only. In the real pipeline pass pairs derived from the netlist."""
    by = lambda cat: [c for c in components if c.category == cat]
    inc, bus, spd = by("MCCB"), by("BUSBAR"), by("SPD")
    mcb, term = by("MCB"), by("TERMINAL")
    pairs: List[Connection] = []
    if inc and bus:
        pairs.append((inc[0].id, bus[0].id))
    if spd and bus:
        pairs.append((spd[0].id, bus[0].id))
    if bus:
        pairs += [(bus[0].id, m.id) for m in mcb]
    pairs += [(m.id, t.id) for m, t in zip(mcb, term)]
    return pairs


class CPSATPlacementOptimizer:
    def __init__(self, config: Optional[LayoutConfig] = None):
        self.cfg = config or LayoutConfig()

    # Backward-compatible entry point (same signature as the old class).
    def optimize_placement(self, components, enclosure_width, enclosure_height,
                           enclosure_depth=0.0, zones_map=None, connections=None):
        r = self.solve(components, enclosure_width, enclosure_height, connections)
        return r.components, r.rails

    # ------------------------------------------------------------------
    def solve(self, components: Sequence[ComponentRef], enclosure_width: float,
              enclosure_height: float,
              connections: Optional[Sequence[Connection]] = None) -> LayoutResult:
        if cp_model is None:
            raise RuntimeError("ortools is required: pip install ortools")
        cfg, t0 = self.cfg, time.time()
        din = [c for c in components if cfg.is_din(c)]
        plate = [c for c in components if not cfg.is_din(c)]

        rail_len = enclosure_width - 2 * cfg.margin_x
        usable_h = enclosure_height - cfg.margin_bottom - cfg.margin_top
        for c in components:
            if c.width > rail_len or c.height > usable_h:
                return LayoutResult(False, "INFEASIBLE",
                                    f"{c.id} ({c.width}x{c.height}) does not fit the enclosure")

        ids = {c.id for c in components}
        raw = connections if connections is not None else derive_default_connections(components)
        conns = [(a, b) for a, b in raw if a in ids and b in ids and a != b]

        din_h = max((c.height for c in din), default=0.0)
        pitch = din_h + cfg.duct_gap_y
        max_rows = int(usable_h // pitch) if din else 0

        if din:
            width_n = max(1, math.ceil(sum(c.width + cfg.device_gap_x for c in din)
                                       / (rail_len * cfg.fill_factor)))
            per_zone: Dict[str, float] = {}
            for c in din:
                per_zone[cfg.zone_of(c)] = per_zone.get(cfg.zone_of(c), 0) + c.width + cfg.device_gap_x
            zone_n = sum(max(1, math.ceil(w / (rail_len * cfg.fill_factor))) for w in per_zone.values())
            n_start = max(width_n, min(zone_n, max_rows))
            if n_start > max_rows:
                return LayoutResult(False, "INFEASIBLE",
                                    f"DIN devices need >= {n_start} rail rows, enclosure fits {max_rows}")
            row_options = range(n_start, max_rows + 1)
        else:
            row_options = [0]

        result = LayoutResult(False, "INFEASIBLE", "no row count produced a feasible layout")
        for n in row_options:
            result = self._solve_rows(din, plate, conns, enclosure_width,
                                      enclosure_height, n, pitch, din_h)
            if result.feasible:
                break
        result.solve_time_s = round(time.time() - t0, 3)
        if result.feasible:
            result.violations = validate_layout(result.components, enclosure_width,
                                                enclosure_height, cfg)
        return result

    # ------------------------------------------------------------------
    def _solve_rows(self, din, plate, conns, W_mm, H_mm, n, pitch, din_h) -> LayoutResult:
        cfg = self.cfg
        g = cfg.grid_mm
        G = lambda v: int(math.ceil(v / g))
        Wg, Hg = int(W_mm // g), int(H_mm // g)
        mx, mb, mt = G(cfg.margin_x), G(cfg.margin_bottom), G(cfg.margin_top)
        rail_len_g = Wg - 2 * mx
        gapx, clr = G(cfg.device_gap_x), G(cfg.plate_clearance)
        pitch_g, dinh_g = G(pitch), G(din_h)
        rail_y = [mb + k * pitch_g for k in range(n)]

        m = cp_model.CpModel()
        cx: Dict[str, object] = {}
        cy: Dict[str, object] = {}
        zone_terms: list = []

        def occupied_width(c):
            # Terminals follow the same declared DIN clearance as other devices.
            return G(c.width)+gapx

        # ---- DIN devices: row choice + x ---------------------------------
        x_var, row_sel = {}, {}
        row_iv = [[] for _ in range(n)]
        for c in din:
            wg, hg = G(c.width), G(c.height)
            w = occupied_width(c)
            x = m.NewIntVar(mx, mx + rail_len_g - wg, f"x_{c.id}")
            b = [m.NewBoolVar(f"b_{c.id}_{r}") for r in range(n)]
            m.AddExactlyOne(b)
            for r in range(n):
                row_iv[r].append(m.NewOptionalIntervalVar(x, w, x + w, b[r], f"iv_{c.id}_{r}"))
            x_var[c.id], row_sel[c.id] = x, b
            cx[c.id] = x + wg // 2
            cy[c.id] = sum(b[r] * (rail_y[r] + hg // 2) for r in range(n))
            target = round(cfg.pref_height(c) * (n - 1))
            zone_terms.append(sum(b[r] * abs(r - target) * pitch_g for r in range(n)))
        for r in range(n):
            m.AddNoOverlap(row_iv[r])

        # ---- Plate items: free rectangles outside rail bands -------------
        px, py = {}, {}
        xs, ys = [], []
        for c in plate:
            wg, hg = G(c.width), G(c.height)
            x = m.NewIntVar(mx, Wg - mx - wg, f"px_{c.id}")
            y = m.NewIntVar(mb, Hg - mt - hg, f"py_{c.id}")
            xs.append(m.NewIntervalVar(x, wg + clr, x + wg + clr, f"ix_{c.id}"))
            ys.append(m.NewIntervalVar(y, hg + clr, y + hg + clr, f"iy_{c.id}"))
            for k in range(n):
                above = m.NewBoolVar(f"above_{c.id}_{k}")
                m.Add(y >= rail_y[k] + dinh_g + clr).OnlyEnforceIf(above)
                m.Add(y + hg + clr <= rail_y[k]).OnlyEnforceIf(above.Not())
            px[c.id], py[c.id] = x, y
            cx[c.id], cy[c.id] = x + wg // 2, y + hg // 2
            target = int(mb + cfg.pref_height(c) * max(0, Hg - mt - hg - mb))
            dev = m.NewIntVar(0, Hg, f"dev_{c.id}")
            m.AddAbsEquality(dev, y - target)
            zone_terms.append(dev)
        if len(xs) > 1:
            m.AddNoOverlap2D(xs, ys)

        # Reserve the physical troughs below/above DIN bands across the plate.
        # Plate devices must sit outside these bands, not just outside the rails.
        if cfg.duct_width_mm:
            dw, dc = G(cfg.duct_width_mm), G(cfg.duct_device_clearance_mm)
            duct_y = [mb-dc-dw] + [y+dinh_g+dc for y in rail_y]
            for c in plate:
                for i, dy in enumerate(duct_y):
                    above = m.NewBoolVar(f'over_duct_{c.id}_{i}')
                    m.Add(py[c.id] >= dy+dw+dc).OnlyEnforceIf(above)
                    m.Add(py[c.id]+G(c.height)+dc <= dy).OnlyEnforceIf(above.Not())

        # A terminal strip is contiguous and includes room for its two end stops.
        terminal_devices = [c for c in din if c.category=='TERMINAL']
        if terminal_devices:
            for c in din:
                if c.category != 'TERMINAL':
                    for r in range(n):
                        m.Add(row_sel[c.id][r] + row_sel[terminal_devices[0].id][r] <= 1)
        for a, b in zip(terminal_devices, terminal_devices[1:]):
            for r in range(n):
                m.Add(row_sel[a.id][r] == row_sel[b.id][r])
            m.Add(x_var[b.id] == x_var[a.id] + occupied_width(a))
        for c in terminal_devices:
            m.Add(x_var[c.id] >= mx + G(15))
            m.Add(x_var[c.id] + G(c.width) <= Wg-mx-G(15))

        # ---- Objective (soft) --------------------------------------------
        wts, terms = cfg.weights, []
        if conns:
            cw = round(1000 * wts.wire_length / len(conns))
            for i, (a, b) in enumerate(conns):
                dx = m.NewIntVar(0, Wg, f"dx{i}")
                dy = m.NewIntVar(0, Hg, f"dy{i}")
                m.AddAbsEquality(dx, cx[a] - cx[b])
                m.AddAbsEquality(dy, cy[a] - cy[b])
                terms.append(cw * (dx + dy))
        allc = list(din) + list(plate)
        total_heat = sum(c.heat_loss for c in allc)
        if total_heat > 0:
            for c in allc:
                coef = round(1000 * wts.thermal * c.heat_loss / total_heat)
                if coef:
                    terms.append(coef * (Hg - cy[c.id]))
        if zone_terms:
            zc = round(1000 * wts.zone / len(zone_terms))
            terms += [zc * t for t in zone_terms]
        if terms:
            m.Minimize(sum(terms))

        s = cp_model.CpSolver()
        # The fixed seed, single worker, and deterministic search budget make
        # repeat regeneration stable while retaining the configured runtime cap.
        s.parameters.max_time_in_seconds = cfg.solver_time_s
        s.parameters.max_deterministic_time = cfg.solver_deterministic_time
        s.parameters.num_workers = cfg.workers
        s.parameters.random_seed = cfg.seed
        status = s.Solve(m)
        name = s.StatusName(status)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return LayoutResult(False, name, f"no feasible layout with {n} rail row(s)", n_rows=n)

        # ---- Extract -----------------------------------------------------
        out: List[PhysicalComponent] = []
        used = set()
        for c in din:
            r = next(r for r in range(n) if s.Value(row_sel[c.id][r]))
            used.add(r)
            out.append(self._mk(c, s.Value(x_var[c.id]) * g, rail_y[r] * g,
                                cfg.z_din, f"RAIL-{r + 1:02d}"))
        for c in plate:
            out.append(self._mk(c, s.Value(px[c.id]) * g, s.Value(py[c.id]) * g,
                                cfg.z_plate, None))
        rails = [DINRail(id=f"RAIL-{r + 1:02d}", label=f"DIN Rail {r + 1}",
                         x=cfg.margin_x, y=rail_y[r] * g, z=cfg.rail_z,
                         length=W_mm - 2 * cfg.margin_x) for r in sorted(used)]
        return LayoutResult(True, name, "ok", out, rails, n,
                            s.ObjectiveValue() if terms else None,
                            s.BestObjectiveBound() if terms else None)

    def _mk(self, c, x, y, z, rail_id) -> PhysicalComponent:
        return PhysicalComponent(
            id=f"PDM-{c.id}", cem_component_id=c.id, name=c.name, category=c.category,
            position=Position3D(x=x, y=y, z=z), width=c.width, height=c.height,
            depth=c.depth, rail_id=rail_id, zone_name=self.cfg.zone_of(c),
            heat_loss_watts=c.heat_loss, cad_model=c.cad_model,
            terminals=c.terminals,
            color_hex=self.cfg.color_of(c))


# ----------------------------------------------------------------------
def validate_layout(placed: Sequence[PhysicalComponent], W: float, H: float,
                    cfg: LayoutConfig) -> List[dict]:
    """Independent geometric check of the solver output (never trust the solver blindly)."""
    v: List[dict] = []
    for p in placed:
        x, y = p.position.x, p.position.y
        if x < 0 or y < 0 or x + p.width > W or y + p.height > H:
            v.append({"type": "BOUNDARY", "object_a": p.cem_component_id, "object_b": "ENCLOSURE",
                      "status": "FAIL", "severity": "CRITICAL"})
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            ax, ay, bx, by = a.position.x, a.position.y, b.position.x, b.position.y
            gap = max(ax - (bx + b.width), bx - (ax + a.width),
                      ay - (by + b.height), by - (ay + a.height))
            same_rail = a.rail_id is not None and a.rail_id == b.rail_id
            required = cfg.device_gap_x if same_rail else (
                cfg.plate_clearance if (a.rail_id is None or b.rail_id is None) else 0.0)
            if gap < required - 1e-6:
                v.append({"type": "OVERLAP" if gap < 0 else "CLEARANCE",
                          "object_a": a.cem_component_id, "object_b": b.cem_component_id,
                          "required": required, "actual": round(gap, 2),
                          "status": "FAIL", "severity": "CRITICAL"})
    return v
