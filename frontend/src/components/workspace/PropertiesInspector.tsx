import {useEffect} from 'react';
import {MousePointer2,Ruler} from 'lucide-react';
import {useProjectStore} from '../../stores/projectStore';
import {useWorkspaceStore} from '../../stores/workspaceStore';
import {componentTransform} from '../threeD/editorGeometry';
import type {SchematicGraphData} from '../schematic/schematicGraph';

const wireColors:Record<string,string>={POWER:'#EF4444',CONTROL:'#A78BFA',SIGNAL:'#F59E0B',NEUTRAL:'#3B82F6',PE:'#22C55E'};

export function PropertiesInspector(){
  const state=useProjectStore();
  const {tool,measurement,measure}=useWorkspaceStore();
  const {pdm,cem,selectedObjectId:id,editorTransforms}=state;
  const part=pdm?.components.find(c=>c.cem_component_id===id||c.id===id);
  const electrical=cem?.components.find(c=>c.id===(part?.cem_component_id||id));
  const schematic=state.schematicData as SchematicGraphData|null;
  const wire=schematic?.wires.find(w=>w.id===id);
  const route=pdm?.routes.find(r=>r.id===id||r.conductor_id===id||r.net_id===id);
  const accessory=pdm?.accessories?.find(p=>p.id===id);
  const duct=pdm?.ducts?.find(p=>p.id===id);
  const rail=pdm?.rails.find(p=>p.id===id);
  useEffect(()=>{if(tool==='measure'&&part)measure(part.cem_component_id);},[tool,part?.cem_component_id,measure]);
  const rows=(values:Record<string,unknown>)=><dl className="property-list">{Object.entries(values).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{String(value??'—')}</dd></div>)}</dl>;
  const commit=()=>{state.commitEditorTransform();void state.validateCurrentPlacement();};
  const pose=part?componentTransform(part,editorTransforms[part.cem_component_id]):null;
  const measured=measurement.map(key=>pdm?.components.find(c=>c.cem_component_id===key)).filter((p):p is NonNullable<typeof p>=>!!p);
  const centers=measured.map(p=>{const t=componentTransform(p,editorTransforms[p.cem_component_id]);return [t.x+p.width/2,t.y+p.height/2,t.z+p.depth/2];});
  const editable=!state.isGenerating&&!state.isLoadingProject&&!state.pendingRecovery;
  return <aside aria-label="Properties inspector" className="properties-inspector">
    <div className="panel-heading">PROPERTIES <span>{id||'No selection'}</span></div>
    {tool==='measure'&&<section className="property-section measurement"><h3><Ruler size={14}/>Measure</h3><p>Select two components in a canvas or browser.</p>
      <div>{measurement.length?measurement.join(' → '):'No components selected'}</div>
      {centers.length===2&&rows({'Center distance':`${Math.hypot(...centers[0].map((v,i)=>v-centers[1][i])).toFixed(2)} mm`,'ΔX':`${Math.abs(centers[0][0]-centers[1][0]).toFixed(2)} mm`,'ΔY':`${Math.abs(centers[0][1]-centers[1][1]).toFixed(2)} mm`,'ΔZ':`${Math.abs(centers[0][2]-centers[1][2]).toFixed(2)} mm`})}
      <p>Distances use component centers in the current placement draft.</p></section>}
    {!id&&<div className="inspector-empty"><MousePointer2 size={26}/><strong>Select a design object</strong><p>Select in the browser, schematic, layout, assembly or BOM to inspect the same object here.</p></div>}
    {(part||electrical)&&<>
      <section className="property-section"><h3>{part?.name||electrical?.name}</h3>{rows({'Object ID':part?.cem_component_id||id,'Category':part?.category||electrical?.category,'Catalog part':electrical?.catalog_id,'Physical ID':part?.id})}</section>
      {part&&pose&&<section className="property-section"><h3>Placement <small>draft · mm</small></h3><div className="property-fields">{(['x','y','z','rotation_deg'] as const).map(field=><label key={field}>{field==='rotation_deg'?'Rotation Z · °':`${field.toUpperCase()} · mm`}<input type="number" aria-label={`Inspector ${field}`} value={Number(pose[field].toFixed(2))} step={field==='rotation_deg'?15:state.editorGridMm} disabled={!editable}
        onChange={event=>{const value=Number(event.target.value);if(Number.isFinite(value)&&event.target.value!=='')state.updateEditorTransform(part.cem_component_id,{[field]:state.editorSnapEnabled?Math.round(value/(field==='rotation_deg'?15:state.editorGridMm))*(field==='rotation_deg'?15:state.editorGridMm):value});}}
        onBlur={commit} onKeyDown={e=>{if(e.key==='Enter')e.currentTarget.blur();}}/></label>)}</div>
        <button className="workspace-button" disabled={!editable||state.isValidatingPlacement} onClick={commit}>{state.isValidatingPlacement?'Rerouting…':'Apply & validate'}</button>
        <p>Save preserves this editor draft. Generation and exports use the engineering revision. Rotated-device rerouting is currently unsupported.</p></section>}
      <section className="property-section"><h3>Specification</h3>{rows({'Width':`${part?.width??electrical?.width} mm`,'Height':`${part?.height??electrical?.height} mm`,'Depth':`${part?.depth??electrical?.depth} mm`,'Rated current':electrical?`${electrical.current_rating} A`:undefined,'Rail':part?.rail_id,'Heat loss':`${part?.heat_loss_watts??electrical?.heat_loss} W`})}<p>Catalog specifications are read-only.</p></section>
    </>}
    {wire&&<section className="property-section"><h3>Electrical connection</h3>{rows({'ID':wire.id,'From':`${wire.from}:${wire.from_terminal}`,'To':`${wire.to}:${wire.to_terminal}`})}<label className="property-label">Net label<input aria-label="Inspector net label" value={wire.net_name} disabled={!editable} onChange={e=>state.setSchematicDraft({...schematic,wires:schematic!.wires.map(w=>w.id===wire.id?{...w,net_name:e.target.value}:w)})}/></label><label className="property-label">Wire class<select aria-label="Inspector wire class" value={wire.wire_class} disabled={!editable} onChange={e=>state.setSchematicDraft({...schematic,wires:schematic!.wires.map(w=>w.id===wire.id?{...w,wire_class:e.target.value,color:wireColors[e.target.value]}:w)})}>{['POWER','CONTROL','SIGNAL','NEUTRAL','PE'].map(value=><option key={value} value={value}>{value}</option>)}</select></label><p>Schematic presentation draft; CEM connectivity is unchanged.</p></section>}
    {route&&<section className="property-section"><h3>Physical wire</h3>{rows({'Net':route.net_name,'Length':`${(route.geometry?.centerline_length_mm||route.length_mm).toFixed(1)} mm`,'Bends':route.bend_count,'Status':route.status||'Unresolved','Dimensions':route.dimension_source||'Legacy estimate'})}</section>}
    {duct&&<section className="property-section"><h3>{duct.label}</h3>{rows({'Catalog':duct.catalog_id,'Width':`${duct.width} mm`,'Height':`${duct.height} mm`,'Depth':`${duct.depth} mm`,'Duct fill':`${duct.capacity_pct}% / ${duct.max_fill_pct}%`,'Conductors':duct.route_ids.length})}</section>}
    {rail&&<section className="property-section"><h3>{rail.label}</h3>{rows({'Length':`${rail.length} mm`,'Height':`${rail.profile_height} mm`,'Orientation':rail.orientation||'HORIZONTAL'})}</section>}
    {accessory&&<section className="property-section"><h3>{accessory.name}</h3>{rows({'Catalog':accessory.catalog_id,'Material':accessory.material,'Width':`${accessory.width} mm`,'Height':`${accessory.height} mm`,'Depth':`${accessory.depth} mm`})}</section>}
    {id&&!part&&!electrical&&!wire&&!route&&!accessory&&!duct&&!rail&&<section className="property-section"><h3>Design reference</h3>{rows({'ID':id})}<p>Open the relevant design view to inspect this reference.</p></section>}
  </aside>;
}
