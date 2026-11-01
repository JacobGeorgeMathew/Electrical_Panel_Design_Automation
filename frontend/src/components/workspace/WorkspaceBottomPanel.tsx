import {ChevronDown,ChevronUp,AlertCircle,CheckCircle2,Loader2,Info} from 'lucide-react';
import {useProjectStore} from '../../stores/projectStore';
import {useWorkspaceStore} from '../../stores/workspaceStore';
import {WireInspector} from '../common/WireInspector';

export function WorkspaceBottomPanel(){
  const state=useProjectStore(),ui=useWorkspaceStore();
  const violations=state.pdm?.validation_results||[];
  const count=violations.length+state.validationErrors.length+state.validationWarnings.length+(state.errorMessage?1:0);
  return <section className="workspace-bottom" aria-label="Engineering console" style={{height:ui.bottomOpen?ui.bottomHeight:29}}>
    <div className="bottom-tabs" role="tablist" aria-label="Console tabs">
      {(['validation','output','engineering'] as const).map(tab=><button key={tab} role="tab" aria-selected={ui.bottomTab===tab&&ui.bottomOpen} onClick={()=>ui.setBottomTab(tab)}>{tab==='validation'?`Validation${count?` · ${count}`:''}`:tab==='output'?'Activity & errors':'Engineering information'}</button>)}
      {state.isGenerating&&<span className="generation-label"><Loader2 size={12} className="animate-spin"/>Generating design</span>}
      <button className="console-toggle" aria-label={ui.bottomOpen?'Collapse console':'Expand console'} onClick={()=>ui.togglePanel('bottom')}>{ui.bottomOpen?<ChevronDown size={14}/>:<ChevronUp size={14}/>}</button>
    </div>
    {ui.bottomOpen&&<div className="bottom-content" role="tabpanel" aria-label={`${ui.bottomTab} console`}>
      {ui.bottomTab==='validation'&&<>
        {state.errorMessage&&<div role="alert" className="console-row error"><AlertCircle size={13}/><span>{state.errorMessage}</span><button onClick={state.clearError}>Dismiss</button></div>}
        {state.validationErrors.map((message,i)=><div key={`error-${i}`} className="console-row error"><AlertCircle size={13}/>{message}</div>)}
        {state.validationWarnings.map((message,i)=><div key={`warning-${i}`} className="console-row warning"><Info size={13}/>{message}</div>)}
        {violations.map((v,i)=><button key={i} className={`console-row ${v.severity==='CRITICAL'?'error':'warning'}`} onClick={()=>{state.selectObject(v.object_a);state.setActiveTab('layout2d');}}><AlertCircle size={13}/><b>{v.type}</b><span>{v.message}</span><code>{v.object_a}</code></button>)}
        {!count&&<div className="console-row"><CheckCircle2 size={13}/>{state.pdm?'No violations reported by the implemented checks.':'Generate a design to obtain a physical validation report.'}</div>}
        {state.isValidatingPlacement&&<div className="console-row"><Loader2 size={13} className="animate-spin"/>Rerouting and validating placement draft…</div>}
      </>}
      {ui.bottomTab==='output'&&<>
        {state.isGenerating&&<div className="console-row"><progress aria-label="Design generation progress"/><span>Running requirements, electrical design, placement, routing and validation…</span></div>}
        {state.errorMessage&&<div role="alert" className="console-row error"><AlertCircle size={13}/>{state.errorMessage}</div>}
        <div className="console-row"><Info size={13}/>{state.autosaveStatus||'Ready. Save writes project inputs and editor drafts; Generate publishes an engineering revision.'}</div>
        <div className="console-row">CAD preview: {state.cadJobStatus||'No active job'} · {state.currentRevisionNo?`Active revision r${state.currentRevisionNo}`:'No published revision'}</div>
      </>}
      {ui.bottomTab==='engineering'&&<>
        <div className="console-row">Units: mm · Archetype: {state.archetype} · Components: {state.cem?.components.length||0} · Connections: {state.cem?.connections?.length||0} · Routes: {state.pdm?.routes.length||0}</div>
        {state.pdm&&<div className="console-row">Enclosure: {state.pdm.enclosure_width} × {state.pdm.enclosure_height} × {state.pdm.enclosure_depth} mm · Heat: {state.pdm.total_heat_loss_watts} W · Density: {state.pdm.thermal_density_index} W/L</div>}
        <WireInspector/>
        <div className="console-row muted">Placement and schematic edits are drafts. Catalog specifications and CEM connectivity remain authoritative.</div>
      </>}
    </div>}
  </section>;
}
