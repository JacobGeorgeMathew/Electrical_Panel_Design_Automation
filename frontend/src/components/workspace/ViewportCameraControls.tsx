import {Scan,Plus,Minus} from 'lucide-react';
import {useEffect,type RefObject} from 'react';
import {useWorkspaceStore,type CameraPose} from '../../stores/workspaceStore';
import {useProjectStore} from '../../stores/projectStore';
import type {DesignViewportHandle} from '../common/DesignViewport';
export function ViewportCameraControls({view,viewportRef}:{view:'threeD'|'layout2d';viewportRef:RefObject<DesignViewportHandle>}){
  const {cameraPose,setCameraPose,camera}=useWorkspaceStore();
  useEffect(()=>useWorkspaceStore.subscribe((state,previous)=>{
    if(state.cameraCommand!==previous.cameraCommand&&useProjectStore.getState().activeTab===view&&state.cameraCommand?.action==='fullscreen')void viewportRef.current?.enterFullscreen();
  }),[view,viewportRef]);
  return <div role="toolbar" aria-label={`${view} camera controls`} className="camera-controls">
    <button aria-label="Fit design in viewport" title="Fit design (F)" onClick={()=>camera('fit')}><Scan size={13}/></button>
    <button aria-label="Zoom in design" onClick={()=>camera('zoom-in')}><Plus size={13}/></button>
    <button aria-label="Zoom out design" onClick={()=>camera('zoom-out')}><Minus size={13}/></button>
    {view==='threeD'&&<select aria-label="Camera orientation" value={cameraPose} onChange={e=>setCameraPose(e.target.value as CameraPose)}>{(['isometric','front','top','right'] as const).map(pose=><option key={pose} value={pose}>{pose[0].toUpperCase()+pose.slice(1)}</option>)}</select>}
  </div>;
}
