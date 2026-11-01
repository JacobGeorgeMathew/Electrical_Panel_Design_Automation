import { useEffect, useState } from 'react';
import { useProjectStore } from '../../stores/projectStore';

export function ProjectPersistenceBar() {
  const state=useProjectStore();
  const [revision,setRevision]=useState('');
  useEffect(()=>setRevision(state.currentRevisionId || ''),[state.currentRevisionId]);
  const busy=state.isLoadingProject || state.isGenerating || state.isSaving;
  return <div className="shrink-0 border-b border-slate-800 bg-slate-900 px-4 py-2 text-xs">
    <div className="flex flex-wrap items-center gap-2">
      <label className="text-slate-400">Project <select aria-label="Open saved project" value={state.projectId} disabled={busy}
        onChange={(e)=>e.target.value && state.openProject(e.target.value)} className="ml-2 max-w-64 rounded border border-slate-700 bg-slate-950 p-1.5 text-slate-200">
        <option value="">Select a saved project</option>
        {state.projects.map(p=><option key={p.id} value={p.id} disabled={p.archetype!=='DB'}>{p.name}{p.archetype!=='DB'?' (reference fixture)':''}</option>)}
      </select></label>
      <button onClick={state.saveCurrentProject} disabled={busy || !state.projectId || !state.hasUnsavedChanges || !!state.pendingRecovery} className="editor-tool disabled:opacity-40">{state.isSaving?'Saving…':'Save project'}</button>
      <button onClick={()=>void state.discardLocalEdits()} disabled={busy || !state.projectId || !state.hasUnsavedChanges} className="editor-tool disabled:opacity-40">Discard local edits</button>
      <button onClick={()=>void state.saveAndClose()} disabled={busy || !state.projectId || !!state.pendingRecovery} className="editor-tool disabled:opacity-40">Save & close</button>
      <button onClick={state.closeProject} disabled={busy || !state.projectId} className="editor-tool disabled:opacity-40">Close</button>
      <label className="ml-auto text-slate-400">Revision <select aria-label="Saved revisions" value={revision} onChange={e=>setRevision(e.target.value)} disabled={busy || !state.revisions.length}
        className="ml-2 rounded border border-slate-700 bg-slate-950 p-1.5 text-slate-200">
        <option value="">No saved design</option>
        {state.revisions.map(r=><option key={r.id} value={r.id}>r{r.revision_no} · {new Date(r.created_at).toLocaleString()}</option>)}
      </select></label>
      <button onClick={()=>state.restoreSavedRevision(revision)} disabled={busy || !revision || state.hasUnsavedChanges || !!state.pendingRecovery} className="editor-tool disabled:opacity-40">Restore as new revision</button>
      <span role="status" className={state.hasUnsavedChanges || state.designStale?'text-amber-300':'text-emerald-300'}>
        {state.isLoadingProject?'Opening project…':state.hasUnsavedChanges?'Unsaved local edits':state.designStale?'Requirements saved · design needs generation':state.currentRevisionNo?`Saved design r${state.currentRevisionNo}`:'No saved design yet'}
      </span>
    </div>
    {state.autosaveStatus&&<p role="status" className="mt-2 text-slate-400">{state.autosaveStatus}</p>}
    {state.pendingRecovery&&<div className="mt-2 rounded border border-amber-700 bg-amber-950 p-3" role="alert">
      Recover unsaved changes from {new Date(state.pendingRecovery.saved_at).toLocaleString()}?
      {state.pendingRecovery.base_version!==state.lockVersion&&' The saved project has changed since this checkpoint. Recovery keeps the saved revision and restores draft inputs.'}
      <button className="ml-3 underline" onClick={state.recoverChanges}>Recover changes</button>
      <button className="ml-3 underline" disabled={busy} onClick={()=>void state.discardRecovery()}>Discard recovery</button>
    </div>}
    {state.errorMessage && <div role="alert" className="mt-2 flex items-center gap-2 rounded border border-red-800 bg-red-950/50 px-3 py-2 text-red-200">
      <span className="flex-1">{state.errorMessage}</span>
      {!state.projectId && <button className="underline" onClick={state.initializeProjects}>Retry loading projects</button>}
      <button className="underline" onClick={state.clearError}>Dismiss</button>
    </div>}
  </div>;
}
