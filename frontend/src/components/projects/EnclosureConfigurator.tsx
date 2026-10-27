import { useEffect,useState } from 'react';
import { fetchEnclosures } from '../../api/client';
import type { Enclosure } from '../../types/api';
import { useProjectStore } from '../../stores/projectStore';

export function EnclosureConfigurator(){
  const {projectConfiguration,setProjectConfiguration,isSaving,isGenerating,isLoadingProject}=useProjectStore();
  const [enclosures,setEnclosures]=useState<Enclosure[]>([]);
  const [error,setError]=useState('');
  const [attempt,setAttempt]=useState(0);
  useEffect(()=>{let active=true;fetchEnclosures().then(rows=>{if(active){setEnclosures(rows);setError('');}})
    .catch(e=>active&&setError(e.message));return()=>{active=false;};},[attempt]);
  const selected=enclosures.find(e=>e.id===projectConfiguration.enclosure_id);
  const parameters=selected?.parameters[0]?.parameters || [];
  const disabled=isSaving||isGenerating||isLoadingProject;
  return <section className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/80 p-4">
    <h3 className="text-sm font-semibold">Project enclosure configuration</h3>
    <p className="text-xs text-slate-400">Automatic selection uses the catalog dimensions. Configurable prototype models allow project dimensions without editing their shared definition.</p>
    {error?<div role="alert" className="text-xs text-red-300">{error} <button className="underline" onClick={()=>setAttempt(v=>v+1)}>Retry</button></div>:
    <select aria-label="Enclosure selection" value={projectConfiguration.enclosure_id||''} disabled={disabled} onChange={e=>setProjectConfiguration(e.target.value?{enclosure_id:e.target.value,enclosure_parameters:{}}:{})}
      className="w-full rounded border border-slate-700 bg-slate-950 p-2 text-sm">
      <option value="">Choose the smallest feasible enclosure automatically</option>
      {enclosures.map(e=><option key={e.id} value={e.id}>{e.name}</option>)}
    </select>}
    {selected && <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">{parameters.filter(p=>!p.derived).map(p=><label key={p.code} className="text-xs text-slate-400">{p.code} ({p.unit_code})
      <input aria-label={p.code} type="number" disabled={disabled||!p.editable} min={p.min_value??undefined} max={p.max_value??undefined}
        value={projectConfiguration.enclosure_parameters?.[p.code]??p.default_value}
        onChange={e=>setProjectConfiguration({...projectConfiguration,enclosure_parameters:{...projectConfiguration.enclosure_parameters,[p.code]:Number(e.target.value)}})}
        className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2 text-slate-200" />
    </label>)}</div>}
  </section>;
}
