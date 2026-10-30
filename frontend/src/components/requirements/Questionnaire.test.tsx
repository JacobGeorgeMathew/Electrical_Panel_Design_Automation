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

it('uses supported numeric options and applies suggestions only when the user asks',async()=>{
  const questions=[
    {id:'num_feeders',label:'Number of Feeders',type:'number',default:12,options:[4,8,12,16],required:true,validation:{min:4,max:16},depends_on:[]},
    {id:'phases',label:'Phases',type:'number',default:3,options:[3],required:true,validation:{},depends_on:[]},
    {id:'spare_capacity_pct',label:'Spare',type:'number',default:20,options:[0,20,50],required:true,validation:{},depends_on:[]},
    {id:'incomer_rating',label:'Incomer Current Rating',type:'number',default:250,options:[100,250],unit:'A',required:true,validation:{},depends_on:[]}];
  useProjectStore.setState({requirementValues:{num_feeders:12,incomer_rating:250}});
  vi.stubGlobal('fetch',vi.fn(async(url:string,init?:RequestInit)=>{
    if(url.endsWith('/suggestions')){
      const values=JSON.parse(String(init?.body));return new Response(JSON.stringify({suggestions:{incomer_rating:{value:values.num_feeders===4?100:250,reason:'Estimated demand'}},estimates:{},assumptions:[]}));
    }
    return new Response(JSON.stringify(url.includes('/enclosures')?[]:questions));
  }));
  await act(async()=>{root.render(<Questionnaire/>);await new Promise(r=>setTimeout(r,0));});
  const rating=host.querySelector('[aria-label="Incomer Current Rating"]') as HTMLSelectElement;
  expect(rating.tagName).toBe('SELECT');expect(Array.from(rating.options,o=>o.value)).toEqual(['100','250']);
  expect(host.querySelector('input[aria-label="Incomer Current Rating"]')).toBeNull();
  const feeders=host.querySelector('[aria-label="Number of Feeders"]') as HTMLSelectElement;
  await act(async()=>{feeders.value='4';feeders.dispatchEvent(new Event('change',{bubbles:true}));});
  await act(async()=>{await new Promise(r=>setTimeout(r,260));});
  expect(useProjectStore.getState().requirementValues.incomer_rating).toBe(250);
  act(()=>(host.querySelector('[aria-label="Use suggested Incomer Current Rating"]') as HTMLButtonElement).click());
  expect(useProjectStore.getState().requirementValues.incomer_rating).toBe(100);
  act(()=>{rating.value='250';rating.dispatchEvent(new Event('change',{bubbles:true}));});
  expect(useProjectStore.getState().requirementValues.incomer_rating).toBe(250);
});
