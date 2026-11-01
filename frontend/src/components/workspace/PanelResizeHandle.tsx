import {useRef,type PointerEvent} from 'react';
import {useWorkspaceStore,type WorkspacePanel} from '../../stores/workspaceStore';

export function PanelResizeHandle({panel}:{panel:WorkspacePanel}){
  const state=useWorkspaceStore();
  const start=useRef<{coordinate:number;size:number}|null>(null);
  const size=panel==='bottom'?state.bottomHeight:panel==='browser'?state.browserWidth:state.inspectorWidth;
  const resize=(next:number)=>state.resizePanel(panel,next,panel==='bottom'?window.innerHeight:window.innerWidth);
  const begin=(event:PointerEvent<HTMLDivElement>)=>{
    start.current={coordinate:panel==='bottom'?event.clientY:event.clientX,size};
    event.currentTarget.setPointerCapture?.(event.pointerId);event.preventDefault();
  };
  return <div role="separator" aria-label={`Resize ${panel} panel`} aria-orientation={panel==='bottom'?'horizontal':'vertical'}
    aria-valuenow={size} aria-valuemin={panel==='bottom'?80:panel==='browser'?144:192} aria-valuemax={panel==='bottom'?400:panel==='browser'?320:360}
    tabIndex={0} className={`workspace-splitter ${panel==='bottom'?'horizontal':'vertical'}`}
    onPointerDown={begin} onPointerMove={event=>{
      if(!start.current)return;
      const coordinate=panel==='bottom'?event.clientY:event.clientX;
      resize(start.current.size+(coordinate-start.current.coordinate)*(panel==='browser'?1:-1));
    }} onPointerUp={()=>{start.current=null;}} onPointerCancel={()=>{start.current=null;}}
    onKeyDown={event=>{
      if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){
        event.preventDefault();resize(size+(['ArrowRight','ArrowDown'].includes(event.key)?16:-16)*(panel==='browser'?1:-1));
      }
      if(event.key==='Home'){event.preventDefault();resize(0);}
    }}/>
}
