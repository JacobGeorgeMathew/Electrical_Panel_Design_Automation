import {useEffect,useRef,useState,useImperativeHandle,type ReactNode,type Ref} from 'react';
import {Maximize,Minimize} from 'lucide-react';

/** Maximize the actual canvas. CSS fallback also supports embedded/Tauri views. */
export type DesignViewportHandle={enterFullscreen:()=>Promise<void>};
export function DesignViewport({name,children,onExpandedChange,controlRef}:{name:string;children:ReactNode;onExpandedChange?:(expanded:boolean)=>void;controlRef?:Ref<DesignViewportHandle>}){
  const host=useRef<HTMLDivElement>(null);
  const button=useRef<HTMLButtonElement>(null);
  const native=useRef(false);
  const [expanded,setExpanded]=useState(false);
  const change=useRef(onExpandedChange);change.current=onExpandedChange;
  const exit=()=>{
    if(document.fullscreenElement===host.current)void document.exitFullscreen?.().catch(()=>{});
    native.current=false;setExpanded(false);button.current?.focus();
  };
  useEffect(()=>{
    const element=host.current;
    const fullscreen=()=>{if(native.current&&document.fullscreenElement!==element){native.current=false;setExpanded(false);button.current?.focus();}};
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();exit();}};
    if(expanded)document.addEventListener('keydown',escape);
    document.addEventListener('fullscreenchange',fullscreen);
    const previous=document.body.style.overflow;
    if(expanded)document.body.style.overflow='hidden';
    change.current?.(expanded);
    return()=>{
      document.removeEventListener('keydown',escape);document.removeEventListener('fullscreenchange',fullscreen);
      if(expanded)document.body.style.overflow=previous;
    };
  },[expanded]);
  useEffect(()=>{
    const element=host.current;
    return()=>{if(document.fullscreenElement===element)void document.exitFullscreen?.().catch(()=>{});};
  },[]);
  const enter=async()=>{
    setExpanded(true);
    if(host.current?.requestFullscreen){
      try{await host.current.requestFullscreen();native.current=true;}
      catch{native.current=false;} // Keep the maximized in-app canvas.
    }
  };
  useImperativeHandle(controlRef,()=>({enterFullscreen:enter}));
  return <div ref={host} role="region" aria-label={`${name} canvas`} data-expanded={expanded}
    className={`design-viewport bg-slate-950 ${expanded?'fixed inset-0 z-[100] h-dvh w-screen':'relative h-full w-full min-h-0'}`}>
    <div className="absolute right-3 top-3 z-30"><button ref={button} type="button" aria-label={`${expanded?'Exit fullscreen':'Fullscreen'} ${name}`} aria-pressed={expanded}
      onClick={()=>expanded?exit():void enter()} className="editor-tool bg-slate-950/95 shadow-lg">
      {expanded?<Minimize className="h-4 w-4"/>:<Maximize className="h-4 w-4"/>}{expanded?'Exit fullscreen':'Fullscreen'}
    </button></div>
    {children}
    {expanded&&<div className="pointer-events-none absolute bottom-2 right-3 z-20 rounded bg-slate-950/90 px-2 py-1 text-xs text-slate-400">Esc to exit fullscreen</div>}
  </div>;
}
