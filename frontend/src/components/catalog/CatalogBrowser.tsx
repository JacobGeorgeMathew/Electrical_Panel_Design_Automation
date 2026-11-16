import {useEffect,useState} from 'react';
import {Canvas} from '@react-three/fiber';
import {Bounds,OrbitControls} from '@react-three/drei';
import {assetUrl,fetchAccessories,fetchCatalogComponent,fetchCatalogFilters,searchCatalog} from '../../api/client';
import type {CatalogComponent,CatalogPage} from '../../types/api';
import {AssetObject} from '../threeD/AssetObject';
import {useProjectStore} from '../../stores/projectStore';
import {useCommandStore} from '../../stores/commandStore';
import {canEditEngineering,proposeOperation} from '../../stores/operationActions';
import {OperationPreview} from '../workspace/OperationPreview';

export function CatalogBrowser(){
  const project=useProjectStore(),command=useCommandStore();
  const [position,setPosition]=useState({x:'',y:'',z:''}),[zone,setZone]=useState(''),[rail,setRail]=useState('');
  const [placementError,setPlacementError]=useState('');
  const [q,setQ]=useState(''),[category,setCategory]=useState(''),[manufacturer,setManufacturer]=useState(''),[sort,setSort]=useState('code');
  const [filters,setFilters]=useState<{categories:string[];manufacturers:{id:string;name:string}[]}>({categories:[],manufacturers:[]});
  const [page,setPage]=useState(1),[data,setData]=useState<CatalogPage|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  const [selected,setSelected]=useState(''),[detail,setDetail]=useState<CatalogComponent|null>(null),[accessories,setAccessories]=useState<CatalogComponent[]>([]),[detailError,setDetailError]=useState('');
  useEffect(()=>{let active=true;fetchCatalogFilters().then(f=>active&&setFilters(f)).catch(e=>active&&setError(e.message));return()=>{active=false;};},[retry]);
  useEffect(()=>{
    const abort=new AbortController();
    setLoading(true);setError('');
    const timer=setTimeout(()=>searchCatalog(new URLSearchParams({q,category,manufacturer,sort,page:String(page),page_size:'12'}),abort.signal)
      .then(result=>{if(!abort.signal.aborted){setData(result);setLoading(false);}})
      .catch(e=>{if(!abort.signal.aborted){setError(e.message);setLoading(false);}}),250);
    return()=>{clearTimeout(timer);abort.abort();};
  },[q,category,manufacturer,sort,page,retry]);
  useEffect(()=>{
    if(!selected)return;
    const abort=new AbortController();setDetail(null);setDetailError('');
    Promise.all([fetchCatalogComponent(selected,abort.signal),fetchAccessories(selected,abort.signal)])
      .then(([d,a])=>{if(!abort.signal.aborted){setDetail(d);setAccessories(a);}})
      .catch(e=>{if(!abort.signal.aborted)setDetailError(e.message);});
    return()=>abort.abort();
  },[selected,retry]);
  const preview=detail?.cad_models?.flatMap(m=>m.assets).find(a=>a.file_format==='GLB'&&a.status==='READY');
  const adding=command.proposal?.kind==='operations'&&command.proposal.request.operations[0]?.type==='AddComponent';
  const addition=command.proposal?.kind==='operations'?command.proposal.request.operations.find(o=>o.type==='AddComponent'):null;
  const previewAdd=async()=>{
    if(!detail||!project.document)return;
    if(!zone||Object.values(position).some(v=>!v||!Number.isFinite(Number(v)))){setPlacementError('Enter finite enclosure coordinates and choose a zone.');return;}
    setPlacementError('');
    if(proposeOperation({type:'AddComponent',target:{panel_id:project.document.document.panel_id},parameters:{
      catalog_id:detail.code,component_version_id:detail.component_version_id,product_version_id:null,
      terminal_intent:'UNCONNECTED',terminal_ids:detail.terminals.map(t=>String(t.id)),
      placement:{position_mm:{x:Number(position.x),y:Number(position.y),z:Number(position.z)},zone_name:zone,rail_id:rail||null},
    }},['cem','pdm']))await useCommandStore.getState().previewProposal();
  };
  return <div className="flex-1 min-h-0 overflow-y-auto p-4">
    <OperationPreview/>
    <h2 className="mb-3 text-lg font-semibold">Component catalog</h2>
    <div className="mb-4 flex flex-wrap gap-2">
      <input aria-label="Search catalog" placeholder="Name, SKU or manufacturer" value={q} onChange={e=>{setQ(e.target.value);setPage(1);}} className="min-w-60 flex-1 rounded border border-slate-700 bg-slate-900 p-2 text-sm"/>
      <select aria-label="Catalog category" value={category} onChange={e=>{setCategory(e.target.value);setPage(1);}} className="rounded border border-slate-700 bg-slate-900 p-2 text-sm"><option value="">All categories</option>{filters.categories.map(c=><option key={c}>{c}</option>)}</select>
      <select aria-label="Catalog manufacturer" value={manufacturer} onChange={e=>{setManufacturer(e.target.value);setPage(1);}} className="rounded border border-slate-700 bg-slate-900 p-2 text-sm"><option value="">All manufacturers</option>{filters.manufacturers.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select>
      <select aria-label="Catalog sort" value={sort} onChange={e=>setSort(e.target.value)} className="rounded border border-slate-700 bg-slate-900 p-2 text-sm"><option value="code">Code</option><option value="name">Name</option><option value="current_rating">Current rating</option></select>
    </div>
    {error&&<div role="alert" className="mb-3 text-sm text-red-300">{error} <button onClick={()=>setRetry(v=>v+1)} className="underline">Retry</button></div>}
    <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
      <section><div role="status" className="mb-2 text-xs text-slate-400">{loading?'Loading catalog…':`${data?.total??0} components`}</div>
        {!loading&&!error&&data?.items.length===0&&<p className="text-sm text-slate-400">No matching components.</p>}
        <div className="grid gap-2 sm:grid-cols-2">{data?.items.map(c=><button key={c.id} onClick={()=>setSelected(c.id)} className={`rounded-xl border p-3 text-left ${selected===c.id?'border-blue-500 bg-blue-950/40':'border-slate-800 bg-slate-900'}`}>
          <div className="text-sm font-semibold">{c.name}</div><div className="text-xs text-slate-400">{c.code} · {c.category}</div>
          <div className="mt-1 text-xs text-slate-500">{c.current_rating} A · {c.width} × {c.height} × {c.depth} mm</div>
        </button>)}</div>
        <div className="mt-3 flex items-center gap-3 text-xs"><button disabled={loading||page===1} onClick={()=>setPage(v=>v-1)} className="editor-tool disabled:opacity-40">Previous</button><span>Page {page}</span><button disabled={loading||!data||page*data.page_size>=data.total} onClick={()=>setPage(v=>v+1)} className="editor-tool disabled:opacity-40">Next</button></div>
      </section>
      <aside className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        {!selected?<p className="text-sm text-slate-400">Select a component to inspect its version and assets.</p>:detailError?<div role="alert" className="text-red-300">{detailError} <button className="underline" onClick={()=>setRetry(v=>v+1)}>Retry</button></div>:!detail?<p>Loading component…</p>:<>
          <h3 className="text-sm font-semibold">{detail.name}</h3><p className="mt-1 text-xs text-slate-400">Version {detail.version_no} · {detail.sku}</p>
          {preview?.url?<div className="my-3 h-48 rounded bg-slate-950"><Canvas camera={{position:[0.2,0.2,0.3]}}><ambientLight intensity={1}/><directionalLight position={[2,3,4]} intensity={2}/><Bounds fit clip observe><AssetObject url={assetUrl(preview.url)}/></Bounds><OrbitControls makeDefault/></Canvas></div>:<p className="my-3 text-xs text-amber-300">3D preview is unavailable.</p>}
          <dl className="mt-3 grid grid-cols-2 gap-2 text-xs"><dt className="text-slate-400">Manufacturer</dt><dd>{detail.manufacturer||'Unspecified'}</dd><dt className="text-slate-400">Rated current</dt><dd>{detail.current_rating} A</dd><dt className="text-slate-400">Rated voltage</dt><dd>{detail.rated_voltage_v??'Unspecified'} V</dd><dt className="text-slate-400">Breaking capacity</dt><dd>{detail.breaking_capacity} kA</dd><dt className="text-slate-400">Mounting</dt><dd>{detail.mounting}</dd><dt className="text-slate-400">Terminals</dt><dd>{detail.terminals.length}</dd></dl>
          <section aria-label="Add catalog component" className="mt-4 text-xs">
            <h4>Add exact catalog version to working panel</h4>
            <p>All catalog terminals remain unconnected: {detail.terminals.map(t=>String(t.id)).join(', ')}. Review placement and downstream dirty stages before Apply.</p>
            <fieldset disabled={!canEditEngineering()}>
              {(['x','y','z'] as const).map(axis=><label key={axis}>{axis.toUpperCase()} mm<input aria-label={`Catalog placement ${axis}`} type="number" value={position[axis]} onChange={e=>setPosition({...position,[axis]:e.target.value})}/></label>)}
              <label>Zone<select aria-label="Catalog placement zone" value={zone} onChange={e=>setZone(e.target.value)}><option value="">Choose zone</option>{project.pdm?.zones.map(z=><option key={z.name}>{z.name}</option>)}</select></label>
              <label>Rail<select aria-label="Catalog placement rail" value={rail} onChange={e=>setRail(e.target.value)}><option value="">Plate mounted</option>{project.pdm?.rails.map(r=><option key={r.id} value={r.id}>{r.label}</option>)}</select></label>
              <button className="editor-tool" onClick={()=>void previewAdd()}>Preview catalog addition</button>
            </fieldset>
            {placementError&&<p role="alert">{placementError}</p>}
            {adding&&addition?.type==='AddComponent'&&command.preview&&<><p role="status">Server preview · {addition.parameters.catalog_id} · version {addition.parameters.component_version_id} · position {Object.values(addition.parameters.placement.position_mm).join(', ')} mm · Added CEM and PDM component · Dirty: {command.preview.dirty_stages.join(', ')}</p>
              <button className="editor-tool" disabled={command.pending||!!command.error||!!project.viewedRevisionId} onClick={()=>void command.commitProposal()}>Apply catalog addition</button></>}
          </section>
          <h4 className="mt-4 text-xs font-semibold">CAD parameters</h4><ul className="mt-1 space-y-1 text-xs text-slate-400">{detail.cad_models?.flatMap(m=>m.parameters).map(p=><li key={p.code}>{p.code}: {String(p.default_value)} {p.unit_code} · {p.editable?'configurable':'fixed'}{p.min_value!==null?` · min ${p.min_value}`:''}{p.max_value!==null?` · max ${p.max_value}`:''}</li>)}</ul>
          <h4 className="mt-4 text-xs font-semibold">Compatible accessories</h4><ul className="mt-1 text-xs text-slate-400">{accessories.length?accessories.map(a=><li key={a.id}>{a.name}</li>):<li>No compatible accessories recorded.</li>}</ul>
          <details className="mt-4 text-xs text-slate-400"><summary>Technical specification</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap">{JSON.stringify(detail.specification,null,2)}</pre></details>
        </>}
      </aside>
    </div>
  </div>;
}
