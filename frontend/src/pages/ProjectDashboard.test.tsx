import React,{act} from 'react';
import {createRoot,Root} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
const api=vi.hoisted(()=>({listProjects:vi.fn(),duplicateProject:vi.fn(),deleteProject:vi.fn(),updateProject:vi.fn()}));
vi.mock('../api/client',async original=>({...await original<typeof import('../api/client')>(),...api}));
import {ProjectDashboard} from './ProjectDashboard';
import {useProjectStore} from '../stores/projectStore';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
let host:HTMLDivElement,root:Root;
const project={id:'p',database_id:'p',name:'Factory',description:'Workshop',location:'Kochi',archetype:'DB',lock_version:2,last_opened_at:null};
beforeEach(()=>{
  vi.clearAllMocks();vi.useFakeTimers();host=document.createElement('div');document.body.append(host);root=createRoot(host);
  api.listProjects.mockResolvedValue([project]);
  useProjectStore.setState({archetypes:[{code:'DB',name:'Distribution Board',supported:true,version_id:'v'}] as any,isSaving:false,isLoadingProject:false,errorMessage:null});
});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.useRealTimers();vi.restoreAllMocks();});
const button=(text:string)=>Array.from(host.querySelectorAll('button')).find(b=>b.textContent===text)!;
const input=(label:string,value:string)=>{
  const element=host.querySelector(`[aria-label="${label}"]`) as HTMLInputElement;
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(element,value);
  element.dispatchEvent(new Event('input',{bubbles:true}));
};
it('creates a project with metadata and offers saved projects without opening one automatically',async()=>{
  const create=vi.fn();useProjectStore.setState({createNewProject:create});
  act(()=>root.render(<ProjectDashboard/>));
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  expect(host.textContent).toContain('Factory');
  act(()=>{input('Project name','New panel');input('Location','Site A');});
  await act(async()=>{host.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));});
  expect(create).toHaveBeenCalledWith('New panel','DB','v',{description:'',location:'Site A'});
});
it('duplicates and deletes with the current project version',async()=>{
  act(()=>root.render(<ProjectDashboard/>));
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  act(()=>button('duplicate').click());
  await act(async()=>{host.querySelector('[role="dialog"]')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));});
  expect(api.duplicateProject).toHaveBeenCalledWith('p',2,'Factory copy');
  await act(async()=>{await vi.advanceTimersByTimeAsync(250);});
  vi.spyOn(window,'confirm').mockReturnValue(true);
  await act(async()=>button('Delete').click());
  expect(api.deleteProject).toHaveBeenCalledWith('p',2);
});
