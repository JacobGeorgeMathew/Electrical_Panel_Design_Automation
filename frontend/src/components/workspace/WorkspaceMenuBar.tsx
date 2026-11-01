import {useEffect,useRef,useState} from 'react';
import {Bolt,ChevronDown} from 'lucide-react';
import {useProjectStore} from '../../stores/projectStore';
import type {WorkspaceCommands} from './useWorkspaceCommands';
const menus:Record<string,(keyof WorkspaceCommands)[]>={
  File:['newProject','openProject','projects','save','close','history','exportProject'],Edit:['undo','redo','deselect','reset'],
  View:['browser','inspector','bottom','fit','fullscreen','layout'],Design:['requirements','generate','catalog'],
  Tools:['select','move','rotate','measure','snap'],Validate:['validateRequirements','validate','report'],
  Export:['exportGLB','exportCAD','exportProject'],Help:['help','documentation'],
};
export function WorkspaceMenuBar({commands}:{commands:WorkspaceCommands}){
  const [active,setActive]=useState<string|null>(null),host=useRef<HTMLDivElement>(null);
  const {projectName,currentRevisionNo,hasUnsavedChanges}=useProjectStore();
  useEffect(()=>{
    const outside=(event:PointerEvent)=>{if(!host.current?.contains(event.target as Node))setActive(null);};
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'){setActive(null);host.current?.querySelector<HTMLButtonElement>('[aria-expanded="true"]')?.focus();}};
    document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);
    return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape);};
  },[]);
  return <div className="workspace-menubar" ref={host}>
    <div className="workspace-brand" title="Panel Studio"><Bolt size={17}/><span>PANEL<span className="brand-light">STUDIO</span></span></div>
    <div role="menubar" aria-label="Application menu" className="menu-items">
      {Object.entries(menus).map(([label,items])=><div className="menu-group" key={label}>
        <button role="menuitem" aria-haspopup="menu" aria-expanded={active===label} className={active===label?'open':''}
          onClick={()=>setActive(active===label?null:label)} onKeyDown={event=>{
            if(event.key==='ArrowDown'){event.preventDefault();setActive(label);requestAnimationFrame(()=>host.current?.querySelector<HTMLButtonElement>('[role="menu"] button:not(:disabled)')?.focus());}
            if(event.key==='ArrowLeft'||event.key==='ArrowRight'){
              event.preventDefault();const all=Array.from(host.current!.querySelectorAll<HTMLButtonElement>('[aria-haspopup="menu"]'));
              all[(all.indexOf(event.currentTarget)+(event.key==='ArrowRight'?1:-1)+all.length)%all.length]?.focus();
            }
          }}>{label}<ChevronDown size={9}/></button>
        {active===label&&<div role="menu" aria-label={`${label} menu`} className="workspace-menu" onKeyDown={event=>{
          if(event.key==='ArrowDown'||event.key==='ArrowUp'){
            event.preventDefault();const buttons=Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
            buttons[(buttons.indexOf(document.activeElement as HTMLButtonElement)+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();
          }
        }}>{items.map(id=>{const command=commands[id];return <button role="menuitem" disabled={command.disabled} key={id} onClick={()=>{setActive(null);command.run();}}><span>{command.label}</span><kbd>{'shortcut' in command?command.shortcut:''}</kbd></button>;})}</div>}
      </div>)}
    </div>
    <div className="workspace-document" title={projectName}>{hasUnsavedChanges&&<span className="unsaved-dot"/>}{projectName}<span>{currentRevisionNo?`r${currentRevisionNo}`:'New project'}</span></div>
  </div>;
}
