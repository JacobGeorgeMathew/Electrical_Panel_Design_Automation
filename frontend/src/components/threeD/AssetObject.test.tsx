import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,expect,it,vi} from 'vitest';
const loader=vi.hoisted(()=>vi.fn());
vi.mock('@react-three/drei',()=>({useGLTF:loader,Clone:({scale}:{scale:number})=><div data-testid="cloned-asset">scale {scale}</div>,Html:({children}:{children:React.ReactNode})=><div>{children}</div>}));
import {AssetObject} from './AssetObject';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
afterEach(()=>{vi.restoreAllMocks();});
it('loads an application asset URL and displays a cloned scene',()=>{
  loader.mockReturnValue({scene:{}});
  const host=document.createElement('div'),root=createRoot(host);
  act(()=>root.render(<AssetObject url="http://127.0.0.1:8731/api/assets/a/content" scale={10}/>));
  expect(loader).toHaveBeenCalledWith('http://127.0.0.1:8731/api/assets/a/content');
  expect(host.textContent).toContain('scale 10');
  act(()=>root.unmount());
});
it('keeps a fallback visible when the GLB cannot be loaded',()=>{
  vi.spyOn(console,'error').mockImplementation(()=>{});
  loader.mockImplementation(()=>{throw new Error('asset unavailable');});
  const host=document.createElement('div'),root=createRoot(host);
  act(()=>root.render(<AssetObject url="/missing.glb" fallback={<span>Component bounds</span>}/>));
  expect(host.textContent).toContain('Component bounds');
  expect(host.textContent).toContain('3D asset unavailable');
  act(()=>root.unmount());
});
