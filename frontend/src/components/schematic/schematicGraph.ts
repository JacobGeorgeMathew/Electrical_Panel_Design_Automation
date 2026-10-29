import type { Edge, Node } from '@xyflow/react';

export type WireClass = 'POWER' | 'CONTROL' | 'SIGNAL' | 'PE' | 'NEUTRAL';
export type TerminalSpec = { id: string; x: number; y: number };
export type SchematicSymbol = {
  id: string; name: string; type: string; category: string; x: number; y: number;
  width: number; height: number; label: string; terminals: TerminalSpec[];
};
export type SchematicWire = {
  id: string; net_id: string; net_name: string; from: string; from_terminal: string;
  to: string; to_terminal: string; wire_class: string; color?: string; svg_path?: string; waypoints?: {x:number;y:number}[]; crossings?: {x:number;y:number;connected:boolean;axis?:'VERTICAL'|'HORIZONTAL'}[]; junctions?: {x:number;y:number;connected:boolean;axis?:'VERTICAL'|'HORIZONTAL'}[];
};
export type SchematicGraphData = {
  width: number; height: number; symbols: SchematicSymbol[]; wires: SchematicWire[]; validation_results?: {id:string;message:string;status:string}[];
};
export type SchematicNodeData = {
  symbolId: string; label: string; name: string; symbolType: string; category: string;
  width: number; height: number; terminals: TerminalSpec[]; properties: Record<string, unknown>;
  junction?: boolean; netId?: string;
};
export type SchematicEdgeData = {
  net_id: string; net_name: string; wire_class: string; color: string; draft?: boolean; svg_path?: string; waypoints?: {x:number;y:number}[]; crossings?: {x:number;y:number;connected:boolean;axis?:'VERTICAL'|'HORIZONTAL'}[]; junctions?: {x:number;y:number;connected:boolean;axis?:'VERTICAL'|'HORIZONTAL'}[];
};
export type SchematicNode = Node<SchematicNodeData, 'symbol' | 'junction'>;
export type SchematicEdge = Edge<SchematicEdgeData, 'wire'>;
export type SchematicRuleViolation = { severity: 'ERROR' | 'WARNING'; code: string; objectId: string; message: string };

const sourceHandle = (terminalId: string) => `source:${terminalId}`;
const targetHandle = (terminalId: string) => `target:${terminalId}`;

export function buildSchematicGraph(data: SchematicGraphData): { nodes: SchematicNode[]; edges: SchematicEdge[] } {
  const symbolById = new Map(data.symbols.map((symbol) => [symbol.id, symbol]));
  const nodes: SchematicNode[] = data.symbols.map((symbol) => ({
    id: symbol.id,
    type: 'symbol', draggable: false, style: {width:symbol.width,height:symbol.height},
    position: { x: symbol.x, y: symbol.y },
    data: {
      symbolId: symbol.id, label: symbol.label, name: symbol.name, symbolType: symbol.type,
      category: symbol.category, width: symbol.width, height: symbol.height,
      terminals: (symbol.terminals || []).map((terminal) => ({ ...terminal, x: terminal.x - symbol.x, y: terminal.y - symbol.y })), properties: { id: symbol.id, name: symbol.name,
        type: symbol.type, category: symbol.category, label: symbol.label },
    },
  }));

  // Draw exactly the CEM connections. A multi-terminal net is not a licence
  // to replace its topology with an invented centroid junction.
  const edges: SchematicEdge[] = data.wires.map(wire => ({
    id: wire.id, source: wire.from, sourceHandle: sourceHandle(wire.from_terminal),
    target: wire.to, targetHandle: targetHandle(wire.to_terminal), type: 'wire',
    data: {net_id: wire.net_id, net_name: wire.net_name, wire_class: wire.wire_class,
      color: wire.color || '#94A3B8', svg_path: wire.svg_path, waypoints: wire.waypoints,
      crossings: wire.crossings, junctions: wire.junctions},
  }));
  return { nodes, edges };
}

export function validateSchematicGraph(nodes: SchematicNode[], edges: SchematicEdge[]): SchematicRuleViolation[] {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const violations: SchematicRuleViolation[] = [];
  const seen = new Set<string>();
  const classes = new Set<WireClass>(['POWER', 'CONTROL', 'SIGNAL', 'PE', 'NEUTRAL']);

  for (const edge of edges) {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    const data = edge.data;
    if (!source || !target) {
      violations.push({ severity: 'ERROR', code: 'MISSING_NODE', objectId: edge.id, message: `Wire ${edge.id} references a missing component or junction.` });
      continue;
    }
    const sourceHandleValid = source.data.junction ? edge.sourceHandle === 'source:net' :
      source.data.terminals.some((terminal) => edge.sourceHandle === sourceHandle(terminal.id));
    const targetHandleValid = target.data.junction ? edge.targetHandle === 'target:net' :
      target.data.terminals.some((terminal) => edge.targetHandle === targetHandle(terminal.id));
    if (!sourceHandleValid || !targetHandleValid) violations.push({ severity: 'ERROR', code: 'MISSING_TERMINAL', objectId: edge.id, message: `Wire ${edge.id} must connect to valid terminals on both ends.` });
    if (source.id === target.id) violations.push({ severity: 'ERROR', code: 'SELF_CONNECTION', objectId: edge.id, message: `Wire ${edge.id} cannot connect a component to itself.` });
    if (!data?.net_id || !data.net_name?.trim()) violations.push({ severity: 'ERROR', code: 'MISSING_NET', objectId: edge.id, message: `Wire ${edge.id} needs a net ID and label.` });
    if (!classes.has(data?.wire_class as WireClass)) violations.push({ severity: 'ERROR', code: 'INVALID_WIRE_CLASS', objectId: edge.id, message: `Wire ${edge.id} has an unsupported electrical class.` });
    const key = [edge.source, edge.sourceHandle, edge.target, edge.targetHandle, data?.net_id].join('|');
    if (seen.has(key)) violations.push({ severity: 'WARNING', code: 'DUPLICATE_CONNECTION', objectId: edge.id, message: `Wire ${edge.id} duplicates an existing terminal connection.` });
    seen.add(key);
  }

  const junctionEdges = new Map<string, SchematicEdge[]>();
  for (const edge of edges) {
    const junctionId = byId.get(edge.source)?.data.junction ? edge.source : byId.get(edge.target)?.data.junction ? edge.target : null;
    if (junctionId) junctionEdges.set(junctionId, [...(junctionEdges.get(junctionId) || []), edge]);
  }
  for (const [junctionId, connected] of junctionEdges) {
    if (connected.length < 2) violations.push({ severity: 'WARNING', code: 'ORPHAN_JUNCTION', objectId: junctionId, message: `Junction ${junctionId} has fewer than two connected wires.` });
    if (new Set(connected.map((edge) => edge.data?.net_id)).size > 1) violations.push({ severity: 'ERROR', code: 'MIXED_NET_JUNCTION', objectId: junctionId, message: `All wires at junction ${junctionId} must belong to the same net.` });
    if (new Set(connected.map((edge) => edge.data?.wire_class)).size > 1) violations.push({ severity: 'ERROR', code: 'MIXED_WIRE_CLASS', objectId: junctionId, message: `All wires at junction ${junctionId} must use the same electrical class.` });
  }
  return violations;
}
