import {create} from 'zustand';
import {persist} from 'zustand/middleware';

export type WorkspacePanel = 'browser' | 'inspector' | 'bottom';
export type CameraAction = 'fit' | 'zoom-in' | 'zoom-out' | 'fullscreen';
export type CameraPose = 'isometric' | 'front' | 'top' | 'right';
export type WorkspaceTool = 'select' | 'translate' | 'rotate' | 'measure';
interface WorkspaceState {
  browserOpen: boolean; inspectorOpen: boolean; bottomOpen: boolean;
  browserWidth: number; inspectorWidth: number; bottomHeight: number;
  bottomTab: 'validation' | 'output' | 'engineering';
  tool: WorkspaceTool; cameraPose: CameraPose;
  cameraCommand: {action:CameraAction;sequence:number} | null;
  measurement: string[];
  togglePanel: (panel:WorkspacePanel)=>void;
  resizePanel: (panel:WorkspacePanel,size:number,available:number)=>void;
  setBottomTab: (tab:WorkspaceState['bottomTab'])=>void;
  setTool: (tool:WorkspaceTool)=>void;
  setCameraPose: (pose:CameraPose)=>void;
  camera: (action:CameraAction)=>void;
  measure: (id:string)=>void;
  resetLayout: ()=>void;
}
const layout={browserOpen:true,inspectorOpen:true,bottomOpen:true,browserWidth:180,inspectorWidth:224,bottomHeight:128};
export function panelSize(panel:WorkspacePanel,size:number,available:number){
  const min=panel==='bottom'?80:panel==='browser'?144:192;
  const max=panel==='bottom'?Math.min(400,available*.45):Math.min(panel==='browser'?320:360,available*.3);
  return Math.round(Math.max(min,Math.min(Number.isFinite(size)?size:min,Math.max(min,max))));
}
export const useWorkspaceStore=create<WorkspaceState>()(persist((set)=>({
  ...layout,bottomTab:'validation',tool:'select',cameraPose:'isometric',cameraCommand:null,measurement:[],
  togglePanel:panel=>set(state=>({[`${panel}Open`]:!state[`${panel}Open`]})),
  resizePanel:(panel,size,available)=>set({[panel==='bottom'?'bottomHeight':`${panel}Width`]:panelSize(panel,size,available)}),
  setBottomTab:bottomTab=>set({bottomTab,bottomOpen:true}),
  setTool:tool=>set({tool,measurement:[]}),
  setCameraPose:cameraPose=>set({cameraPose}),
  camera:action=>set(state=>({cameraCommand:{action,sequence:(state.cameraCommand?.sequence||0)+1}})),
  measure:id=>set(state=>({measurement:state.measurement.includes(id)?state.measurement:state.measurement.length===2?[id]:[...state.measurement,id]})),
  resetLayout:()=>set(layout),
}),{name:'panelstudio-workspace-v1',partialize:state=>({browserOpen:state.browserOpen,inspectorOpen:state.inspectorOpen,
  bottomOpen:state.bottomOpen,browserWidth:state.browserWidth,inspectorWidth:state.inspectorWidth,bottomHeight:state.bottomHeight})}));
