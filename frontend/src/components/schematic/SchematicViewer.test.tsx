import React,{act} from 'react';
import {createRoot,Root} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {useProjectStore} from '../../stores/projectStore';
const flow=vi.hoisted(()=>({zoomIn:vi.fn(),zoomOut:vi.fn(),fitView:vi.fn()}));
vi.mock('@xyflow/react',()=>({
 ReactFlowProvider:({children}:any)=><>{children}</>,ReactFlow:({children}:any)=><div>{children}</div>,
 useReactFlow:()=>flow,useNodesState:(initial:any)=>[initial,vi.fn(),vi.fn()],useEdgesState:(initial:any)=>[initial,vi.fn(),vi.fn()],
 Background:()=>null,MiniMap:()=>null,BaseEdge:()=>null,EdgeLabelRenderer:({children}:any)=><>{children}</>,Handle:()=>null,
 Position:{Top:'top',Bottom:'bottom'},getSmoothStepPath:()=>['M 0 0 L 10 10',0,0],addEdge:vi.fn(),
}));
import {SchematicViewer} from './SchematicViewer';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
let host:HTMLDivElement,root:Root;
beforeEach(()=>{host=document.createElement('div');document.body.append(host);root=createRoot(host);useProjectStore.setState({schematicData:{width:1200,height:700,symbols:[],wires:[]}});});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.clearAllMocks();});

it('keeps zoom and fit controls inside the canvas so they remain available in fullscreen',async()=>{
 act(()=>root.render(<SchematicViewer/>));
 const pane=host.querySelector('[aria-label="schematic canvas"]')!;
 const click=(label:string)=>act(()=>(pane.querySelector(`[aria-label="${label}"]`) as HTMLButtonElement).click());
 click('Zoom in schematic');expect(flow.zoomIn).toHaveBeenCalled();
 click('Zoom out schematic');expect(flow.zoomOut).toHaveBeenCalled();
 click('Fit schematic');expect(flow.fitView).toHaveBeenCalledWith(expect.objectContaining({minZoom:0.02}));
 await act(async()=>{(pane.querySelector('[aria-label="Fullscreen schematic"]') as HTMLButtonElement).click();});
 expect(pane.getAttribute('data-expanded')).toBe('true');
 expect(pane.querySelector('[aria-label="Zoom in schematic"]')).not.toBeNull();
});
