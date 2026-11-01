import {useEffect,useState,type CSSProperties} from 'react';
import {Box,Layers,GitBranch,FileSpreadsheet,Sliders,Package,BookOpen,ShieldCheck} from 'lucide-react';
import {useProjectStore,type ViewTab} from '../stores/projectStore';
import {useWorkspaceStore} from '../stores/workspaceStore';
import {Questionnaire} from '../components/requirements/Questionnaire';
import {SchematicViewer} from '../components/schematic/SchematicViewer';
import {Layout2DViewer} from '../components/layout/Layout2DViewer';
import {Panel3DViewer} from '../components/threeD/Panel3DViewer';
import {ValidationPanel} from '../components/validation/ValidationPanel';
import {BOMTable} from '../components/bom/BOMTable';
import {ChangePropagationModal} from '../components/common/ChangePropagationModal';
import {ProjectPersistenceBar} from '../components/projects/ProjectPersistenceBar';
import {CatalogBrowser} from '../components/catalog/CatalogBrowser';
import {WorkspaceMenuBar} from '../components/workspace/WorkspaceMenuBar';
import {WorkspaceToolbar} from '../components/workspace/WorkspaceToolbar';
import {ProjectBrowser} from '../components/workspace/ProjectBrowser';
import {PropertiesInspector} from '../components/workspace/PropertiesInspector';
import {WorkspaceBottomPanel} from '../components/workspace/WorkspaceBottomPanel';
import {PanelResizeHandle} from '../components/workspace/PanelResizeHandle';
import {WorkspaceDialog} from '../components/workspace/WorkspaceDialog';
import {useWorkspaceCommands} from '../components/workspace/useWorkspaceCommands';
import {assetUrl} from '../api/client';
import '../components/workspace/workspace.css';

const tabs:{id:ViewTab;label:string;icon:typeof Box}[]=[
  {id:'threeD',label:'3D Assembly',icon:Box},{id:'layout2d',label:'2D Physical Layout',icon:Layers},
  {id:'schematic',label:'Electrical Schematic',icon:GitBranch},{id:'bom',label:'BOM',icon:FileSpreadsheet},
  {id:'requirements',label:'Requirements',icon:Sliders},
];
export function ProjectPage(){
  const state=useProjectStore(),ui=useWorkspaceStore();
  const [dialog,setDialog]=useState<'project'|'help'|null>(null);
  const commands=useWorkspaceCommands(setDialog);
  useEffect(()=>{
    let previous=window.innerWidth;
    if(previous<1100)useWorkspaceStore.setState({inspectorOpen:false});
    if(previous<720)useWorkspaceStore.setState({browserOpen:false});
    const resize=()=>{
      const width=window.innerWidth;
      if(width<1100&&previous>=1100)useWorkspaceStore.setState({inspectorOpen:false});
      if(width<720&&previous>=720)useWorkspaceStore.setState({browserOpen:false});
      previous=width;
    };
    window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize);
  },[]);
  useEffect(()=>{
    const key=(event:KeyboardEvent)=>{
      const primary=event.ctrlKey||event.metaKey;
      const target=event.target as HTMLElement;
      if(target?.closest('[role="dialog"],[role="menu"]'))return;
      if(target?.closest('input,textarea,select,[contenteditable="true"]')&&!(primary&&event.key.toLowerCase()==='s'))return;
      const command=primary&&event.key.toLowerCase()==='s'?'save':primary&&event.key.toLowerCase()==='z'?(event.shiftKey?'redo':'undo'):primary&&event.key.toLowerCase()==='y'?'redo':!primary&&event.key.toLowerCase()==='f'?(event.shiftKey?'fullscreen':'fit'):!primary&&event.key.toLowerCase()==='v'?'select':!primary&&event.key.toLowerCase()==='m'?'move':null;
      if(command){event.preventDefault();if(!commands[command].disabled)commands[command].run();}
      if(event.key==='Escape'&&!document.fullscreenElement)state.selectObject(null);
    };
    document.addEventListener('keydown',key);return()=>document.removeEventListener('keydown',key);
  },[commands,state.selectObject]);
  useEffect(()=>{useWorkspaceStore.setState({measurement:[],tool:'select'});state.setEditorMode('select');},[state.projectId]);
  const extra=state.activeTab==='catalog'?{id:'catalog' as const,label:'Component Library',icon:Package}:state.activeTab==='documentation'?{id:'documentation' as const,label:'Documentation',icon:BookOpen}:state.activeTab==='validation'?{id:'validation' as const,label:'Validation Report',icon:ShieldCheck}:null;
  return <div className="engineering-workspace" style={{'--browser-width':`${ui.browserWidth}px`,'--inspector-width':`${ui.inspectorWidth}px`} as CSSProperties}>
    <WorkspaceMenuBar commands={commands}/><WorkspaceToolbar commands={commands}/>
    {state.pendingRecovery&&<div className="workspace-notice" role="alert">Recovery checkpoint available{state.pendingRecovery.base_version!==state.lockVersion?' from an earlier project version':''}.
      <button onClick={state.recoverChanges}>Recover changes</button><button disabled={state.isSaving} onClick={()=>void state.discardRecovery()}>Discard checkpoint</button></div>}
    <main className="workspace-body">
      {ui.browserOpen&&<><div className="browser-dock"><ProjectBrowser/></div><PanelResizeHandle panel="browser"/></>}
      <section className="workspace-center" aria-label="Design workspace">
        <div role="tablist" aria-label="Workspace views" className="workspace-tabs" onKeyDown={event=>{
          if(event.key==='ArrowLeft'||event.key==='ArrowRight'){
            const available=[...tabs,...(extra?[extra]:[])],index=available.findIndex(tab=>tab.id===state.activeTab);
            const next=available[(index+(event.key==='ArrowRight'?1:-1)+available.length)%available.length];
            event.preventDefault();state.setActiveTab(next.id);event.currentTarget.querySelector<HTMLButtonElement>(`[data-view="${next.id}"]`)?.focus();
          }
        }}>{[...tabs,...(extra?[extra]:[])].map(tab=><button key={tab.id} role="tab" id={`tab-${tab.id}`} data-view={tab.id} aria-controls="workspace-view" aria-selected={state.activeTab===tab.id} tabIndex={state.activeTab===tab.id?0:-1} onClick={()=>state.setActiveTab(tab.id)}><tab.icon size={14}/>{tab.label}</button>)}</div>
        <div id="workspace-view" role="tabpanel" aria-labelledby={`tab-${state.activeTab}`} className="workspace-canvas">
          {state.activeTab==='threeD'&&<Panel3DViewer embedded/>}
          {state.activeTab==='layout2d'&&<Layout2DViewer embedded/>}
          {state.activeTab==='schematic'&&<SchematicViewer embedded/>}
          {state.activeTab==='requirements'&&<Questionnaire/>}
          {state.activeTab==='bom'&&<div className="workspace-document-view"><BOMTable/></div>}
          {state.activeTab==='catalog'&&<div className="workspace-document-view"><CatalogBrowser/><p className="library-note">Inspect catalog parts here. To add electrical devices, configure Requirements and generate a new design. <button className="workspace-button" onClick={()=>state.setActiveTab('requirements')}>Configure component requirements</button></p></div>}
          {state.activeTab==='validation'&&<div className="workspace-document-view"><ValidationPanel/></div>}
          {state.activeTab==='documentation'&&<div className="workspace-document-view documentation-view"><h1>Project documentation</h1><p>{state.projectDescription||'No project description recorded.'}</p><dl><dt>Location</dt><dd>{state.projectLocation||'Unspecified'}</dd><dt>Project ID</dt><dd>{state.projectId}</dd><dt>Revision</dt><dd>{state.currentRevisionNo?`r${state.currentRevisionNo}`:'No generated revision'}</dd></dl><h2>Saved outputs</h2>{state.artifacts.length?state.artifacts.map(a=><p key={a.id}>{a.url&&a.status==='READY'?<a href={assetUrl(a.url)} download>{a.type||a.file_format} · {a.generator_version}</a>:<span>{a.file_format} · {a.status}</span>}</p>):<p>Generate a design to create engineering outputs.</p>}<h2>Working with designs</h2><p>Save stores project inputs and editor drafts. Generate runs the existing electrical and physical pipeline and publishes a new revision. Placement edits can be rerouted and validated, while exports continue to use the saved engineering revision.</p></div>}
        </div>
      </section>
      {ui.inspectorOpen&&<><PanelResizeHandle panel="inspector"/><div className="inspector-dock"><PropertiesInspector/></div></>}
    </main>
    {ui.bottomOpen&&<PanelResizeHandle panel="bottom"/>}<WorkspaceBottomPanel/>
    <footer className="workspace-statusbar"><span className={`save-state ${state.hasUnsavedChanges?'dirty':''}`}>{state.isSaving?'Saving…':state.hasUnsavedChanges?'● Unsaved draft':'● Saved'}</span><span>{state.designStale?'Engineering revision out of date':state.currentRevisionNo?`Active revision r${state.currentRevisionNo}`:'Empty engineering document'}</span><span className="status-selection">{state.selectedObjectId?`Selected: ${state.selectedObjectId}`:'No selection'}</span><span>mm</span><span>{state.archetype}</span></footer>
    {dialog&&<WorkspaceDialog title={dialog==='project'?'Project & revision history':'Workspace help'} onClose={()=>setDialog(null)}>{dialog==='project'?<ProjectPersistenceBar/>:<div className="workspace-help"><p>Use the browser to navigate the project and select components. The properties inspector follows selection across all views.</p><dl><dt>Ctrl / ⌘ S</dt><dd>Save project</dd><dt>Ctrl / ⌘ Z</dt><dd>Undo placement</dd><dt>Ctrl / ⌘ Shift Z</dt><dd>Redo placement</dd><dt>V / M</dt><dd>Select / Move</dd><dt>F / Shift F</dt><dd>Fit / Full-screen viewport</dd><dt>Esc</dt><dd>Exit full screen or clear selection</dd></dl><p>Drag panel dividers to resize, or focus a divider and use the arrow keys. Panel buttons in the toolbar collapse the browser and inspector. Measure selects two component centers.</p><p>Component specifications remain catalog-controlled. Save preserves placement and schematic drafts. Exports use the generated engineering revision.</p></div>}</WorkspaceDialog>}
    <ChangePropagationModal/>
  </div>;
}
