import {useEffect,useState} from 'react';
import {useProjectStore} from '../stores/projectStore';
import {listProjects,updateProject,duplicateProject,deleteProject,exportProject,importProject} from '../api/client';
import type {ProjectRecord} from '../types/api';

export function ProjectDashboard(){
  const {archetypes,createNewProject,openProject,isSaving,isLoadingProject,errorMessage,clearError}=useProjectStore();
  const [query,setQuery]=useState(''),[recent,setRecent]=useState(false),[rows,setRows]=useState<ProjectRecord[]>([]);
  const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
  const [name,setName]=useState(''),[description,setDescription]=useState(''),[location,setLocation]=useState(''),[panelType,setPanelType]=useState('DB');
  const [editing,setEditing]=useState<{project:ProjectRecord;mode:'rename'|'duplicate'}|null>(null),[editName,setEditName]=useState('');
  useEffect(()=>{
    const abort=new AbortController();setLoading(true);
    const timer=setTimeout(()=>listProjects(abort.signal,query,recent).then(result=>{if(!abort.signal.aborted){setRows(result);setLoading(false);}})
      .catch(e=>{if(!abort.signal.aborted){setError(e.message);setLoading(false);}}),200);
    return()=>{clearTimeout(timer);abort.abort();};
  },[query,recent,refresh]);
  const act=async(task:()=>Promise<unknown>)=>{setBusy(true);setError('');try{await task();setRefresh(v=>v+1);}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}};
  const disabled=busy||isSaving||isLoadingProject;
  return <main className="min-h-dvh bg-slate-950 p-6 text-slate-100 md:p-10">
    <div className="mx-auto max-w-6xl space-y-6">
      <header><h1 className="text-3xl font-semibold">Electrical panel projects</h1><p className="mt-2 text-sm text-slate-400">Create an empty project or reopen your saved engineering work.</p></header>
      {(error||errorMessage)&&<div role="alert" className="rounded border border-red-800 bg-red-950 p-3">{error||errorMessage}<button className="ml-3 underline" onClick={()=>{setError('');clearError();setRefresh(v=>v+1);}}>Retry</button></div>}
      <form aria-label="Create project" onSubmit={e=>{e.preventDefault();void createNewProject(name,panelType,archetypes.find(a=>a.code===panelType)?.version_id,{description,location});}} className="space-y-3 rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h2 className="text-lg font-semibold">New project</h2>
        <div className="grid gap-3 md:grid-cols-3">
          <label className="text-sm">Project name<input required maxLength={200} aria-label="Project name" value={name} onChange={e=>setName(e.target.value)} className="mt-1 w-full rounded bg-slate-950 p-2"/></label>
          <label className="text-sm">Panel type<select aria-label="Panel type" value={panelType} onChange={e=>setPanelType(e.target.value)} className="mt-1 w-full rounded bg-slate-950 p-2">{archetypes.map(a=><option key={a.code} value={a.code} disabled={!a.supported}>{a.name}{!a.supported?' (unavailable)':''}</option>)}</select></label>
          <label className="text-sm">Location<input maxLength={500} aria-label="Location" value={location} onChange={e=>setLocation(e.target.value)} className="mt-1 w-full rounded bg-slate-950 p-2"/></label>
        </div>
        <label className="block text-sm">Description<textarea maxLength={10000} aria-label="Description" value={description} onChange={e=>setDescription(e.target.value)} className="mt-1 w-full rounded bg-slate-950 p-2"/></label>
        <button disabled={disabled||!name.trim()||!archetypes.some(a=>a.code===panelType&&a.supported)} className="rounded bg-blue-600 px-4 py-2 text-sm disabled:opacity-40">Create project</button>
      </form>
      <section className="space-y-4" aria-label="Saved projects">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-lg font-semibold">{recent?'Recent projects':'All projects'}</h2>
          <input aria-label="Search projects" placeholder="Search name, description or location" value={query} maxLength={200} onChange={e=>setQuery(e.target.value)} className="min-w-64 flex-1 rounded border border-slate-700 bg-slate-900 p-2 text-sm"/>
          <button className="editor-tool" aria-pressed={recent} onClick={()=>setRecent(v=>!v)}>{recent?'Show all':'Recent projects'}</button>
          <label className="editor-tool cursor-pointer">Import project<input aria-label="Import project" type="file" accept=".json,application/json" disabled={disabled} className="sr-only" onChange={e=>{
            const file=e.target.files?.[0];e.target.value='';if(!file)return;
            void act(async()=>{if(file.size>32*1024*1024)throw new Error('Project packages are limited to 32 MiB.');await importProject(JSON.parse(await file.text()));});
          }}/></label>
        </div>
        {loading?<p role="status">Loading projects…</p>:rows.length===0?<p className="text-slate-400">No projects found.</p>:<div className="grid gap-4 md:grid-cols-2">{rows.map(p=><article key={p.database_id} className="space-y-3 rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div><h3 className="text-lg font-semibold">{p.name}</h3><p className="text-xs text-slate-400">{p.archetype} · {p.location||'No location'} · {p.current_revision_id?'Saved design':'Empty design'}</p></div>
          <p className="whitespace-pre-wrap text-sm text-slate-400">{p.description}</p>
          <p className="break-all font-mono text-[10px] text-slate-500">ID {p.database_id}</p>
          <p className="text-xs text-slate-500">{p.last_opened_at?'Last opened '+new Date(p.last_opened_at).toLocaleString():'Not opened yet'}{p.recovery?' · Recovery available':''}</p>
          <div className="flex flex-wrap gap-2">
            <button className="editor-tool" disabled={disabled||p.archetype!=='DB'} onClick={()=>void openProject(p.id)}>Open</button>
            {(['rename','duplicate'] as const).map(mode=><button key={mode} className="editor-tool capitalize" disabled={disabled||p.archetype!=='DB'} onClick={()=>{setEditing({project:p,mode});setEditName(mode==='duplicate'?p.name+' copy':p.name);}}>{mode}</button>)}
            <button className="editor-tool" disabled={disabled} onClick={()=>void act(async()=>{
              const data=await exportProject(p.id),url=URL.createObjectURL(new Blob([JSON.stringify(data)],{type:'application/json'}));
              const link=document.createElement('a');link.href=url;link.download=`panel-project-${p.database_id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
            })}>Export</button>
            <button className="editor-tool text-red-300" disabled={disabled} onClick={()=>{if(window.confirm(`Delete “${p.name}”? It will be removed from your projects.`))void act(()=>deleteProject(p.id,p.lock_version));}}>Delete</button>
          </div>
        </article>)}</div>}
      </section>
    </div>
    {editing&&<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"><form role="dialog" aria-modal="true" aria-label={editing.mode==='rename'?'Rename project':'Duplicate project'} onSubmit={e=>{e.preventDefault();void act(async()=>{
      if(editing.mode==='rename')await updateProject(editing.project.id,editing.project.lock_version,{name:editName});
      else await duplicateProject(editing.project.id,editing.project.lock_version,editName);
      setEditing(null);
    });}} className="w-full max-w-md space-y-4 rounded-xl border border-slate-700 bg-slate-900 p-6">
      <label className="block">Project name<input autoFocus required maxLength={200} aria-label="Updated project name" value={editName} onChange={e=>setEditName(e.target.value)} className="mt-2 w-full rounded bg-slate-950 p-2"/></label>
      <div className="flex gap-3"><button disabled={busy||!editName.trim()} className="editor-tool">{editing.mode==='rename'?'Rename':'Duplicate'}</button><button type="button" disabled={busy} onClick={()=>setEditing(null)} className="editor-tool">Cancel</button></div>
    </form></div>}
  </main>;
}
