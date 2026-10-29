import {useProjectStore} from '../../stores/projectStore';

export function WireInspector(){
  const {pdm,selectedObjectId,selectObject,wireVisibility,toggleWireVisibility,activeTab}=useProjectStore();
  if(!pdm||!['schematic','layout2d','threeD'].includes(activeTab))return null;
  const route=pdm.routes.find(r=>[r.id,r.conductor_id,r.net_id].includes(selectedObjectId||''));
  return <section aria-label="Wire inspection" className="max-h-36 shrink-0 overflow-auto border-t border-slate-800 bg-slate-900 px-4 py-2 text-xs text-slate-300">
    <div className="flex flex-wrap items-center gap-3"><button className="editor-tool" onClick={toggleWireVisibility}>{wireVisibility?'Hide':'Show'} physical wires</button>
      <select aria-label="Inspect electrical net" value={route?.net_id||''} onChange={e=>selectObject(e.target.value||null)} className="rounded border border-slate-700 bg-slate-950 p-1"><option value="">Inspect a net</option>{[...new Map(pdm.routes.map(r=>[r.net_id,r])).values()].map(r=><option key={r.net_id} value={r.net_id}>{r.net_name}</option>)}</select>
      {route&&<span>{route.conductor_id||route.id} | {route.from_component}:{route.from_terminal} → {route.to_component}:{route.to_terminal} | {(route.geometry?.centerline_length_mm||route.length_mm).toFixed(1)} mm | {route.bend_count} bends | Ø {route.wire_diameter_mm} mm ({route.dimension_source||'legacy estimate'}) | {route.status||'UNRESOLVED'}</span>}
    </div>
    {route?.geometry?.checks.filter(c=>c.status!=='PASS').map(c=><p key={c.type} className="mt-1 text-amber-300">{c.status}: {c.message}</p>)}
  </section>;
}
