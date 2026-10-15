from typing import Dict, List, Tuple
from app.models.cem import ComponentRef, ConnectionRef, NetRef
from app.models.electrical_graph import ElectricalGraphModel
from app.services.design_errors import DesignError


class NetlistEngine:
    """Creates deterministic electrical nets from the DB graph and component terminals."""

    def generate_netlist(self, graph: ElectricalGraphModel, components: List[ComponentRef],
                         voltage: float = 415.0, phases: int = 3) -> List[NetRef]:
        by_id = {component.id: component for component in components}
        by_category = {category: next((c for c in components if c.category == category), None)
                       for category in ("MCCB", "BUSBAR", "SPD", "NEUTRAL_BAR", "EARTH_BAR")}
        incomer, busbar, spd = by_category["MCCB"], by_category["BUSBAR"], by_category["SPD"]
        if not incomer or not busbar:
            raise DesignError("INCOMPLETE_ELECTRICAL_GRAPH", "The DB graph requires an incomer and busbar.")

        nets: List[NetRef] = []

        def add_net(net_id: str, name: str, level: float, wire_class: str,
                    endpoints: List[Tuple[str, str, str, str]]) -> None:
            connections = []
            for index, (src, src_terminal, dst, dst_terminal) in enumerate(endpoints, 1):
                connections.append(ConnectionRef(
                    id=f"{net_id}-C{index:02d}", from_component=src, from_terminal=src_terminal,
                    to_component=dst, to_terminal=dst_terminal, net_id=net_id, wire_class=wire_class))
            nets.append(NetRef(id=net_id, name=name, voltage_level=level, wire_class=wire_class,
                               connections=connections))

        # Each phase is an independent net with a stable identity.
        for phase in range(1, phases + 1):
            label = f"L{phase}"
            add_net(f"NET-MAIN-{label}", f"Main {label} Feed", voltage, "POWER",
                    [(incomer.id, f"{label}_OUT", busbar.id, f"IN_{label}")])

        if spd:
            for phase in range(1, phases + 1):
                label = f"L{phase}"
                add_net(f"NET-SPD-{label}", f"Surge Protection {label}", voltage, "POWER",
                        [(busbar.id, f"IN_{label}", spd.id, label)])

        feeders = sorted((c for c in components if c.category == "MCB"), key=lambda c: c.id)
        terminals = sorted((c for c in components if c.category == "TERMINAL"), key=lambda c: c.id)
        terminal_by_id = {c.id: c for c in terminals}
        for index, mcb in enumerate(feeders):
            terminal_id = f"X{index + 1:03d}"
            if terminal_id not in terminal_by_id:
                raise DesignError("INCOMPLETE_COMPONENT_SET", f"Feeder {mcb.id} has no paired terminal block.",
                                  {"component_id": mcb.id, "terminal_id": terminal_id})
            phase_count = max(1, min(phases, mcb.poles))
            phase = (index % phases) + 1
            if phase_count == 1:
                endpoints = [(busbar.id, f"IN_L{phase}", mcb.id, "IN"),
                             (mcb.id, "OUT", terminal_id, "LEFT")]
                branch_voltage = voltage / (3 ** 0.5) if phases == 3 else voltage
            else:
                # The current catalog exposes three pole terminals as L1/L2/L3.
                endpoints = [(busbar.id, f"IN_L{p}", mcb.id, f"L{p}_IN")
                             for p in range(1, min(phase_count, phases) + 1)]
                endpoints += [(mcb.id, f"L{p}_OUT", terminal_id, "LEFT")
                              for p in range(1, min(phase_count, phases) + 1)]
                branch_voltage = voltage
            add_net(f"NET-BRANCH-{mcb.id}", f"Branch Circuit {mcb.id} to {terminal_id}",
                    branch_voltage, "POWER", endpoints)

        nbar = by_category["NEUTRAL_BAR"]
        if nbar:
            add_net("NET-NEUTRAL-MAIN", "Main Neutral Trunk", 0.0, "NEUTRAL",
                    [(busbar.id, "IN_N", nbar.id, "MAIN_N")])

        pebar = by_category["EARTH_BAR"]
        if pebar:
            add_net("NET-PE-MAIN", "Main Protective Earth Bus", 0.0, "PE",
                    [("PANEL_ROOT", "EARTH_STUD", pebar.id, "MAIN_PE")])

        return nets

    def validate_netlist(self, nets: List[NetRef], components: List[ComponentRef]) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        ids = {component.id for component in components} | {"PANEL_ROOT"}
        seen_net_ids = set()
        seen_conn_ids = set()
        for net in nets:
            if net.id in seen_net_ids:
                errors.append(f"Duplicate net ID '{net.id}'.")
            seen_net_ids.add(net.id)
            if not net.connections:
                errors.append(f"Net '{net.name}' ({net.id}) has no connections.")
            for conn in net.connections:
                if conn.net_id != net.id:
                    errors.append(f"Connection '{conn.id}' references net '{conn.net_id}', expected '{net.id}'.")
                if conn.id in seen_conn_ids:
                    errors.append(f"Duplicate connection ID '{conn.id}'.")
                seen_conn_ids.add(conn.id)
                for endpoint, terminal in ((conn.from_component, conn.from_terminal),
                                          (conn.to_component, conn.to_terminal)):
                    if endpoint not in ids:
                        errors.append(f"Connection '{conn.id}' references unknown component '{endpoint}'.")
                    elif endpoint != "PANEL_ROOT":
                        component = next(c for c in components if c.id == endpoint)
                        if terminal not in {t.get("id") for t in component.terminals}:
                            errors.append(f"Connection '{conn.id}' references unknown terminal '{terminal}' on '{endpoint}'.")
        return len(errors) == 0, errors
