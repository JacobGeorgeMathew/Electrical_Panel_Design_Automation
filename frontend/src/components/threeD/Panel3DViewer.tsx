import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AssetObject } from './AssetObject';
import { assetUrl } from '../../api/client';
import { Canvas, useThree } from '@react-three/fiber';
import { Line, OrbitControls, Text, TransformControls } from '@react-three/drei';
import { useProjectStore } from '../../stores/projectStore';
import { AlertTriangle, Box, Eye, EyeOff, Layers, MousePointer2, Redo2, Rotate3D, RotateCcw,
  Sparkles, Undo2, Move3D } from 'lucide-react';
import * as THREE from 'three';
import { fitPanelCamera } from './cameraFit';
import { analyzeEditorGeometry, componentTransform } from './editorGeometry';
import { PhysicalComponent } from '../../types/pdm';

export const ResponsiveCamera: React.FC<{ width: number; height: number; depth: number }> = ({ width, height, depth }) => {
  const { camera, size } = useThree();
  React.useEffect(() => {
    if (size.width < 1 || size.height < 1) return;
    const fit = fitPanelCamera({ width, height, depth }, size.width / size.height, 45);
    camera.position.set(...fit.position);
    camera.lookAt(...fit.center);
    camera.near = 0.01;
    camera.far = Math.max(width, height, depth) * 20;
    camera.updateProjectionMatrix();
  }, [camera, size.width, size.height, width, height, depth]);
  return null;
};

type ComponentMeshProps = {
  comp: PhysicalComponent;
  transform: { x: number; y: number; z: number; rotation_deg: number };
  isSelected: boolean;
  isHovered: boolean;
  exploded: boolean;
  hidden: boolean;
  mode: 'translate' | 'rotate' | null;
  snapEnabled: boolean;
  gridMm: number;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
  onTransform: (id: string, transform: { x: number; y: number; z: number; rotation_deg: number }) => void;
  onCommit: () => void;
};

const ComponentMesh: React.FC<ComponentMeshProps> = ({ comp, transform, isSelected, isHovered, exploded, hidden,
  mode, snapEnabled, gridMm, onSelect, onHover, onTransform, onCommit }) => {
  // Drei's TransformControls expects a mutable ref whose current value is non-null.
  // React attaches the group before the selected gizmo is rendered.
  const groupRef = useRef<THREE.Group>(null!);
  const scale = 0.01;
  const w = comp.width * scale;
  const h = comp.height * scale;
  const d = comp.depth * scale;
  const explodedZOffset = exploded ? (comp.category === 'MCCB' ? 1.5 : 0.8) : 0;
  const position: [number, number, number] = [
    (transform.x + comp.width / 2) * scale,
    (transform.y + comp.height / 2) * scale,
    (transform.z + comp.depth / 2) * scale + explodedZOffset,
  ];

  const updateFromGizmo = () => {
    const group = groupRef.current;
    if (!group) return;
    const step = snapEnabled ? gridMm : 1;
    const snap = (value: number) => Math.round(value / step) * step;
    onTransform(comp.cem_component_id, {
      x: snap(group.position.x / scale - comp.width / 2),
      y: snap(group.position.y / scale - comp.height / 2),
      z: snap((group.position.z - explodedZOffset) / scale - comp.depth / 2),
      rotation_deg: snapEnabled
        ? Math.round(THREE.MathUtils.radToDeg(group.rotation.z) / 15) * 15
        : THREE.MathUtils.radToDeg(group.rotation.z),
    });
  };

  return (
    <>
      <group ref={groupRef} position={position} rotation={[0, 0, THREE.MathUtils.degToRad(transform.rotation_deg)]} visible={!hidden}>
        <group
          onClick={(event) => { event.stopPropagation(); onSelect(comp.cem_component_id); }}
          onPointerOver={(event) => { event.stopPropagation(); onHover(comp.cem_component_id); }}
          onPointerOut={() => onHover(null)}>
          {comp.preview_asset?.status === 'READY' && comp.preview_asset.url ?
            <AssetObject url={assetUrl(comp.preview_asset.url)} scale={10}
              fallback={<mesh><boxGeometry args={[w,h,d]}/><meshStandardMaterial color={comp.color_hex}/></mesh>}/> :
            <mesh><boxGeometry args={[w,h,d]}/><meshStandardMaterial color={comp.color_hex} metalness={0.4} roughness={0.3}/></mesh>}
          {(isSelected || isHovered) && <mesh><boxGeometry args={[w*1.02,h*1.02,d*1.02]}/>
            <meshBasicMaterial color={isSelected?'#3B82F6':'#60A5FA'} wireframe/></mesh>}
        </group>
        <Text position={[0, 0, d / 2 + 0.01]} fontSize={Math.min(w * 0.25, 0.12)} color="#FFFFFF"
          anchorX="center" anchorY="middle">{comp.cem_component_id}</Text>
      </group>
      {isSelected && mode && !hidden && (
        <TransformControls object={groupRef} mode={mode} size={0.8}
          translationSnap={snapEnabled ? gridMm * scale : null}
          rotationSnap={snapEnabled ? THREE.MathUtils.degToRad(15) : null}
          onObjectChange={updateFromGizmo} onMouseUp={onCommit} />
      )}
    </>
  );
};

const snapValue = (value: number, enabled: boolean, step: number) =>
  enabled ? Math.round(value / step) * step : value;

export const Panel3DViewer: React.FC = () => {
  const {
    pdm, selectedObjectId, selectObject, hoveredObjectId, hoverObject, explodedView,
    toggleExplodedView, wireVisibility, toggleWireVisibility,
    editorTransforms, editorHiddenComponentIds, editorMode, editorSnapEnabled, editorGridMm,
    editorUndoStack, editorRedoStack, setEditorMode, toggleEditorSnap, setEditorGridMm,
    toggleComponentVisibility, updateEditorTransform, commitEditorTransform,
    undoEditorTransform, redoEditorTransform, resetEditorDraft, artifacts, refreshCadPreview, cadJobStatus, designStale,
    hasUnsavedChanges, currentRevisionId,
  } = useProjectStore();

  const [showArtifact,setShowArtifact] = useState(false);
  const preview = artifacts.find(a=>a.file_format==='GLB'&&a.status==='READY');
  useEffect(()=>setShowArtifact(false),[currentRevisionId,designStale,editorTransforms]);
  const warnings = useMemo(() => pdm ? analyzeEditorGeometry(pdm.components, editorTransforms,
    { width: pdm.enclosure_width, height: pdm.enclosure_height, depth: pdm.enclosure_depth }) : [], [pdm, editorTransforms]);
  const selectedComponent = pdm?.components.find((component) =>
    component.cem_component_id === selectedObjectId || component.id === selectedObjectId) || null;
  const selectedId = selectedComponent?.cem_component_id;
  const selectedTransform = selectedComponent ? componentTransform(selectedComponent, editorTransforms[selectedComponent.cem_component_id]) : null;
  const hasDraftEdits = Object.keys(editorTransforms).length > 0;

  if (!pdm) {
    return <div className="p-12 text-center text-slate-500 font-mono text-sm">No 3D panel model loaded. Click "Generate Design" to create the 3D panel.</div>;
  }

  const scale = 0.01;
  const encW = pdm.enclosure_width * scale;
  const encH = pdm.enclosure_height * scale;
  const encD = pdm.enclosure_depth * scale;

  const updateNumeric = (field: 'x' | 'y' | 'z' | 'rotation_deg', value: number) => {
    if (!selectedComponent) return;
    const step = field === 'rotation_deg' ? 15 : editorGridMm;
    updateEditorTransform(selectedComponent.cem_component_id, {
      [field]: snapValue(value, editorSnapEnabled, step),
    });
  };

  return (
    <div className="flex flex-1 min-h-0 min-w-0 flex-col h-full bg-slate-950 p-3 md:p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900 border border-slate-800 p-3 rounded-2xl">
        <div className="flex min-w-0 items-center gap-3">
          <div className="p-2 bg-blue-500/10 text-blue-400 rounded-xl"><Box className="w-5 h-5" /></div>
          <div>
            <h3 className="text-sm font-bold text-slate-200">3D Assembly Editor</h3>
            <p className="text-xs text-slate-400">React Three Fiber • select, inspect, move and rotate PDM components</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button onClick={() => setEditorMode('select')} aria-pressed={editorMode === 'select'} title="Select components"
            className={`editor-tool ${editorMode === 'select' ? 'editor-tool-active' : ''}`}><MousePointer2 className="h-3.5 w-3.5" />Select</button>
          <button onClick={() => setEditorMode('translate')} aria-pressed={editorMode === 'translate'} title="Move selected component"
            className={`editor-tool ${editorMode === 'translate' ? 'editor-tool-active' : ''}`}><Move3D className="h-3.5 w-3.5" />Move</button>
          <button onClick={() => setEditorMode('rotate')} aria-pressed={editorMode === 'rotate'} title="Rotate selected component"
            className={`editor-tool ${editorMode === 'rotate' ? 'editor-tool-active' : ''}`}><Rotate3D className="h-3.5 w-3.5" />Rotate</button>
          <button onClick={toggleEditorSnap} aria-pressed={editorSnapEnabled} className={`editor-tool ${editorSnapEnabled ? 'editor-tool-active' : ''}`}>Snap {editorSnapEnabled ? 'On' : 'Off'}</button>
          <label className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-2 py-1.5 text-slate-300">
            Grid <input aria-label="Snap grid in millimeters" type="number" min="1" max="100" value={editorGridMm}
              onChange={(event) => setEditorGridMm(Number(event.target.value))} className="w-12 bg-slate-950 text-center text-slate-100 outline-none" /> mm
          </label>
          <button onClick={undoEditorTransform} disabled={!editorUndoStack.length} title="Undo transform" className="editor-tool disabled:opacity-40"><Undo2 className="h-3.5 w-3.5" />Undo</button>
          <button onClick={redoEditorTransform} disabled={!editorRedoStack.length} title="Redo transform" className="editor-tool disabled:opacity-40"><Redo2 className="h-3.5 w-3.5" />Redo</button>
          <button onClick={toggleExplodedView} aria-pressed={explodedView} className="editor-tool"><Sparkles className="h-3.5 w-3.5" />Explode</button>
          <button onClick={toggleWireVisibility} aria-pressed={wireVisibility} className="editor-tool"><Layers className="h-3.5 w-3.5" />Routes</button>
          <button onClick={resetEditorDraft} disabled={!hasDraftEdits} title="Discard local editor changes" className="editor-tool disabled:opacity-40"><RotateCcw className="h-3.5 w-3.5" />Reset</button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
        <button className="editor-tool disabled:opacity-40" disabled={!preview?.url || designStale || hasUnsavedChanges || hasDraftEdits}
          onClick={()=>setShowArtifact(v=>!v)}>{showArtifact?'Return to assembly editor':'View saved GLB'}</button>
        <button className="editor-tool disabled:opacity-40" onClick={refreshCadPreview}
          disabled={cadJobStatus==='PENDING'||designStale||hasUnsavedChanges}>Regenerate saved preview</button>
        <span role="status">{cadJobStatus==='PENDING'?'Generating preview…':showArtifact?'Saved revision GLB preview':preview?'Saved preview ready':'Saved preview unavailable'}</span>
        {preview?.url && !designStale && <a className="text-blue-300 underline" href={assetUrl(preview.url)} download>Download GLB</a>}
        {pdm.components.some(c=>c.preview_asset&&c.preview_asset.status!=='READY')&&<span className="text-amber-300">Some component assets are unavailable; showing their bounds.</span>}
      </div>
      {designStale && <div role="status" className="rounded border border-amber-800 bg-amber-950/40 p-2 text-xs text-amber-200">Showing the last saved design. Generate the current requirements to refresh geometry and exports.</div>}
      {hasDraftEdits && (
        <div role="status" className="flex items-start gap-2 rounded-xl border border-amber-700 bg-amber-950/40 px-3 py-2 text-xs text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Local 3D draft edits are not applied to the generated 2D layout, wire routes, validation report, BOM or FreeCAD export. Generate Design restores the validated assembly.</span>
        </div>
      )}

      <div className="grid flex-1 min-h-0 grid-cols-1 grid-rows-[minmax(110px,0.25fr)_minmax(220px,1fr)_minmax(150px,0.4fr)] gap-3 overflow-hidden xl:grid-cols-[220px_minmax(0,1fr)_280px] xl:grid-rows-1">
        <aside className="min-h-0 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/80 p-3" aria-label="Component tree">
          <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-300">Component tree ({pdm.components.length})</h4>
          <ul className="space-y-1">
            {pdm.components.map((component) => {
              const id = component.cem_component_id;
              const selected = selectedId === id;
              const hidden = editorHiddenComponentIds.includes(id);
              return <li key={component.id} className={`flex items-center gap-1 rounded-lg ${selected ? 'bg-blue-900/60' : 'hover:bg-slate-800'}`}>
                <button onClick={() => selectObject(id)} className="min-w-0 flex-1 truncate px-2 py-1.5 text-left text-xs text-slate-200" title={`${component.name} (${id})`}>
                  <span className="block truncate">{component.name}</span><span className="font-mono text-[10px] text-slate-500">{id}</span>
                </button>
                <button onClick={() => toggleComponentVisibility(id)} aria-label={`${hidden ? 'Show' : 'Hide'} ${id}`} title={hidden ? 'Show component' : 'Hide component'} className="p-2 text-slate-400 hover:text-white">
                  {hidden ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </li>;
            })}
          </ul>
        </aside>

        <div className="relative min-h-0 min-w-0 overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60">
          <Canvas camera={{ fov: 45, near: 0.01, far: Math.max(encW, encH, encD) * 20 }} className="h-full w-full">
            <ResponsiveCamera width={encW} height={encH} depth={encD} />
            <ambientLight intensity={0.7} />
            <directionalLight position={[10, 10, 10]} intensity={1.2} />
            <pointLight position={[-10, -10, 5]} intensity={0.5} />
            <OrbitControls makeDefault target={[encW / 2, encH / 2, encD / 2]} />
            {showArtifact && preview?.url ? <AssetObject url={assetUrl(preview.url)} scale={10}/> : <>
            <mesh position={[encW / 2, encH / 2, encD / 2]}>
              <boxGeometry args={[encW, encH, encD]} />
              <meshStandardMaterial color="#1E293B" wireframe transparent opacity={0.3} />
            </mesh>
            <mesh position={[(pdm.mounting_plate_x + (pdm.mounting_plate_width ?? pdm.enclosure_width - 60) / 2) * scale,
              (pdm.mounting_plate_y + (pdm.mounting_plate_height ?? pdm.enclosure_height - 60) / 2) * scale,
              (pdm.mounting_plate_z + 1.5) * scale]}>
              <boxGeometry args={[(pdm.mounting_plate_width ?? pdm.enclosure_width - 60) * scale,
                (pdm.mounting_plate_height ?? pdm.enclosure_height - 60) * scale, 0.03]} />
              <meshStandardMaterial color="#64748B" metalness={0.8} roughness={0.2} />
            </mesh>
            {pdm.rails.map((rail) => <mesh key={rail.id}
              position={[(rail.x + rail.length / 2) * scale, (rail.y + rail.profile_height / 2) * scale,
                (rail.z + rail.profile_depth / 2) * scale]}>
              <boxGeometry args={[rail.length * scale, rail.profile_height * scale, rail.profile_depth * scale]} />
              <meshStandardMaterial color="#94A3B8" metalness={0.9} roughness={0.1} />
            </mesh>)}
            {pdm.components.map((component) => {
              const id = component.cem_component_id;
              return <ComponentMesh key={component.id} comp={component}
                transform={componentTransform(component, editorTransforms[id])}
                isSelected={selectedId === id} isHovered={hoveredObjectId === id || hoveredObjectId === component.id}
                exploded={explodedView} hidden={editorHiddenComponentIds.includes(id)}
                mode={selectedId === id && editorMode !== 'select' ? editorMode : null}
                snapEnabled={editorSnapEnabled} gridMm={editorGridMm}
                onSelect={selectObject} onHover={hoverObject} onTransform={updateEditorTransform} onCommit={commitEditorTransform} />;
            })}
            {wireVisibility && pdm.routes.map((route) => <Line key={route.id}
              points={route.waypoints.map((point) => [point.x * scale, point.y * scale, point.z * scale])}
              color={hasDraftEdits ? '#F59E0B' : route.color_hex} lineWidth={1.5}
              transparent opacity={hasDraftEdits ? 0.35 : 0.8} dashed={hasDraftEdits} dashSize={0.08} gapSize={0.04} />)}
            </>}
          </Canvas>
          {warnings.length > 0 && <div className="absolute bottom-3 left-3 rounded-lg border border-amber-700 bg-slate-950/90 px-3 py-2 text-xs text-amber-200">
            {warnings.length} placement warning{warnings.length === 1 ? '' : 's'}
          </div>}
        </div>

        <aside className="min-h-0 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/80 p-3" aria-label="Properties inspector">
          <h4 className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-300">Properties inspector</h4>
          {!selectedComponent || !selectedTransform ? <p className="text-xs text-slate-500">Select a component in the tree or viewport.</p> : <>
            <div className="mb-3 border-b border-slate-800 pb-3">
              <p className="text-sm font-semibold text-slate-100">{selectedComponent.name}</p>
              <p className="font-mono text-[10px] text-blue-300">{selectedComponent.cem_component_id} · {selectedComponent.category}</p>
              <p className="mt-1 text-[10px] text-slate-500">{selectedComponent.width} × {selectedComponent.height} × {selectedComponent.depth} mm</p>
            </div>
            <label className="mb-3 flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={!editorHiddenComponentIds.includes(selectedComponent.cem_component_id)}
                onChange={() => toggleComponentVisibility(selectedComponent.cem_component_id)} /> Visible in 3D
            </label>
            <div className="grid grid-cols-2 gap-2">
              {(['x', 'y', 'z'] as const).map((field) => <label key={field} className="text-[10px] text-slate-400">
                Position {field.toUpperCase()} (mm)
                <input aria-label={`Position ${field.toUpperCase()} in millimeters`} type="number" value={Number(selectedTransform[field].toFixed(1))}
                  onChange={(event) => updateNumeric(field, Number(event.target.value))} onBlur={commitEditorTransform}
                  className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-100" />
              </label>)}
              <label className="text-[10px] text-slate-400">Rotation Z (°)
                <input aria-label="Rotation Z in degrees" type="number" value={Number(selectedTransform.rotation_deg.toFixed(1))}
                  onChange={(event) => updateNumeric('rotation_deg', Number(event.target.value))} onBlur={commitEditorTransform}
                  className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-100" />
              </label>
            </div>
          </>}
          <div className="mt-4 border-t border-slate-800 pt-3">
            <h5 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-300"><AlertTriangle className="h-3.5 w-3.5 text-amber-400" />Collision & clearance</h5>
            {warnings.length === 0 ? <p className="text-[10px] text-emerald-300">No draft placement warnings.</p> : <ul className="space-y-1.5">
              {warnings.slice(0, 12).map((warning) => <li key={warning.id} className={`text-[10px] ${warning.type === 'COLLISION' || warning.type === 'BOUNDARY' ? 'text-red-300' : 'text-amber-300'}`}>
                <span className="font-semibold">{warning.type}:</span> {warning.message}
              </li>)}
              {warnings.length > 12 && <li className="text-[10px] text-slate-500">and {warnings.length - 12} more</li>}
            </ul>}
            <p className="mt-2 text-[9px] leading-relaxed text-slate-500">Prototype footprint checks use rotated 2D bounding boxes. They do not replace backend physical validation.</p>
          </div>
        </aside>
      </div>
    </div>
  );
};
