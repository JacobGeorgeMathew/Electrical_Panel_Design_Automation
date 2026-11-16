"""Read-only DB connectivity checks and legacy equipotential projection.

This is topology evidence, not conductor sizing, terminal capacity, PE bonding
approval or a publishable net migration. Callers supply explicit domain and
permanent-equivalence evidence; labels, wire classes, voltages and functional
graph edges never establish it. Historical CEM objects are never normalized.
"""
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Literal
import math

from pydantic import BaseModel, ConfigDict, Field

from app.models.cem import CanonicalEngineeringModel
from app.services.design_errors import DesignError


TerminalKey = tuple[str, str]
Role = Literal['L1', 'L2', 'L3', 'N', 'PE']


class ConnectivityRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')


class ElectricalDomain(ConnectivityRecord):
    supply_id: str = Field(min_length=1, pattern=r'\S')
    role: Role


class TerminalEquivalence(ConnectivityRecord):
    """Caller-supplied permanent group, backed by pinned configuration evidence.

    An evidence ID records provenance; this service cannot authenticate a human
    review. Missing evidence leaves the proposed group separate and unresolved.
    Device transfer paths must never be submitted as permanent groups.
    """
    id: str = Field(min_length=1, pattern=r'\S')
    members: tuple[TerminalKey, ...] = Field(min_length=2)
    evidence_id: str | None = Field(default=None, min_length=1, pattern=r'\S')


class ConnectivityIssue(ConnectivityRecord):
    status: Literal['FAIL', 'UNRESOLVED']
    code: str
    subject: tuple[str, ...]
    message: str


class EquipotentialGroup(ConnectivityRecord):
    # None for an isolated terminal with no predecessor net. These are projection
    # labels only; no persistent identity is allocated or rewritten here.
    net_id: str | None
    legacy_net_ids: tuple[str, ...]
    terminals: tuple[TerminalKey, ...]
    conductor_ids: tuple[str, ...]
    domains: tuple[ElectricalDomain, ...]


class LegacyNetProjection(ConnectivityRecord):
    net_id: str
    # Preserve observations, including conflicting implicit voltage references.
    # A numeric legacy voltage never authorizes an electrical union.
    voltage_level: float = Field(allow_inf_nan=False)
    wire_class: str
    equipotential_ids: tuple[str, ...]


class ConnectivityProjection(ConnectivityRecord):
    schema_version: Literal['db-connectivity/1'] = 'db-connectivity/1'
    groups: tuple[EquipotentialGroup, ...]
    legacy_nets: tuple[LegacyNetProjection, ...]
    issues: tuple[ConnectivityIssue, ...]

    @property
    def status(self) -> str:
        if any(issue.status == 'FAIL' for issue in self.issues):
            return 'FAIL'
        return 'UNRESOLVED' if self.issues else 'PASS'

    def require_consistent(self, *, require_resolved: bool = True) -> None:
        """Refuse invalid/unknown topology before an electrical edit is applied.

        Historical preview callers may inspect unresolved partitions. Passing
        this check does not establish the other required engineering checks.
        """
        blocking = [i for i in self.issues if require_resolved or i.status == 'FAIL']
        if blocking:
            raise DesignError('ELECTRICAL_INCONSISTENCY',
                'DB connectivity is invalid or lacks required topology evidence.',
                {'issues': [i.model_dump(mode='json') for i in blocking]},
                errors=[f'{i.code}: {i.message}' for i in blocking])


def project_legacy_connectivity(
    cem: CanonicalEngineeringModel, *,
    domains: Mapping[TerminalKey, ElectricalDomain] | None = None,
    equivalences: Sequence[TerminalEquivalence] = (),
) -> ConnectivityProjection:
    """Validate identities/references, then derive undirected terminal closure.

    Supply/role assignments are explicit external topology evidence, never
    inferred from DB feeder order or terminal names. Legacy inputs without them
    remain representable but UNRESOLVED. All declared terminals, including unused
    ports, are represented. Missing domain evidence blocks participating ports;
    isolated unused ports impose no invented required-path obligation.

    Nested and flattened conductor projections must agree by identity/content.
    Functional graph references are checked but never used as conductor edges.
    Any known failure suppresses groups, so callers cannot use a partial failed
    partition. Unknown domains permit provisional closure for historical preview.
    """
    domains = domains or {}
    issues: set[tuple[str, str, tuple[str, ...], str]] = set()

    def issue(code, subject, message, status='FAIL'):
        issues.add((status, code, tuple(subject), message))

    def finish(groups=(), legacy=()):
        return ConnectivityProjection(groups=groups, legacy_nets=legacy, issues=tuple(
            ConnectivityIssue(status=status, code=code, subject=subject, message=message)
            for status, code, subject, message in sorted(issues)))

    def duplicates(ids, code):
        for key, count in sorted(Counter(ids).items()):
            if not key.strip():
                issue('INVALID_IDENTITY', (code, key), 'Logical identity requires a nonempty string.')
            if count > 1:
                issue(code, (key,), f"Identity '{key}' occurs more than once.")

    if cem.panel_type != 'DB':
        issue('UNSUPPORTED_PANEL_TYPE', (cem.panel_type,), 'Connectivity profile supports DB only.')
    duplicates([c.id for c in cem.components], 'DUPLICATE_COMPONENT_ID')
    duplicates([n.id for n in cem.nets], 'DUPLICATE_NET_ID')
    duplicates([e.id for e in equivalences], 'DUPLICATE_EQUIVALENCE_ID')
    components = {c.id: c for c in cem.components}
    terminals: set[TerminalKey] = set()
    for component in cem.components:
        if component.id == 'PANEL_ROOT':
            issue('RESERVED_COMPONENT_ID', (component.id,), 'PANEL_ROOT is a virtual legacy interface.')
        ids = []
        for terminal in component.terminals:
            key = terminal.get('id')
            if not isinstance(key, str) or not key.strip():
                issue('INVALID_TERMINAL_ID', (component.id,), 'A terminal requires a nonempty string ID.')
            else:
                ids.append(key)
                terminals.add((component.id, key))
        for key, count in sorted(Counter(ids).items()):
            if count > 1:
                issue('DUPLICATE_TERMINAL_ID', (component.id, key), 'Terminal identity occurs more than once on its component.')

    # Only this exact historical virtual endpoint is representable; it is not
    # proof of a real earth stud, bonding or termination capacity.
    virtual_earth = ('PANEL_ROOT', 'EARTH_STUD')

    def reference(key, subject):
        if key == virtual_earth:
            terminals.add(key)
            issue('VIRTUAL_PE_ANCHOR', key, 'Legacy earth endpoint has no real anchor evidence.', 'UNRESOLVED')
        elif key[0] not in components:
            issue('UNKNOWN_COMPONENT', (*subject, *key), 'Endpoint component does not exist.')
        elif key not in terminals:
            issue('UNKNOWN_TERMINAL', (*subject, *key), 'Endpoint terminal does not exist on its component.')

    nested = [c for net in cem.nets for c in net.connections]
    duplicates([c.id for c in nested], 'DUPLICATE_CONNECTION_ID')
    duplicates([c.id for c in cem.connections], 'DUPLICATE_FLAT_CONNECTION_ID')
    if ({c.id: c.model_dump() for c in nested}
            != {c.id: c.model_dump() for c in cem.connections}):
        issue('CONNECTION_PROJECTION_MISMATCH', (), 'Nested and flattened conductors differ.')

    participating = set()
    edges = []
    for net in cem.nets:
        if not math.isfinite(net.voltage_level):
            issue('NONFINITE_LEGACY_VOLTAGE', (net.id,), 'Legacy voltage must be finite in V.')
        if not net.connections:
            issue('EMPTY_NET', (net.id,), 'A legacy net has no conductor connections.')
        for connection in net.connections:
            if connection.net_id != net.id:
                issue('CONNECTION_NET_MISMATCH', (connection.id,), 'Conductor references a different containing net.')
            a = (connection.from_component, connection.from_terminal)
            b = (connection.to_component, connection.to_terminal)
            reference(a, (connection.id,))
            reference(b, (connection.id,))
            participating.update((a, b))
            if a == b:
                issue('SELF_CONNECTION', (connection.id,), 'A conductor must have two distinct terminal endpoints.')
            edges.append((a, b))

    for equivalence in equivalences:
        members = sorted(set(equivalence.members))
        if len(members) != len(equivalence.members):
            issue('DUPLICATE_EQUIVALENCE_MEMBER', (equivalence.id,), 'Permanent group repeats a terminal.')
        for key in members:
            reference(key, (equivalence.id,))
        participating.update(members)
        owners = {key[0] for key in members}
        if len(owners) != 1 or any(key not in components or components[key].category not in
                {'BUSBAR', 'NEUTRAL_BAR', 'EARTH_BAR', 'TERMINAL'} for key in owners):
            issue('UNSUPPORTED_PERMANENT_GROUP', (equivalence.id,),
                  'Permanent groups require one declared bar or terminal assembly; device paths and bridges are excluded.')
        known = [domains[key] for key in members if isinstance(domains.get(key), ElectricalDomain)]
        if len({d.supply_id for d in known}) > 1:
            issue('SUPPLY_DOMAIN_CONFLICT', (equivalence.id,), 'Permanent group has different supply identities.')
        if len({d.role for d in known}) > 1:
            code = 'PE_BOUNDARY_CONFLICT' if any(d.role == 'PE' for d in known) else 'PHASE_DOMAIN_CONFLICT'
            issue(code, (equivalence.id,), 'Permanent group has incompatible phase/N/PE roles.')
        if not equivalence.evidence_id:
            issue('MISSING_EQUIVALENCE_EVIDENCE', (equivalence.id,),
                  'Distinct terminals remain separate without permanent-group evidence.', 'UNRESOLVED')
        else:
            edges.extend((members[0], member) for member in members[1:])

    for key, domain in sorted(domains.items()):
        reference(key, ('domain',))
        if not isinstance(domain, ElectricalDomain):
            issue('INVALID_DOMAIN', key, 'Domain must be an explicit ElectricalDomain record.')
    for key in sorted(participating):
        if key not in domains:
            issue('MISSING_TERMINAL_DOMAIN', key, 'Explicit supply identity and phase/N/PE role are required.', 'UNRESOLVED')
        elif key == virtual_earth and isinstance(domains[key], ElectricalDomain) and domains[key].role != 'PE':
            issue('PE_BOUNDARY_CONFLICT', key, 'The legacy earth endpoint can only participate in PE.')

    graph = cem.electrical_graph
    if graph is not None:
        if graph.project_id != cem.project_id:
            issue('GRAPH_PROJECT_MISMATCH', (graph.project_id,), 'Functional graph belongs to another project.')
        duplicates([n.id for n in graph.nodes], 'DUPLICATE_GRAPH_NODE_ID')
        node_ids = {n.id for n in graph.nodes}
        for key in sorted(node_ids - set(components) - {'PANEL_ROOT'}):
            issue('UNKNOWN_GRAPH_COMPONENT', (key,), 'Functional graph node has no component.')
        for edge in graph.edges:
            for key in (edge.source, edge.target):
                if key not in node_ids:
                    issue('UNKNOWN_GRAPH_ENDPOINT', (edge.source, edge.target, key), 'Functional graph endpoint has no node.')

    if any(i[0] == 'FAIL' for i in issues):
        return finish()

    parent = {key: key for key in terminals}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    # Only actual conductors and evidenced permanent groups enter closure. A
    # legacy net ID containing disconnected edges does not join those edges.
    for a, b in sorted(edges):
        ra, rb = sorted((find(a), find(b)))
        parent[rb] = ra
    members = defaultdict(list)
    for key in sorted(terminals):
        members[find(key)].append(key)
    roles = {}
    for root, keys in sorted(members.items()):
        known = sorted({(domains[k].supply_id, domains[k].role) for k in keys if k in domains})
        roles[root] = tuple(ElectricalDomain(supply_id=s, role=r) for s, r in known)
        if len({s for s, r in known}) > 1:
            issue('SUPPLY_DOMAIN_CONFLICT', root, 'Connected terminals have different supply identities.')
        distinct = {r for s, r in known}
        if len(distinct) > 1:
            code = 'PE_BOUNDARY_CONFLICT' if 'PE' in distinct else 'PHASE_DOMAIN_CONFLICT'
            issue(code, root, 'Connected terminals have incompatible phase/N/PE roles.')
    if any(i[0] == 'FAIL' for i in issues):
        return finish()

    conductor_ids = defaultdict(list)
    predecessors = defaultdict(set)
    net_roots = defaultdict(set)
    for net in cem.nets:
        for connection in net.connections:
            root = find((connection.from_component, connection.from_terminal))
            conductor_ids[root].append(connection.id)
            predecessors[root].add(net.id)
            net_roots[net.id].add(root)
    # A predecessor spanning disconnected classes cannot be assigned multiple
    # active IDs. Preview labels use the smallest surviving terminal's class;
    # other classes need explicit allocation in a later conversion operation.
    assigned = defaultdict(list)
    for net_id, roots in sorted(net_roots.items()):
        assigned[min(roots)].append(net_id)
        if len(roots) > 1:
            issue('LEGACY_NET_SPLIT', (net_id,),
                  'Legacy net spans disconnected terminal classes; explicit identity allocation is required.', 'UNRESOLVED')
    labels = {root: min(ids) for root, ids in assigned.items()}
    groups = tuple(EquipotentialGroup(net_id=labels.get(root),
        legacy_net_ids=tuple(sorted(predecessors[root])), terminals=tuple(keys),
        conductor_ids=tuple(sorted(conductor_ids[root])), domains=roles[root])
        for root, keys in sorted(members.items()))
    legacy = tuple(LegacyNetProjection(net_id=net.id, voltage_level=net.voltage_level,
        wire_class=net.wire_class, equipotential_ids=tuple(sorted(labels[r]
            for r in net_roots[net.id] if r in labels))) for net in sorted(cem.nets, key=lambda n: n.id))
    return finish(groups, legacy)
