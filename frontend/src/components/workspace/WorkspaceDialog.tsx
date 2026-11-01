import {useEffect,useRef,type ReactNode} from 'react';
import {X} from 'lucide-react';
export function WorkspaceDialog({title,children,onClose}:{title:string;children:ReactNode;onClose:()=>void}){
  const host=useRef<HTMLDivElement>(null),close=useRef(onClose);close.current=onClose;
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null;
    host.current?.querySelector<HTMLElement>('button,input,select')?.focus();
    const key=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){event.stopPropagation();close.current();}
      if(event.key==='Tab'){
        const nodes=Array.from(host.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),[href]')||[]);
        const index=nodes.indexOf(document.activeElement as HTMLElement);
        if(event.shiftKey&&index<=0){event.preventDefault();nodes.at(-1)?.focus();}
        else if(!event.shiftKey&&index===nodes.length-1){event.preventDefault();nodes[0]?.focus();}
      }
    };
    document.addEventListener('keydown',key,true);
    return()=>{document.removeEventListener('keydown',key,true);previous?.focus();};
  },[]);
  return <div className="workspace-dialog-backdrop" onPointerDown={e=>{if(e.target===e.currentTarget)onClose();}}><div ref={host} role="dialog" aria-modal="true" aria-label={title} className="workspace-dialog"><header><h2>{title}</h2><button aria-label="Close dialog" onClick={onClose}><X size={18}/></button></header>{children}</div></div>;
}
