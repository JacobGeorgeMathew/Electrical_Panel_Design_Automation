import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  addEdge, Background, BaseEdge, Controls, EdgeLabelRenderer, getBezierPath,
  Handle, MiniMap, Position, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState,
  type Connection, type EdgeProps, type NodeProps, type NodeTypes, type EdgeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { GitBranch, Plus, TriangleAlert, X } from 'lucide-react';
import { useProjectStore } from '../../stores/projectStore';
import { buildSchematicGraph, validateSchematicGraph, type SchematicEdge, type SchematicGraphData,
  type SchematicNode, type SchematicEdgeData, type WireClass } from './schematicGraph';

const SymbolNode: React.FC<NodeProps<SchematicNode>> = ({ data, selected }) => {
  const top = data.terminals.filter((terminal) => terminal.y <= data.height / 2);
  const bottom = data.terminals.filter((terminal) => terminal.y > data.height / 2);
  const handles = (terminals: typeof data.terminals, position: Position, kind: 'source' | 'target') =>
    terminals.map((terminal) => {
      const xPct = data.width ? (terminal.x / data.width) * 100 : 50;
      const yPct = data.height ? (terminal.y / data.height) * 100 : 50;
      const vertical = position === Position.Top || position === Position.Bottom;
      return <Handle key={`${kind}:${terminal.id}`} id={`${kind}:${terminal.id}`} type={kind} position={position}
        title={`${terminal.id} ${kind}`} style={vertical ? { left: `${xPct}%` } : { top: `${yPct}%` }} />;
    });
  const lines = data.label.split('\n');
  return <div className={`relative flex h-full w-full flex-col items-center justify-center rounded-md border bg-slate-900 px-2 text-center shadow-lg ${selected ? 'border-blue-400 ring-2 ring-blue-500/40' : 'border-slate-600'}`}
    style={{ minWidth: Math.max(72, Math.min(data.width, 190)), minHeight: Math.max(46, Math.min(data.height, 110)) }}>
    {handles(top, Position.Top, 'target')}{handles(top, Position.Top, 'source')}
    {handles(bottom, Position.Bottom, 'target')}{handles(bottom, Position.Bottom, 'source')}
    <span className="text-[11px] font-bold text-slate-100">{lines[0]}</span>
    {lines[1] && <span className="text-[9px] text-slate-400">{lines[1]}</span>}
    <span className="mt-1 text-[8px] uppercase tracking-wide text-slate-500">{data.symbolType}</span>
  </div>;
};

const JunctionNode: React.FC<NodeProps<SchematicNode>> = ({ data, selected }) => <div className="relative flex h-4 w-4 items-center justify-center rounded-full border border-amber-300 bg-amber-400 shadow-[0_0_10px_#fbbf24]"
  title={`Junction · ${data.netId || data.label}`}>
  <Handle id="target:net" type="target" position={Position.Top} />
  <Handle id="source:net" type="source" position={Position.Bottom} />
  {selected && <span className="absolute left-5 whitespace-nowrap text-[10px] text-amber-200">{data.label}</span>}
</div>;

const WireEdge: React.FC<EdgeProps<SchematicEdge>> = ({ id, sourceX, sourceY, targetX, targetY, sourcePosition,
  targetPosition, data, selected }) => {
  const [path, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  return <>
    <BaseEdge id={id} path={path} style={{ stroke: selected ? '#F8FAFC' : data?.color || '#64748B', strokeWidth: selected ? 3 : 2 }} />
    <EdgeLabelRenderer><div className="nodrag nopan absolute rounded bg-slate-950/90 px-1.5 py-0.5 font-mono text-[9px] text-slate-200"
      style={{ transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`, pointerEvents: 'all' }}>
      {data?.net_name || 'Unlabelled'} <span className="text-slate-500">{data?.wire_class || ''}</span>
    </div></EdgeLabelRenderer>
  </>;
};

const nodeTypes: NodeTypes = { symbol: SymbolNode as React.ComponentType<NodeProps>, junction: JunctionNode as React.ComponentType<NodeProps> };
const edgeTypes = { wire: WireEdge } as unknown as EdgeTypes;
const wireClasses: WireClass[] = ['POWER', 'CONTROL', 'SIGNAL', 'NEUTRAL', 'PE'];
const colors: Record<WireClass, string> = { POWER: '#EF4444', CONTROL: '#A78BFA', SIGNAL: '#F59E0B', NEUTRAL: '#3B82F6', PE: '#22C55E' };

const SchematicCanvas: React.FC<{ data: SchematicGraphData }> = ({ data }) => {
  const { selectObject } = useProjectStore();
  const initial = useMemo(() => buildSchematicGraph(data), [data]);
  const [nodes, setNodes, onNodesChange] = useNodesState<SchematicNode>(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<SchematicEdge>(initial.edges);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [wireFilter, setWireFilter] = useState<'ALL' | WireClass>('ALL');
  const draftSequence = useRef(0);

  useEffect(() => {
    const graph = buildSchematicGraph(data);
    setNodes(graph.nodes);
    setEdges(graph.edges);
    setSelectedEdgeId(null);
  }, [data, setNodes, setEdges]);

  const violations = useMemo(() => validateSchematicGraph(nodes, edges), [nodes, edges]);
  const selectedNode = nodes.find((node) => node.selected) || null;
  const selectedEdge = edges.find((edge) => edge.id === selectedEdgeId) || null;
  const visibleEdges = edges.filter((edge) => wireFilter === 'ALL' || edge.data?.wire_class === wireFilter);

  const onConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target || !connection.sourceHandle || !connection.targetHandle) return;
    draftSequence.current += 1;
    const suffix = String(draftSequence.current).padStart(3, '0');
    const wireClass: WireClass = wireFilter === 'ALL' ? 'POWER' : wireFilter;
    setEdges((current) => addEdge({ ...connection, id: `DRAFT-CONN-${suffix}`, type: 'wire',
      data: { net_id: `NET-DRAFT-${suffix}`, net_name: `Draft net ${suffix}`, wire_class: wireClass,
        color: colors[wireClass], draft: true } }, current) as SchematicEdge[]);
  }, [setEdges, wireFilter]);

  const addJunction = () => {
    draftSequence.current += 1;
    const suffix = String(draftSequence.current).padStart(3, '0');
    const id = `DRAFT-JUNCTION-${suffix}`;
    setNodes((current) => [...current, { id, type: 'junction', position: { x: data.width / 2, y: data.height / 2 },
      data: { symbolId: id, label: `Draft junction ${suffix}`, name: 'Draft junction', symbolType: 'JUNCTION',
        category: 'JUNCTION', width: 12, height: 12, terminals: [], properties: { draft: true }, junction: true, netId: `NET-DRAFT-${suffix}` } }]);
  };

  const updateSelectedEdge = (patch: Partial<SchematicEdgeData>) => {
    if (!selectedEdgeId) return;
    setEdges((current) => current.map((edge) => edge.id === selectedEdgeId ? {
      ...edge, data: { ...(edge.data || { net_id: '', net_name: '', wire_class: 'POWER', color: colors.POWER }), ...patch,
        color: patch.wire_class ? colors[patch.wire_class as WireClass] : (edge.data?.color || colors.POWER) },
    } : edge));
  };

  return <div className="flex min-h-0 flex-1 flex-col gap-3">
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-900 p-3">
      <div className="flex items-center gap-3"><div className="rounded-xl bg-blue-500/10 p-2 text-blue-400"><GitBranch className="h-5 w-5" /></div>
        <div><h3 className="text-sm font-bold text-slate-200">Interactive Electrical Schematic</h3>
          <p className="text-xs text-slate-400">React Flow · CEM IDs · terminal-level nets · schematic edits are drafts</p></div></div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <select aria-label="Filter wire class" value={wireFilter} onChange={(event) => setWireFilter(event.target.value as 'ALL' | WireClass)}
          className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-slate-200">
          <option value="ALL">All wires</option>{wireClasses.map((wireClass) => <option key={wireClass} value={wireClass}>{wireClass}</option>)}
        </select>
        <button type="button" onClick={addJunction} className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-slate-200 hover:bg-slate-800"><Plus className="h-3.5 w-3.5" /> Junction</button>
      </div>
    </div>

    <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(0,1fr)_260px]">
      <div className="relative min-h-[420px] overflow-hidden rounded-2xl border border-slate-800 bg-slate-950">
        <div className="absolute left-3 top-3 z-10 rounded-lg border border-amber-500/30 bg-slate-950/90 px-2.5 py-1.5 text-[10px] text-amber-200">Draft graph · CEM connections and exports are unchanged</div>
        <ReactFlow nodes={nodes} edges={visibleEdges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
          onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
          onNodeClick={(_, node) => { selectObject(node.id); setSelectedEdgeId(null); }}
          onEdgeClick={(_, edge) => setSelectedEdgeId(edge.id)}
          onPaneClick={() => { setSelectedEdgeId(null); selectObject(null); }}
          onSelectionChange={({ nodes: chosenNodes, edges: chosenEdges }) => {
            if (chosenNodes[0]) selectObject(chosenNodes[0].id);
            setSelectedEdgeId(chosenEdges[0]?.id || null);
          }}
          fitView fitViewOptions={{ padding: 0.15 }} minZoom={0.2} maxZoom={2.5} nodesConnectable nodesDraggable
          selectionOnDrag panOnDrag deleteKeyCode={['Backspace', 'Delete']}>
          <Background color="#334155" gap={24} size={1} /><MiniMap nodeColor={(node) => node.type === 'junction' ? '#FBBF24' : '#334155'} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      <aside className="flex min-h-[220px] flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-900 p-4">
        <div className="flex items-center justify-between"><h4 className="text-sm font-semibold text-slate-100">Electrical properties</h4>
          {selectedEdge && <button aria-label="Delete selected wire" onClick={() => { setEdges((current) => current.filter((edge) => edge.id !== selectedEdgeId)); setSelectedEdgeId(null); }} className="text-slate-400 hover:text-red-300"><X className="h-4 w-4" /></button>}</div>
        {selectedEdge ? <>
          <div className="text-[10px] font-mono text-slate-500">{selectedEdge.id}</div>
          <label className="text-xs text-slate-400">Net ID<input aria-label="Net ID" value={selectedEdge.data?.net_id || ''} onChange={(event) => updateSelectedEdge({ net_id: event.target.value })}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 font-mono text-sm text-slate-100" /></label>
          <label className="text-xs text-slate-400">Wire label<input aria-label="Wire label" value={selectedEdge.data?.net_name || ''} onChange={(event) => updateSelectedEdge({ net_name: event.target.value })}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-sm text-slate-100" /></label>
          <label className="text-xs text-slate-400">Electrical class<select aria-label="Electrical class" value={selectedEdge.data?.wire_class || 'POWER'} onChange={(event) => updateSelectedEdge({ wire_class: event.target.value })}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-sm text-slate-100">{wireClasses.map((item) => <option key={item}>{item}</option>)}</select></label>
          <p className="break-all text-[10px] text-slate-500">{selectedEdge.source} ({selectedEdge.sourceHandle}) → {selectedEdge.target} ({selectedEdge.targetHandle})</p>
        </> : selectedNode ? <>
          <div className="text-[10px] font-mono text-slate-500">Stable object ID · {selectedNode.id}</div>
          <div className="rounded-lg border border-slate-800 bg-slate-950 p-3"><div className="text-sm font-semibold text-slate-100">{selectedNode.data.name}</div>
            <div className="mt-1 text-xs text-slate-400">{selectedNode.data.category} / {selectedNode.data.symbolType}</div></div>
          <div className="text-xs font-semibold text-slate-300">Terminals</div>
          <div className="max-h-40 space-y-1 overflow-auto">{selectedNode.data.terminals.map((terminal) => <div key={terminal.id} className="flex justify-between rounded bg-slate-950 px-2 py-1.5 text-[10px] font-mono text-slate-400"><span>{terminal.id}</span><span>{terminal.x}, {terminal.y}</span></div>)}
            {!selectedNode.data.terminals.length && <div className="text-xs text-slate-500">Junction node</div>}</div>
          <div className="text-[10px] text-slate-500">CEM electrical properties are read-only in this schematic draft.</div>
        </> : <p className="text-xs leading-5 text-slate-400">Select a component or wire to inspect stable IDs, terminals, net labels, and electrical class.</p>}

        <div className="mt-auto border-t border-slate-800 pt-3"><div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-300"><TriangleAlert className="h-3.5 w-3.5 text-amber-400" />Draft rule checks <span className="ml-auto font-mono text-slate-500">{violations.length}</span></div>
          <div className="max-h-36 space-y-1 overflow-auto">{violations.length ? violations.slice(0, 8).map((violation, index) => <div key={`${violation.objectId}-${violation.code}-${index}`} className={`rounded px-2 py-1.5 text-[10px] ${violation.severity === 'ERROR' ? 'bg-red-950/60 text-red-200' : 'bg-amber-950/50 text-amber-200'}`}>{violation.message}</div>) : <div className="text-[10px] text-emerald-300">No draft graph rule issues found.</div>}</div>
        </div>
      </aside>
    </div>
  </div>;
};

export const SchematicViewer: React.FC = () => {
  const schematicData = useProjectStore((state) => state.schematicData) as SchematicGraphData | null;
  if (!schematicData) return <div className="p-12 text-center text-slate-500 font-mono text-sm">No schematic data loaded. Click "Generate Design" to build the schematic diagram.</div>;
  return <div className="flex h-full min-h-0 flex-col bg-slate-950 p-4 md:p-6"><ReactFlowProvider><SchematicCanvas data={schematicData} /></ReactFlowProvider></div>;
};
