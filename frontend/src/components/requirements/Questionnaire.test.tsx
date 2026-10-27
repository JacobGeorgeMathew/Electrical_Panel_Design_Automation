import React,{act} from 'react';
import {createRoot,Root} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {Questionnaire} from './Questionnaire';
import {useProjectStore} from '../../stores/projectStore';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
let host:HTMLDivElement,root:Root;
beforeEach(()=>{host=document.createElement('div');document.body.append(host);root=createRoot(host);useProjectStore.setState({projectId:'P1',archetypes:[],isGenerating:false,isSaving:false,isLoadingProject:false,errorMessage:null,requirementValues:{},projectConfiguration:{}});});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();});

it('renders server ranges and evaluates conditional questions against server defaults',async()=>{
  const questions=[{id:'phases',label:'Supply phases',type:'number',default:3,required:true,validation:{min:1,max:3},depends_on:[]},
    {id:'neutral_required',label:'Neutral bar',type:'boolean',default:true,required:true,validation:{},depends_on:[{field:'phases',operator:'equals',value:3}]}];
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>new Response(JSON.stringify(url.includes('/enclosures')?[]:questions))));
  await act(async()=>{root.render(<Questionnaire/>);await new Promise(r=>setTimeout(r,0));});
  expect(host.textContent).toContain('Neutral bar');
  expect(host.querySelector('[aria-label="Supply phases"]')?.getAttribute('max')).toBe('3');
});
