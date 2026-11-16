import {useState} from 'react';
import {useProjectStore} from '../../stores/projectStore';
import {useCommandStore} from '../../stores/commandStore';
import {canEditEngineering, proposeOperation} from '../../stores/operationActions';
import type {ConductorIntent} from '../../types/operations';

export interface ConnectionDraft {action: 'CREATE' | 'REPLACE' | 'DELETE'; connectionId: string | null; sourcePin?: string; targetPin?: string}

export function ConnectionPreview({initial, onClose}: {initial: ConnectionDraft; onClose: ()=>void}) {
  const state=useProjectStore(), command=useCommandStore();
  const view=state.document!, page=view.snapshots.schematic!, cem=view.snapshots.cem!;
  const existing=cem.connections.find(c=>c.id===initial.connectionId);
  const pins=page.symbols.flatMap(s=>s.pins.map(p=>({id:p.id,component:s.component_id,terminal:p.terminal_id})));
  const [source,setSource]=useState(initial.sourcePin||pins.find(p=>p.component===existing?.from_component&&p.terminal===existing?.from_terminal)?.id||'');
  const [target,setTarget]=useState(initial.targetPin||pins.find(p=>p.component===existing?.to_component&&p.terminal===existing?.to_terminal)?.id||'');
  const [net,setNet]=useState(existing?.net_id||'');
  const [material,setMaterial]=useState(existing?.conductor_material||'COPPER');
  const [area,setArea]=useState(String(existing?.cross_section_mm2??''));
  const [diameter,setDiameter]=useState(String(existing?.insulation_diameter_mm??''));
  const [insulation,setInsulation]=useState(existing?.insulation_type||'');
  const [bend,setBend]=useState(String(existing?.minimum_bend_radius_mm??''));
  const [error,setError]=useState('');
  const editable=canEditEngineering();
  const preview=async()=>{
    setError('');
    const a=pins.find(p=>p.id===source),b=pins.find(p=>p.id===target),n=cem.nets.find(n=>n.id===net);
    if(initial.action!=='DELETE'&&(!a||!b||!n||!insulation.trim()||[area,diameter,bend].some(v=>!v||!Number.isFinite(Number(v))||Number(v)<=0))){
      setError('Choose two pins, an existing net and positive conductor dimensions with insulation.');return;
    }
    const conductor: ConductorIntent | null=initial.action==='DELETE'?null:{from_component:a!.component,from_terminal:a!.terminal,
      to_component:b!.component,to_terminal:b!.terminal,net_id:n!.id,wire_class:n!.wire_class as ConductorIntent['wire_class'],
      conductor_material:material as ConductorIntent['conductor_material'],cross_section_mm2:Number(area),
      insulation_diameter_mm:Number(diameter),insulation_type:insulation,minimum_bend_radius_mm:Number(bend)};
    const routes=view.snapshots.pdm?.routes.filter(r=>r.conductor_id===initial.connectionId).map(r=>r.id)||[];
    const removed=existing&&cem.connections.filter(c=>c.net_id===existing.net_id&&c.id!==existing.id).length===0&&
      conductor?.net_id!==existing.net_id?[existing.net_id]:[];
    if(proposeOperation({type:'ModifyElectricalConnection',target:{connection_id:initial.connectionId},
      parameters:{action:initial.action,conductor,invalidated_route_ids:routes,removed_net_ids:removed}},['cem','pdm','schematic']))
      await useCommandStore.getState().previewProposal();
  };
  const operation=command.proposal?.kind==='operations'?command.proposal.request.operations[0]:null;
  const ours=operation?.type==='ModifyElectricalConnection';
  const effects=command.preview;
  return <section aria-label="Connection effect preview" className="rounded border border-slate-700 bg-slate-900 p-3 text-xs">
    <h3>{initial.action} electrical connection {initial.connectionId||''}</h3>
    <p>Changes CEM conductor/net membership and schematic wires. Graphical crossings create no connection.</p>
    {initial.action!=='DELETE'&&<fieldset disabled={!editable} className="flex flex-wrap gap-2">
      <label>From pin<select aria-label="From pin" value={source} onChange={e=>setSource(e.target.value)}><option value="">Choose pin</option>{pins.map(p=><option key={p.id} value={p.id}>{p.component}:{p.terminal}</option>)}</select></label>
      <label>To pin<select aria-label="To pin" value={target} onChange={e=>setTarget(e.target.value)}><option value="">Choose pin</option>{pins.map(p=><option key={p.id} value={p.id}>{p.component}:{p.terminal}</option>)}</select></label>
      <label>Existing net<select aria-label="Connection net" value={net} onChange={e=>setNet(e.target.value)}><option value="">Choose net</option>{cem.nets.map(n=><option key={n.id} value={n.id}>{n.name} · {n.wire_class}</option>)}</select></label>
      <label>Material<select aria-label="Conductor material" value={material} onChange={e=>setMaterial(e.target.value)}><option>COPPER</option><option>ALUMINIUM</option></select></label>
      <label>Area mm²<input aria-label="Conductor area mm2" type="number" value={area} onChange={e=>setArea(e.target.value)}/></label>
      <label>Diameter mm<input aria-label="Conductor diameter mm" type="number" value={diameter} onChange={e=>setDiameter(e.target.value)}/></label>
      <label>Insulation<input aria-label="Conductor insulation" value={insulation} onChange={e=>setInsulation(e.target.value)}/></label>
      <label>Bend radius mm<input aria-label="Conductor bend radius mm" type="number" value={bend} onChange={e=>setBend(e.target.value)}/></label>
    </fieldset>}
    <p>Before: {existing?`${existing.from_component}:${existing.from_terminal} → ${existing.to_component}:${existing.to_terminal} · ${existing.net_id}`:'No conductor'}</p>
    {ours&&<p>After: {operation.parameters.conductor?`${operation.parameters.conductor.from_component}:${operation.parameters.conductor.from_terminal} → ${operation.parameters.conductor.to_component}:${operation.parameters.conductor.to_terminal} · ${operation.parameters.conductor.net_id}`:'Conductor removed'} · Invalidated routes: {operation.parameters.invalidated_route_ids.join(', ')||'none'} · Removed nets: {operation.parameters.removed_net_ids?.join(', ')||'none'}</p>}
    {ours&&effects&&<p role="status">Server preview accepted · {effects.changes.map(c=>`${c.model}: ${c.changed_fields.join(', ')}`).join('; ')} · Recompute: {effects.dirty_stages.join(', ')}</p>}
    {(error||command.error)&&<p role="alert">{error||`${command.error?.code}: ${command.error?.message}`}</p>}
    <div className="flex gap-2">
      <button className="editor-tool" disabled={!editable} onClick={()=>void preview()}>Preview electrical effect</button>
      <button className="editor-tool" disabled={!ours||!effects||command.pending||!!command.error||!!state.viewedRevisionId} onClick={()=>void command.commitProposal().then(()=>{if(!useCommandStore.getState().proposal)onClose();})}>Apply electrical change</button>
      <button className="editor-tool" disabled={command.pending} onClick={()=>{if(ours)command.clear();onClose();}}>Cancel connection edit</button>
    </div>
  </section>;
}
