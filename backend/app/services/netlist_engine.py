from typing import List, Tuple
from app.models.cem import ConnectionRef, NetRef
from app.models.electrical_graph import ElectricalGraphModel


class NetlistEngine:
    """Generates explicit netlists and performs connectivity validation."""

    def generate_netlist(self, graph: ElectricalGraphModel) -> List[NetRef]:
        nets = []
        net_counter = 1

        # 1. Main Feed Net (Incomer -> Busbar)
        incomer_node = next((n for n in graph.nodes if n.category == "MCCB"), None)
        busbar_node = next((n for n in graph.nodes if n.category == "BUSBAR"), None)

        if incomer_node and busbar_node:
            net_id = f"NET-{net_counter:03d}"
            net_counter += 1
            nets.append(NetRef(
                id=net_id,
                name="Main Bus Feeder Net",
                voltage_level=415.0,
                wire_class="POWER",
                connections=[
                    ConnectionRef(
                        id=f"CONN-{net_counter}-1",
                        from_component=incomer_node.id,
                        from_terminal="L1_OUT",
                        to_component=busbar_node.id,
                        to_terminal="IN_L1",
                        net_id=net_id,
                        wire_class="POWER"
                    ),
                    ConnectionRef(
                        id=f"CONN-{net_counter}-2",
                        from_component=incomer_node.id,
                        from_terminal="L2_OUT",
                        to_component=busbar_node.id,
                        to_terminal="IN_L2",
                        net_id=net_id,
                        wire_class="POWER"
                    ),
                    ConnectionRef(
                        id=f"CONN-{net_counter}-3",
                        from_component=incomer_node.id,
                        from_terminal="L3_OUT",
                        to_component=busbar_node.id,
                        to_terminal="IN_L3",
                        net_id=net_id,
                        wire_class="POWER"
                    )
                ]
            ))

        # 2. SPD Net
        spd_node = next((n for n in graph.nodes if n.category == "SPD"), None)
        if busbar_node and spd_node:
            net_id = f"NET-{net_counter:03d}"
            net_counter += 1
            nets.append(NetRef(
                id=net_id,
                name="Surge Protection Net",
                voltage_level=415.0,
                wire_class="POWER",
                connections=[
                    ConnectionRef(
                        id=f"CONN-SPD-1",
                        from_component=busbar_node.id,
                        from_terminal="IN_L1",
                        to_component=spd_node.id,
                        to_terminal="L1",
                        net_id=net_id,
                        wire_class="POWER"
                    )
                ]
            ))

        # 3. Branch Feeder Nets (Busbar -> MCB -> Terminals)
        mcbs = [n for n in graph.nodes if n.category == "MCB"]
        for idx, mcb in enumerate(mcbs):
            term_id = f"X{idx+1:03d}"
            net_id = f"NET-{net_counter:03d}"
            net_counter += 1

            # Distribute 1P MCBs across L1, L2, L3 phases for phase balancing
            phase_bus_term = f"IN_L{(idx % 3) + 1}"

            conns = [
                ConnectionRef(
                    id=f"CONN-FEED-{idx+1}-A",
                    from_component=busbar_node.id if busbar_node else "BUS001",
                    from_terminal=phase_bus_term,
                    to_component=mcb.id,
                    to_terminal="IN" if "1P" in mcb.name or "16A" in mcb.name or "20A" in mcb.name or "32A" in mcb.name else "L1_IN",
                    net_id=net_id,
                    wire_class="POWER"
                ),
                ConnectionRef(
                    id=f"CONN-FEED-{idx+1}-B",
                    from_component=mcb.id,
                    from_terminal="OUT" if "1P" in mcb.name or "16A" in mcb.name or "20A" in mcb.name or "32A" in mcb.name else "L1_OUT",
                    to_component=term_id,
                    to_terminal="LEFT",
                    net_id=net_id,
                    wire_class="POWER"
                )
            ]

            nets.append(NetRef(
                id=net_id,
                name=f"Branch Circuit Net {mcb.id} -> {term_id}",
                voltage_level=230.0 if "1P" in mcb.name or "16A" in mcb.name or "20A" in mcb.name or "32A" in mcb.name else 415.0,
                wire_class="POWER",
                connections=conns
            ))

        # 4. Neutral & PE Bus Nets
        nbar = next((n for n in graph.nodes if n.category == "NEUTRAL_BAR"), None)
        pebar = next((n for n in graph.nodes if n.category == "EARTH_BAR"), None)

        if nbar:
            net_id = f"NET-{net_counter:03d}"
            net_counter += 1
            nets.append(NetRef(
                id=net_id,
                name="Main Neutral Trunk",
                voltage_level=0.0,
                wire_class="NEUTRAL",
                connections=[
                    ConnectionRef(
                        id="CONN-N-1",
                        from_component=busbar_node.id if busbar_node else "BUS001",
                        from_terminal="IN_N",
                        to_component=nbar.id,
                        to_terminal="MAIN_N",
                        net_id=net_id,
                        wire_class="NEUTRAL"
                    )
                ]
            ))

        if pebar:
            net_id = f"NET-{net_counter:03d}"
            net_counter += 1
            nets.append(NetRef(
                id=net_id,
                name="Main Protective Earth (PE) Bus",
                voltage_level=0.0,
                wire_class="PE",
                connections=[
                    ConnectionRef(
                        id="CONN-PE-1",
                        from_component="PANEL_ROOT",
                        from_terminal="EARTH_STUD",
                        to_component=pebar.id,
                        to_terminal="MAIN_PE",
                        net_id=net_id,
                        wire_class="PE"
                    )
                ]
            ))

        return nets

    def validate_netlist(self, nets: List[NetRef]) -> Tuple[bool, List[str]]:
        errors = []
        if not nets:
            errors.append("Netlist is empty.")
            return False, errors

        for net in nets:
            if not net.connections:
                errors.append(f"Net '{net.name}' ({net.id}) has no connections (floating net).")

        return len(errors) == 0, errors
