import {useProjectStore} from '../../stores/projectStore';
import {useWorkspaceStore,type WorkspaceTool} from '../../stores/workspaceStore';
import {assetUrl,exportProject,fetchFreeCADScript} from '../../api/client';

export function downloadFile(data:Blob,name:string){
  const url=URL.createObjectURL(data),anchor=document.createElement('a');
  anchor.href=url;anchor.download=name;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export function useWorkspaceCommands(openDialog:(dialog:'project'|'help')=>void){
  const state=useProjectStore(),ui=useWorkspaceStore();
  const busy=state.isGenerating||state.isSaving||state.isLoadingProject||!!state.pendingRecovery;
  const tool=(value:WorkspaceTool)=>{
    ui.setTool(value);state.setEditorMode(value==='measure'?'select':value);
    if(value==='measure')useWorkspaceStore.setState({inspectorOpen:true});
  };
  const reportError=(error:unknown)=>{state.setError(error instanceof Error?error.message:String(error));ui.setBottomTab('output');};
  const run=async(action:()=>Promise<unknown>)=>{try{await action();}catch(error){reportError(error);}};
  const preview=state.artifacts.find(a=>a.file_format==='GLB'&&a.status==='READY');
  const commands={
    projects:{label:'Project dashboard…',shortcut:'',run:()=>{if(state.hasUnsavedChanges)openDialog('project');else state.closeProject();},disabled:busy},
    newProject:{label:'New project…',run:()=>{if(state.hasUnsavedChanges)openDialog('project');else state.closeProject();},disabled:busy},
    openProject:{label:'Open project…',run:()=>{if(state.hasUnsavedChanges)openDialog('project');else state.closeProject();},disabled:busy},
    save:{label:'Save project',shortcut:'Ctrl+S',run:()=>void state.saveCurrentProject(),disabled:busy||!state.hasUnsavedChanges},
    close:{label:'Save & close',run:()=>void state.saveAndClose(),disabled:busy},
    history:{label:'Project & revision history…',run:()=>openDialog('project'),disabled:false},
    undo:{label:'Undo placement',shortcut:'Ctrl+Z',run:()=>{state.undoEditorTransform();void state.validateCurrentPlacement();},disabled:busy||!state.editorUndoStack.length},
    redo:{label:'Redo placement',shortcut:'Ctrl+Shift+Z',run:()=>{state.redoEditorTransform();void state.validateCurrentPlacement();},disabled:busy||!state.editorRedoStack.length},
    deselect:{label:'Clear selection',shortcut:'Esc',run:()=>state.selectObject(null),disabled:!state.selectedObjectId},
    reset:{label:'Reset placement draft',run:state.resetEditorDraft,disabled:busy||!Object.keys(state.editorTransforms).length},
    browser:{label:ui.browserOpen?'Hide project browser':'Show project browser',run:()=>ui.togglePanel('browser'),disabled:false},
    inspector:{label:ui.inspectorOpen?'Hide properties':'Show properties',run:()=>ui.togglePanel('inspector'),disabled:false},
    bottom:{label:ui.bottomOpen?'Collapse bottom panel':'Expand bottom panel',run:()=>ui.togglePanel('bottom'),disabled:false},
    layout:{label:'Reset workspace layout',run:ui.resetLayout,disabled:false},
    fit:{label:'Fit design',shortcut:'F',run:()=>ui.camera('fit'),disabled:!['threeD','layout2d','schematic'].includes(state.activeTab)||(!state.pdm&&!state.schematicData)},
    fullscreen:{label:'Full-screen viewport',shortcut:'Shift+F',run:()=>ui.camera('fullscreen'),disabled:!['threeD','layout2d','schematic'].includes(state.activeTab)},
    generate:{label:'Generate design',run:()=>{ui.setBottomTab('output');void state.runDesignPipeline().then(()=>{const current=useProjectStore.getState();if(current.projectId===state.projectId&&!current.errorMessage&&current.pdm)current.setActiveTab('threeD');});},disabled:busy},
    requirements:{label:'Requirements',run:()=>state.setActiveTab('requirements'),disabled:false},
    catalog:{label:'Component library…',run:()=>state.setActiveTab('catalog'),disabled:false},
    select:{label:'Select',shortcut:'V',run:()=>tool('select'),disabled:busy},
    move:{label:'Move',shortcut:'M',run:()=>{if(!['threeD','layout2d'].includes(state.activeTab))state.setActiveTab('threeD');tool('translate');},disabled:busy||!state.pdm},
    rotate:{label:'Rotate',run:()=>{state.setActiveTab('threeD');tool('rotate');},disabled:busy||!state.pdm},
    measure:{label:'Measure',run:()=>tool(ui.tool==='measure'?'select':'measure'),disabled:!state.pdm},
    snap:{label:state.editorSnapEnabled?'Disable snapping':'Enable snapping',run:state.toggleEditorSnap,disabled:false},
    wires:{label:state.wireVisibility?'Hide wires':'Show wires',run:state.toggleWireVisibility,disabled:!state.pdm},
    explode:{label:state.explodedView?'Collapse assembly':'Explode assembly',run:()=>{state.setActiveTab('threeD');state.toggleExplodedView();},disabled:!state.pdm},
    validate:{label:'Validate placement',run:()=>{ui.setBottomTab('validation');void state.validateCurrentPlacement();},disabled:busy||!state.pdm||state.isValidatingPlacement},
    validateRequirements:{label:'Validate requirements',run:()=>{ui.setBottomTab('validation');void state.validateCurrentRequirements();},disabled:busy},
    report:{label:'Detailed validation report',run:()=>state.setActiveTab('validation'),disabled:!state.pdm},
    exportProject:{label:'Project package (saved)…',run:()=>void run(async()=>downloadFile(new Blob([JSON.stringify(await exportProject(state.projectId))],{type:'application/json'}),`panel-project-${state.projectId}.json`)),disabled:busy},
    exportGLB:{label:'Saved assembly · GLB',run:()=>{if(preview?.url){const a=document.createElement('a');a.href=assetUrl(preview.url);a.download='panel-assembly.glb';a.click();}},disabled:!preview?.url||state.designStale||state.hasUnsavedChanges},
    exportCAD:{label:'FreeCAD script…',run:()=>void run(async()=>{const result=await fetchFreeCADScript(state.projectId);downloadFile(new Blob([result.script],{type:'text/x-python'}),`panel-${state.projectId}.py`);}),disabled:!state.pdm||state.designStale||state.hasUnsavedChanges},
    help:{label:'Workspace help & shortcuts',run:()=>openDialog('help'),disabled:false},
    documentation:{label:'Project documentation',run:()=>state.setActiveTab('documentation'),disabled:false},
  };
  return commands;
}
export type WorkspaceCommands=ReturnType<typeof useWorkspaceCommands>;
