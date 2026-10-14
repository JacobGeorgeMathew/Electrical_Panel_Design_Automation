import networkx as nx
from typing import List
from app.models.cem import ComponentRef
from app.models.electrical_graph import ElectricalEdge, ElectricalGraphModel, ElectricalNode


class GraphEngine:
    """Builds and analyzes typed electrical graphs using NetworkX."""

    def build_electrical_graph(self, project_id: str, components: List[ComponentRef]) -> ElectricalGraphModel:
        G = nx.DiGraph()
        nodes = []
        edges = []

        comp_dict = {c.id: c for c in components}

        # 1. Add main Panel root node
        nodes.append(ElectricalNode(id="PANEL_ROOT", name="Distribution Panel DB", type="PANEL", category="PANEL"))
        G.add_node("PANEL_ROOT", type="PANEL")

        # 2. Add Incomer
        incomer = comp_dict.get("QF001")
        if incomer:
            nodes.append(ElectricalNode(id=incomer.id, name=incomer.name, type=incomer.category, category=incomer.category))
            edges.append(ElectricalEdge(source="PANEL_ROOT", target=incomer.id, relation="FEEDS", wire_class="POWER"))
            G.add_edge("PANEL_ROOT", incomer.id, relation="FEEDS")

        # 3. Add Busbar
        busbar = comp_dict.get("BUS001")
        if incomer and busbar:
            nodes.append(ElectricalNode(id=busbar.id, name=busbar.name, type=busbar.category, category=busbar.category))
            edges.append(ElectricalEdge(source=incomer.id, target=busbar.id, relation="FEEDS", wire_class="POWER"))
            G.add_edge(incomer.id, busbar.id, relation="FEEDS")

        # 4. Add SPD
        spd = comp_dict.get("SPD001")
        if busbar and spd:
            nodes.append(ElectricalNode(id=spd.id, name=spd.name, type=spd.category, category=spd.category))
            edges.append(ElectricalEdge(source=busbar.id, target=spd.id, relation="PROTECTED_BY", wire_class="POWER"))
            G.add_edge(busbar.id, spd.id, relation="PROTECTED_BY")

        # 5. Add Feeders (MCBs) & Terminals
        feeders = [c for c in components if c.category == "MCB"]
        terminals = {c.id: c for c in components if c.category == "TERMINAL"}

        for idx, mcb in enumerate(feeders):
            nodes.append(ElectricalNode(id=mcb.id, name=mcb.name, type=mcb.category, category=mcb.category))
            if busbar:
                edges.append(ElectricalEdge(source=busbar.id, target=mcb.id, relation="FEEDS", wire_class="POWER"))
                G.add_edge(busbar.id, mcb.id, relation="FEEDS")

            # Connect MCB to terminal strip X001, X002...
            term_id = f"X{idx+1:03d}"
            if term_id in terminals:
                term = terminals[term_id]
                nodes.append(ElectricalNode(id=term.id, name=term.name, type=term.category, category=term.category))
                edges.append(ElectricalEdge(source=mcb.id, target=term.id, relation="FEEDS", wire_class="POWER"))
                G.add_edge(mcb.id, term.id, relation="FEEDS")

        # 6. Add Neutral & Earth Bars
        nbar = comp_dict.get("NBAR01")
        if nbar:
            nodes.append(ElectricalNode(id=nbar.id, name=nbar.name, type=nbar.category, category=nbar.category))
            if busbar:
                edges.append(ElectricalEdge(source=busbar.id, target=nbar.id, relation="CONNECTED_TO", wire_class="NEUTRAL"))

        pebar = comp_dict.get("PEBAR01")
        if pebar:
            nodes.append(ElectricalNode(id=pebar.id, name=pebar.name, type=pebar.category, category=pebar.category))
            edges.append(ElectricalEdge(source="PANEL_ROOT", target=pebar.id, relation="CONNECTED_TO", wire_class="PE"))

        return ElectricalGraphModel(project_id=project_id, nodes=nodes, edges=edges)
