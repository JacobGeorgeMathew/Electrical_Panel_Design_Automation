import {FolderOpen,Save,Undo2,Redo2,Play,MousePointer2,Move3D,Rotate3D,PackagePlus,Ruler,Layers,Box,ShieldCheck,PanelLeftClose,PanelRightClose,Maximize,Scan} from 'lucide-react';
import type {WorkspaceCommands} from './useWorkspaceCommands';
import {useWorkspaceStore} from '../../stores/workspaceStore';
import {useProjectStore} from '../../stores/projectStore';
export function WorkspaceToolbar({commands}:{commands:WorkspaceCommands}){
  const {tool,browserOpen,inspectorOpen}=useWorkspaceStore();
  const {isGenerating,wireVisibility,explodedView,editorSnapEnabled,editorGridMm,setEditorGridMm}=useProjectStore();
  const button=(id:keyof WorkspaceCommands,Icon:typeof Save,label?:string,pressed?:boolean)=><button title={commands[id].label+('shortcut' in commands[id]?` (${commands[id].shortcut})`:'')} aria-label={commands[id].label} aria-pressed={pressed} disabled={commands[id].disabled} onClick={commands[id].run} className={`toolbar-button ${pressed?'active':''} ${id==='generate'?'generate-button':''}`}><Icon size={16}/>{label&&<span>{label}</span>}</button>;
  return <div role="toolbar" aria-label="Design tools" className="workspace-toolbar">
    <div className="toolbar-group">{button('projects',FolderOpen)}{button('save',Save)}{button('undo',Undo2)}{button('redo',Redo2)}</div>
    <div className="toolbar-group">{button('generate',Play,isGenerating?'Generating…':'Generate')}</div>
    <div className="toolbar-group">{button('select',MousePointer2,'Select',tool==='select')}{button('move',Move3D,'Move',tool==='translate')}{button('rotate',Rotate3D,undefined,tool==='rotate')}{button('catalog',PackagePlus,'Components')}{button('measure',Ruler,undefined,tool==='measure')}</div>
    <div className="toolbar-group">{button('wires',Layers,undefined,wireVisibility)}{button('explode',Box,undefined,explodedView)}{button('snap',Scan,undefined,editorSnapEnabled)}<label className="toolbar-grid">Grid<input aria-label="Workspace snap grid" type="number" value={editorGridMm} min={1} max={100} onChange={e=>setEditorGridMm(Number(e.target.value))}/>mm</label></div>
    <div className="toolbar-group">{button('validate',ShieldCheck,'Validate')}</div>
    <div className="toolbar-group toolbar-panels">{button('browser',PanelLeftClose,undefined,browserOpen)}{button('inspector',PanelRightClose,undefined,inspectorOpen)}{button('fullscreen',Maximize)}</div>
  </div>;
}
