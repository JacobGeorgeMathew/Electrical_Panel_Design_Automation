import React, { useMemo, useRef, useState } from 'react';
import { AlignCenterHorizontal, AlignStartHorizontal, Eye, EyeOff, Layers, RotateCw, ShieldAlert } from 'lucide-react';
import { useProjectStore, type EditorTransform } from '../../stores/projectStore';
import { analyzeEditorGeometry, componentTransform } from '../threeD/editorGeometry';

type DragState = { id: string; offsetX: number; offsetY: number; pointerId: number };

export function snapLayoutValue(value: number, enabled: boolean, grid: number) {
  return enabled ? Math.round(value / grid) * grid : value;
}

export function screenToPanelPoint(svg: SVGSVGElement, clientX: number, clientY: number) {
  const point = svg.createSVGPoint();
  point.x = clientX;
  point.y = clientY;
  const matrix = svg.getScreenCTM();
  const local = matrix ? point.matrixTransform(matrix.inverse()) : point;
  return { x: local.x, y: local.y };
}

export const Layout2DViewer: React.FC = () => {
  const {
    pdm, selectedObjectId, selectObject, hoveredObjectId, hoverObject,
    editorTransforms, editorSnapEnabled, editorGridMm, toggleEditorSnap, setEditorGridMm,
    updateEditorTransform, commitEditorTransform, validateCurrentPlacement, isValidatingPlacement,
    resetEditorDraft, errorMessage,
  } = useProjectStore();
  const [showZones, setShowZones] = useState(true);
  const [showRoutes, setShowRoutes] = useState(true);
  const [showClearances, setShowClearances] = useState(true);
  const [drag, setDrag] = useState<DragState | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const warnings = useMemo(() => pdm ? analyzeEditorGeometry(pdm.components, editorTransforms,
    { width: pdm.enclosure_width, height: pdm.enclosure_height, depth: pdm.enclosure_depth }) : [], [pdm, editorTransforms]);
  if (!pdm) return <div className="p-12 text-center text-slate-500 font-mono text-sm">No PDM physical layout loaded. Click "Generate Design" to create the 2D layout.</div>;

  const { enclosure_width: width, enclosure_height: height, zones, components, rails, routes } = pdm;
  const selected = components.find((component) => component.cem_component_id === selectedObjectId || component.id === selectedObjectId) || null;
  const selectedTransform = selected ? componentTransform(selected, editorTransforms[selected.cem_component_id]) : null;
  const warningIds = new Set(warnings.flatMap((warning) => warning.componentIds));

  const updatePosition = (event: React.PointerEvent<SVGGElement>, id: string) => {
    if (!drag || drag.id !== id || !svgRef.current) return;
    const point = screenToPanelPoint(svgRef.current, event.clientX, event.clientY);
    const component = components.find((item) => item.cem_component_id === id);
    if (!component) return;
    const x = snapLayoutValue(point.x - drag.offsetX, editorSnapEnabled, editorGridMm);
    const y = snapLayoutValue(height - point.y - drag.offsetY, editorSnapEnabled, editorGridMm);
    updateEditorTransform(id, { x, y });
  };

  const commitLayoutEdit = () => {
    setDrag(null);
    commitEditorTransform();
    void validateCurrentPlacement();
  };

  const beginDrag = (event: React.PointerEvent<SVGGElement>, id: string) => {
    if (!svgRef.current) return;
    event.preventDefault();
    event.stopPropagation();
    selectObject(id);
    const point = screenToPanelPoint(svgRef.current, event.clientX, event.clientY);
    const component = components.find((item) => item.cem_component_id === id);
    if (!component) return;
    const current = componentTransform(component, editorTransforms[id]);
    setDrag({ id, offsetX: point.x - current.x, offsetY: height - point.y - current.y, pointerId: event.pointerId });
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const updateNumeric = (field: 'x' | 'y' | 'z' | 'rotation_deg', value: number) => {
    if (!selected || !Number.isFinite(value)) return;
    const step = field === 'rotation_deg' ? 15 : editorGridMm;
    updateEditorTransform(selected.cem_component_id, { [field]: snapLayoutValue(value, editorSnapEnabled, step) } as Partial<EditorTransform>);
  };

  const align = (kind: 'left' | 'centerX' | 'bottom') => {
    if (!selected || !selectedTransform) return;
    if (kind === 'left') updateEditorTransform(selected.cem_component_id, { x: 20 });
    if (kind === 'centerX') updateEditorTransform(selected.cem_component_id, { x: (width - selected.width) / 2 });
    if (kind === 'bottom') updateEditorTransform(selected.cem_component_id, { y: 20 });
    commitEditorTransform();
    void validateCurrentPlacement();
  };

  return <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 bg-slate-950 p-4 md:p-6">
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-900 p-4">
      <div className="flex items-center gap-3"><div className="rounded-xl bg-blue-500/10 p-2 text-blue-400"><Layers className="h-5 w-5" /></div>
        <div><h3 className="text-sm font-bold text-slate-200">Editable 2D Physical Panel Layout</h3>
          <p className="text-xs text-slate-400">Selected enclosure ({width} × {height} mm) · PDM coordinates in millimetres</p></div></div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <label className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950 px-3 py-1.5 text-slate-300"><input type="checkbox" checked={showZones} onChange={(event) => setShowZones(event.target.checked)} />Zones</label>
        <label className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950 px-3 py-1.5 text-slate-300"><input type="checkbox" checked={showRoutes} onChange={(event) => setShowRoutes(event.target.checked)} />Routes</label>
        <label className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950 px-3 py-1.5 text-slate-300"><input type="checkbox" checked={showClearances} onChange={(event) => setShowClearances(event.target.checked)} />Clearances</label>
      </div>
    </div>

    <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(0,1fr)_270px]">
      <div className="flex min-h-[420px] min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 bg-slate-900 p-2.5">
          <button aria-pressed={editorSnapEnabled} onClick={toggleEditorSnap} className={`rounded-lg border px-2.5 py-1.5 text-xs ${editorSnapEnabled ? 'border-blue-500 bg-blue-600 text-white' : 'border-slate-700 text-slate-300'}`}>Snap {editorSnapEnabled ? 'On' : 'Off'}</button>
          <label className="flex items-center gap-1.5 text-xs text-slate-400">Grid<input aria-label="Snap grid mm" type="number" min="1" step="1" value={editorGridMm} onChange={(event) => setEditorGridMm(Number(event.target.value))} className="w-14 rounded border border-slate-700 bg-slate-950 px-1.5 py-1 text-slate-100" />mm</label>
          <span className="mx-1 h-5 border-l border-slate-700" />
          <button onClick={() => align('left')} disabled={!selected} className="editor-tool"><AlignStartHorizontal className="h-3.5 w-3.5" />Align left</button>
          <button onClick={() => align('centerX')} disabled={!selected} className="editor-tool"><AlignCenterHorizontal className="h-3.5 w-3.5" />Center X</button>
          <button onClick={() => align('bottom')} disabled={!selected} className="editor-tool">Align bottom</button>
          <button onClick={() => { if (selected && selectedTransform) { updateNumeric('rotation_deg', selectedTransform.rotation_deg + 90); commitEditorTransform(); void validateCurrentPlacement(); } }} disabled={!selected} className="editor-tool"><RotateCw className="h-3.5 w-3.5" />Rotate 90°</button>
          <div className="ml-auto flex gap-2">
            <button onClick={resetEditorDraft} className="editor-tool"><Eye className="h-3.5 w-3.5" />Reset</button>
            <button onClick={() => { commitEditorTransform(); void validateCurrentPlacement(); }} disabled={isValidatingPlacement} className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">{isValidatingPlacement ? 'Validating…' : 'Apply & Validate'}</button>
          </div>
        </div>
        <div className="relative min-h-0 flex-1 overflow-hidden p-3">
          <svg ref={svgRef} width="100%" height="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" className="h-full w-full select-none touch-none">
            <defs><pattern id="layout-grid" width={editorGridMm * 4} height={editorGridMm * 4} patternUnits="userSpaceOnUse"><path d={`M ${editorGridMm * 4} 0 L 0 0 0 ${editorGridMm * 4}`} fill="none" stroke="#334155" strokeWidth="1" opacity="0.28" /></pattern></defs>
            <rect x={0} y={0} width={width} height={height} fill="#0B0F19" stroke="#334155" strokeWidth={4} rx={10} />
            <rect x={0} y={0} width={width} height={height} fill="url(#layout-grid)" />
            <rect x={pdm.mounting_plate_x} y={height - pdm.mounting_plate_y - (pdm.mounting_plate_height ?? height - 60)} width={pdm.mounting_plate_width ?? width - 60} height={pdm.mounting_plate_height ?? height - 60} fill="#1E293B" stroke="#475569" strokeWidth={2} rx={6} />
            {showZones && zones.map((zone, index) => <g key={zone.name} pointerEvents="none"><rect x={zone.x_min} y={height - zone.y_max} width={zone.x_max - zone.x_min} height={zone.y_max - zone.y_min} fill={`hsla(${index * 60},70%,50%,0.08)`} stroke={`hsla(${index * 60},70%,50%,0.3)`} strokeDasharray="5,5" /><text x={zone.x_min + 10} y={height - zone.y_max + 18} fill={`hsla(${index * 60},70%,65%,0.9)`} fontSize="10">ZONE: {zone.name}</text></g>)}
            {(pdm.ducts||[]).map(d=><g key={d.id} onClick={()=>selectObject(d.id)} className="cursor-pointer"><rect x={d.x} y={height-d.y-d.height} width={d.width} height={d.height} fill={selectedObjectId===d.id?'#3B82F6':'#64748B'} fillOpacity={.65} stroke="#CBD5E1" strokeWidth={1}/><title>{d.label}: {d.capacity_pct}% fill, {d.route_ids.length} wires</title></g>)}
            {rails.map((rail) => <g key={rail.id} pointerEvents="none"><rect x={rail.x} y={height - rail.y - rail.profile_height / 2} width={rail.length} height={rail.profile_height} fill="#475569" stroke="#64748B" rx={2} /><text x={rail.x + 10} y={height - rail.y - 3} fill="#94A3B8" fontSize="9">{rail.label}</text></g>)}
            {showRoutes && routes.map((route) => route.waypoints.length < 2 ? null : <polyline key={route.id} points={route.waypoints.map((point) => `${point.x},${height - point.y}`).join(' ')} fill="none" stroke={route.color_hex} strokeWidth={2.5} strokeOpacity={0.7} strokeDasharray={route.wire_class === 'NEUTRAL' ? '4,4' : 'none'} pointerEvents="none" />)}
            {showClearances && warnings.map((warning) => {
              if (warning.type === 'CLEARANCE') return warning.componentIds.map((id) => {
                const component = components.find((item) => item.cem_component_id === id);
                const transform = component && componentTransform(component, editorTransforms[id]);
                if (!component || !transform) return null;
                const pad = component.rail_id ? 4 : 20;
                return <rect key={`${warning.id}:${id}`} x={transform.x - pad} y={height - transform.y - component.height - pad} width={component.width + pad * 2} height={component.height + pad * 2} fill="#F59E0B" fillOpacity="0.05" stroke="#F59E0B" strokeDasharray="5,4" strokeWidth={1.5} pointerEvents="none" />;
              });
              return null;
            })}
            {components.map((component) => {
              const id = component.cem_component_id;
              const transform = componentTransform(component, editorTransforms[id]);
              const selectedComponent = selectedObjectId === id || selectedObjectId === component.id;
              const hovered = hoveredObjectId === id || hoveredObjectId === component.id;
              const flagged = warningIds.has(id);
              const centerX = transform.x + component.width / 2;
              const centerY = height - transform.y - component.height / 2;
              return <g key={component.id} transform={`translate(${centerX},${centerY}) rotate(${-transform.rotation_deg})`} onPointerDown={(event) => beginDrag(event, id)} onPointerMove={(event) => updatePosition(event, id)} onPointerUp={commitLayoutEdit} onPointerCancel={commitLayoutEdit} onClick={() => selectObject(id)} onMouseEnter={() => hoverObject(id)} onMouseLeave={() => hoverObject(null)} className="cursor-move" tabIndex={0} role="button" aria-label={`Move ${id}`}>
                <rect x={-component.width / 2} y={-component.height / 2} width={component.width} height={component.height} rx={4} fill={flagged ? '#991B1B' : selectedComponent ? '#1E40AF' : hovered ? '#1E293B' : component.color_hex} fillOpacity={0.9} stroke={flagged ? '#F87171' : selectedComponent ? '#60A5FA' : '#1E293B'} strokeWidth={selectedComponent || flagged ? 3 : 1} />
                <text x={0} y={4} textAnchor="middle" fill="#FFFFFF" fontSize="10" fontWeight="bold" fontFamily="monospace" pointerEvents="none">{id}</text>
              </g>;
            })}
          </svg>
          <div className="pointer-events-none absolute bottom-5 left-5 rounded bg-slate-950/80 px-2 py-1 text-[10px] text-slate-400">Drag footprints · PDM origin at lower left · dimensions in mm</div>
        </div>
      </div>

      <aside className="flex min-h-[240px] flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-900 p-4">
        <div className="flex items-center justify-between"><h4 className="text-sm font-semibold text-slate-100">Placement properties</h4>{selected && <span className="text-[10px] text-blue-300">{selected.cem_component_id}</span>}</div>
        {selected && selectedTransform ? <>
          <div className="rounded-lg border border-slate-800 bg-slate-950 p-2.5 text-xs"><div className="font-semibold text-slate-100">{selected.name}</div><div className="mt-1 text-slate-400">{selected.category} · {selected.width} × {selected.height} × {selected.depth} mm</div><div className="text-slate-500">PDM ID {selected.id} · {selected.rail_id || 'Plate mounted'}</div></div>
          <div className="grid grid-cols-2 gap-2">{(['x', 'y', 'z', 'rotation_deg'] as const).map((field) => <label key={field} className="text-[10px] uppercase text-slate-400">{field === 'rotation_deg' ? 'Rotation °' : `${field} mm`}<input aria-label={field === 'rotation_deg' ? 'Rotation degrees' : `${field.toUpperCase()} mm`} type="number" value={Number(selectedTransform[field].toFixed(1))} step={field === 'rotation_deg' ? 15 : editorGridMm} onChange={(event) => updateNumeric(field, Number(event.target.value))} onBlur={() => { commitEditorTransform(); void validateCurrentPlacement(); }} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100" /></label>)}</div>
          <div className="flex gap-2"><button onClick={() => selectObject(null)} className="editor-tool"><EyeOff className="h-3.5 w-3.5" />Deselect</button><span className="self-center text-[10px] text-slate-500">Changes are applied to PDM on validation.</span></div>
        </> : <p className="text-xs leading-5 text-slate-400">Select a footprint to edit its physical position and orientation.</p>}
        <div className="mt-auto border-t border-slate-800 pt-3"><div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-300"><ShieldAlert className="h-3.5 w-3.5 text-amber-400" />Placement checks <span className="ml-auto font-mono text-slate-500">{warnings.length}</span></div>
          <div className="max-h-36 space-y-1 overflow-auto">{warnings.length ? warnings.slice(0, 8).map((warning) => <div key={warning.id} className={`rounded px-2 py-1.5 text-[10px] ${warning.type === 'COLLISION' || warning.type === 'BOUNDARY' ? 'bg-red-950/60 text-red-200' : 'bg-amber-950/50 text-amber-200'}`}>{warning.message}</div>) : <div className="text-[10px] text-emerald-300">No prototype geometry warnings.</div>}</div>
          {pdm.validation_results.length > 0 && <div className="mt-2 border-t border-slate-800 pt-2"><div className="mb-1 text-[10px] font-semibold text-slate-400">Backend PDM validator</div>{pdm.validation_results.slice(0, 6).map((violation, index) => <div key={`${violation.type}:${violation.object_a}:${index}`} className={`mb-1 rounded px-2 py-1 text-[10px] ${violation.severity === 'CRITICAL' ? 'bg-red-950/60 text-red-200' : 'bg-amber-950/50 text-amber-200'}`}>{violation.message}</div>)}</div>}
          {errorMessage && <div role="alert" className="mt-2 text-[10px] text-red-300">{errorMessage}</div>}
        </div>
      </aside>
    </div>
    <div className="flex items-center gap-2 rounded-xl border border-amber-700/30 bg-amber-950/20 px-3 py-2 text-[10px] text-amber-100"><Eye className="h-3.5 w-3.5" />Prototype clearance checks are advisory; moving components can make existing wire routes stale. Run design generation to regenerate routes and downstream artifacts.</div>
  </div>;
};
