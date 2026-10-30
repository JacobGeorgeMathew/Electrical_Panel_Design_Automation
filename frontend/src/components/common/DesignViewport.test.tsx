import React,{act} from 'react';
import {createRoot,Root} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {DesignViewport} from './DesignViewport';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
let host:HTMLDivElement,root:Root;
const originalRequest=Object.getOwnPropertyDescriptor(HTMLElement.prototype,'requestFullscreen');
const originalElement=Object.getOwnPropertyDescriptor(document,'fullscreenElement');
const originalExit=Object.getOwnPropertyDescriptor(document,'exitFullscreen');
beforeEach(()=>{host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{
  act(()=>root.unmount());host.remove();document.body.style.overflow='';
  for(const [object,key,descriptor] of [[HTMLElement.prototype,'requestFullscreen',originalRequest],[document,'fullscreenElement',originalElement],[document,'exitFullscreen',originalExit]] as const){
    if(descriptor)Object.defineProperty(object,key,descriptor);else delete (object as any)[key];
  }
});

it('maximizes the actual canvas on native rejection and restores it with Escape',async()=>{
  Object.defineProperty(HTMLElement.prototype,'requestFullscreen',{configurable:true,value:vi.fn().mockRejectedValue(new Error('Unsupported'))});
  act(()=>root.render(<DesignViewport name="schematic"><svg data-testid="drawing"/></DesignViewport>));
  const drawing=host.querySelector('[data-testid="drawing"]');
  await act(async()=>{(host.querySelector('button') as HTMLButtonElement).click();});
  expect(host.querySelector('[aria-label="schematic canvas"]')?.getAttribute('data-expanded')).toBe('true');
  expect(host.querySelector('[data-testid="drawing"]')).toBe(drawing);
  expect(document.body.style.overflow).toBe('hidden');
  act(()=>document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true})));
  expect(host.querySelector('[data-expanded]')?.getAttribute('data-expanded')).toBe('false');
  expect(document.body.style.overflow).toBe('');
});

it('follows native fullscreen exit events and retains canvas identity',async()=>{
  let current:Element|null=null;
  Object.defineProperty(document,'fullscreenElement',{configurable:true,get:()=>current});
  Object.defineProperty(document,'exitFullscreen',{configurable:true,value:vi.fn(async()=>{current=null;document.dispatchEvent(new Event('fullscreenchange'));})});
  Object.defineProperty(HTMLElement.prototype,'requestFullscreen',{configurable:true,value:vi.fn(async function(this:HTMLElement){current=this;document.dispatchEvent(new Event('fullscreenchange'));})});
  act(()=>root.render(<DesignViewport name="3D panel"><canvas/></DesignViewport>));
  await act(async()=>{(host.querySelector('button') as HTMLButtonElement).click();});
  expect(current).toBe(host.firstElementChild);
  expect(host.querySelector('[data-expanded]')?.getAttribute('data-expanded')).toBe('true');
  act(()=>{current=null;document.dispatchEvent(new Event('fullscreenchange'));});
  expect(host.querySelector('[data-expanded]')?.getAttribute('data-expanded')).toBe('false');
});

it('allows a toolbar launcher to maximize a canvas even when its normal viewport is tiny',async()=>{
  Object.defineProperty(HTMLElement.prototype,'requestFullscreen',{configurable:true,value:undefined});
  function Viewer(){
    const ref=React.useRef<import('./DesignViewport').DesignViewportHandle>(null);
    return <><button aria-label="Launch fullscreen" onClick={()=>void ref.current?.enterFullscreen()}>Fullscreen</button><div style={{height:1}}><DesignViewport name="2D layout" controlRef={ref}><svg data-testid="tiny-drawing"/></DesignViewport></div></>;
  }
  act(()=>root.render(<Viewer/>));
  await act(async()=>{(host.querySelector('[aria-label="Launch fullscreen"]') as HTMLButtonElement).click();});
  expect(host.querySelector('[aria-label="2D layout canvas"]')?.getAttribute('data-expanded')).toBe('true');
  expect(host.querySelector('[aria-label="Exit fullscreen 2D layout"]')).not.toBeNull();
});
