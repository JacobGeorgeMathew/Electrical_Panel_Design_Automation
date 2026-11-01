import React,{act} from 'react';
import {createRoot,Root} from 'react-dom/client';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import * as THREE from 'three';
const context=vi.hoisted(()=>({current:null as any}));
vi.mock('@react-three/fiber',()=>({Canvas:()=>null,useThree:()=>context.current}));
vi.mock('@react-three/drei',()=>({OrbitControls:()=>null,Text:()=>null}));
import {ResponsiveCamera} from '../threeD/Panel3DViewer';
import {ViewportCameraControls} from './ViewportCameraControls';
import {useWorkspaceStore} from '../../stores/workspaceStore';
import {useProjectStore} from '../../stores/projectStore';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
let host:HTMLDivElement,root:Root;
beforeEach(()=>{
  host=document.createElement('div');root=createRoot(host);
  context.current={camera:new THREE.PerspectiveCamera(45,1.5,.01,1000),size:{width:900,height:600},controls:{target:new THREE.Vector3(),update:vi.fn()},invalidate:vi.fn()};
  useWorkspaceStore.setState({cameraPose:'isometric',cameraCommand:null});useProjectStore.setState({activeTab:'threeD'});
});
afterEach(()=>{act(()=>root.unmount());});
describe('viewport navigation',()=>{
  it('keeps zoom commands from resetting the camera and fits again on request',()=>{
    act(()=>root.render(<ResponsiveCamera width={6} height={8} depth={3}/>));
    const {camera,controls}=context.current;
    const original=camera.position.distanceTo(controls.target);
    act(()=>useWorkspaceStore.getState().camera('fit'));
    act(()=>useWorkspaceStore.getState().camera('zoom-in'));
    expect(camera.position.distanceTo(controls.target)).toBeCloseTo(original*.8);
    act(()=>useWorkspaceStore.getState().camera('zoom-out'));
    expect(camera.position.distanceTo(controls.target)).toBeCloseTo(original);
    act(()=>useWorkspaceStore.getState().setCameraPose('front'));
    expect(camera.position.x).toBe(3);expect(camera.position.y).toBe(4);
  });
  it('reframes from the actual canvas aspect after a panel resize',()=>{
    act(()=>root.render(<ResponsiveCamera width={6} height={8} depth={3}/>));
    const {camera,controls}=context.current,original=camera.position.distanceTo(controls.target);
    context.current.size={width:250,height:600};
    act(()=>root.render(<ResponsiveCamera width={6} height={8} depth={3}/>));
    expect(camera.position.distanceTo(controls.target)).toBeGreaterThan(original);
    expect(controls.target.toArray()).toEqual([3,4,1.5]);
  });
  it('does not replay a previous fullscreen request when changing views',()=>{
    const enterFullscreen=vi.fn(async()=>{}),ref={current:{enterFullscreen}};
    act(()=>root.render(<ViewportCameraControls view="threeD" viewportRef={ref}/>));
    act(()=>useWorkspaceStore.getState().camera('fullscreen'));
    expect(enterFullscreen).toHaveBeenCalledTimes(1);
    act(()=>useProjectStore.setState({activeTab:'layout2d'}));
    act(()=>useProjectStore.setState({activeTab:'threeD'}));
    expect(enterFullscreen).toHaveBeenCalledTimes(1);
  });
});
