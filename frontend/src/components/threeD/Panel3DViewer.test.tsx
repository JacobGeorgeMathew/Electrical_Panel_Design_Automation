import React from 'react';
import { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const threeState = vi.hoisted(() => ({
  camera: {
    position: { set: vi.fn() },
    lookAt: vi.fn(),
    near: 0,
    far: 0,
    updateProjectionMatrix: vi.fn(),
  },
  size: { width: 900, height: 600 },
}));

vi.mock('@react-three/fiber', () => ({
  Canvas: ({ className }: { className?: string }) => <div data-testid="three-canvas" className={className} />,
  useThree: () => threeState,
}));
vi.mock('@react-three/drei', () => ({ OrbitControls: () => null, Line: () => null, Text: () => null, Html: () => null }));

import { Panel3DViewer, ResponsiveCamera } from './Panel3DViewer';
import { useProjectStore } from '../../stores/projectStore';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

describe('Panel3DViewer sizing', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    threeState.size.width = 900;
    threeState.size.height = 600;
    threeState.camera.position.set.mockClear();
    threeState.camera.lookAt.mockClear();
    host = document.createElement('div');
    document.body.append(host);
    root = createRoot(host);
    useProjectStore.setState({
      pdm: { enclosure_width: 600, enclosure_height: 800, enclosure_depth: 300, rails: [], components: [{
        id: 'PDM-QF001', cem_component_id: 'QF001', name: 'Feeder breaker', category: 'MCB',
        position: { x: 20, y: 30, z: 10 }, width: 20, height: 45, depth: 35, rotation_deg: 0,
        rail_id: 'RAIL-01', zone_name: 'DISTRIBUTION', heat_loss_watts: 1, cad_model: 'demo', color_hex: '#3B82F6', terminals: [],
      }], routes: [], mounting_plate_x: 0, mounting_plate_y: 0, mounting_plate_z: 0 } as any,
      selectedObjectId: null, hoveredObjectId: null, explodedView: false, wireVisibility: true,
      toggleExplodedView: vi.fn(), toggleWireVisibility: vi.fn(),
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    host.remove();
  });

  it('lets the viewer and canvas fill the available flex viewport without a fixed-height cap', () => {
    act(() => root.render(<Panel3DViewer />));
    const viewer = host.firstElementChild as HTMLElement;
    const canvas = host.querySelector('[data-testid="three-canvas"]') as HTMLElement;
    expect(viewer.className).toContain('flex-1');
    expect(viewer.className).toContain('min-h-0');
    expect(canvas.className).toContain('w-full');
    expect(canvas.className).toContain('h-full');
  });

  it('reframes the camera when the measured viewport size changes', () => {
    act(() => root.render(<ResponsiveCamera width={6} height={8} depth={3} />));
    const firstPosition = threeState.camera.position.set.mock.calls[0];

    threeState.size.width = 300;
    threeState.size.height = 600;
    act(() => root.render(<ResponsiveCamera width={6} height={8} depth={3} />));

    const resizedPosition = threeState.camera.position.set.mock.calls[1];
    expect(resizedPosition).toBeDefined();
    expect(resizedPosition).not.toEqual(firstPosition);
  });

  it('selects parts from the component tree and exposes numeric properties and visibility', () => {
    act(() => root.render(<Panel3DViewer />));
    const treeButton = Array.from(host.querySelectorAll('button')).find((button) => button.textContent?.includes('Feeder breaker'))!;
    act(() => treeButton.click());
    expect(useProjectStore.getState().selectedObjectId).toBe('QF001');
    expect(host.querySelector('[aria-label="Position X in millimeters"]')).not.toBeNull();
    expect(host.querySelector('[aria-label="Rotation Z in degrees"]')).not.toBeNull();

    act(() => host.querySelector('[aria-label="Hide QF001"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(useProjectStore.getState().editorHiddenComponentIds).toContain('QF001');
  });

  it('opens the door, removes covers and inspects persisted duct fill',()=>{
    useProjectStore.setState({pdm:{...useProjectStore.getState().pdm!,ducts:[{
      id:'DUCT-LEFT',label:'Left vertical wiring duct',x:20,y:20,z:30,width:40,height:700,depth:60,
      catalog_id:'WIRE_DUCT_40_60',orientation:'VERTICAL',wall_mm:2,capacity_pct:12.5,max_fill_pct:40,
      wire_area_mm2:250,usable_area_mm2:2000,route_ids:['R1','R2']
    }],accessories:[{id:'DOOR',catalog_id:'PANEL_DOOR_STEEL',name:'Hinged steel door',category:'DOOR',
      parent_id:'ENCLOSURE',position:{x:3,y:3,z:303},width:594,height:794,depth:18,material:'Steel',color_hex:'#CBD5E1',parameters:{}}]}});
    act(()=>root.render(<Panel3DViewer/>));
    const button=(text:string)=>Array.from(host.querySelectorAll('button')).find(b=>b.textContent?.includes(text))!;
    expect(button('Close door').getAttribute('aria-pressed')).toBe('true');
    act(()=>button('Close door').click());
    expect(button('Open door').getAttribute('aria-pressed')).toBe('false');
    act(()=>button('Fit duct covers').click());
    expect(button('Remove duct covers').getAttribute('aria-pressed')).toBe('true');
    act(()=>button('Left vertical wiring duct').click());
    expect(useProjectStore.getState().selectedObjectId).toBe('DUCT-LEFT');
    expect(host.querySelector('[aria-label="Properties inspector"]')?.textContent).toContain('12.5% / 40%');
  });
});
