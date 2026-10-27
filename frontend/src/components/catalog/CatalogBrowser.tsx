import {useEffect,useState} from 'react';
import {Canvas} from '@react-three/fiber';
import {Bounds,OrbitControls} from '@react-three/drei';
import {assetUrl,fetchAccessories,fetchCatalogComponent,fetchCatalogFilters,searchCatalog} from '../../api/client';
import type {CatalogComponent,CatalogPage} from '../../types/api';
import {AssetObject} from '../threeD/AssetObject';

export function CatalogBrowser(){
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
  return <div className="flex-1 min-h-0 overflow-y-auto p-4">
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
          <h4 className="mt-4 text-xs font-semibold">CAD parameters</h4><ul className="mt-1 space-y-1 text-xs text-slate-400">{detail.cad_models?.flatMap(m=>m.parameters).map(p=><li key={p.code}>{p.code}: {String(p.default_value)} {p.unit_code} · {p.editable?'configurable':'fixed'}{p.min_value!==null?` · min ${p.min_value}`:''}{p.max_value!==null?` · max ${p.max_value}`:''}</li>)}</ul>
          <h4 className="mt-4 text-xs font-semibold">Compatible accessories</h4><ul className="mt-1 text-xs text-slate-400">{accessories.length?accessories.map(a=><li key={a.id}>{a.name}</li>):<li>No compatible accessories recorded.</li>}</ul>
          <details className="mt-4 text-xs text-slate-400"><summary>Technical specification</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap">{JSON.stringify(detail.specification,null,2)}</pre></details>
        </>}
      </aside>
    </div>
  </div>;
}
