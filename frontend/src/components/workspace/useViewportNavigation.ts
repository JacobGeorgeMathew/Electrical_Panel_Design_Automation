import {useEffect,useState,type WheelEvent} from 'react';
import {useWorkspaceStore} from '../../stores/workspaceStore';
import {useProjectStore} from '../../stores/projectStore';

export function useViewportNavigation(){
  const [zoom,setZoom]=useState(1);
  const revision=useProjectStore(state=>state.currentRevisionId);
  useEffect(()=>{setZoom(1);},[revision]);
  useEffect(()=>useWorkspaceStore.subscribe((state,previous)=>{
    const command=state.cameraCommand;
    if(command===previous.cameraCommand||useProjectStore.getState().activeTab!=='layout2d'||!command)return;
    if(command.action==='fit')setZoom(1);
    if(command.action==='zoom-in')setZoom(z=>Math.min(8,z*1.2));
    if(command.action==='zoom-out')setZoom(z=>Math.max(.25,z/1.2));
  }),[]);
  return {viewBox:(width:number,height:number)=>`${(width-width/zoom)/2} ${(height-height/zoom)/2} ${width/zoom} ${height/zoom}`,
    onWheel:(event:WheelEvent)=>{if(event.ctrlKey){event.preventDefault();setZoom(z=>Math.max(.25,Math.min(8,z*(event.deltaY<0?1.1:1/1.1))));}}};
}
