import { describe, expect, it } from 'vitest';
import { PhysicalComponent } from '../../types/pdm';
import { analyzeEditorGeometry, transformFromGizmo } from './editorGeometry';

function component(id: string, x: number, y: number, width = 20, height = 20): PhysicalComponent {
  return {
    id: `PDM-${id}`, cem_component_id: id, name: id, category: 'TEST',
    position: { x, y, z: 10 }, width, height, depth: 20, rotation_deg: 0, rail_id: 'RAIL-01',
    zone_name: 'TEST', heat_loss_watts: 0, cad_model: '', color_hex: '#ffffff', terminals: [],
  };
}

describe('3D editor geometry warnings', () => {
  it('converts centered exploded gizmos to enclosure mm and preserves untouched off-grid axes',()=>{
    const part={...component('A',125.5,200.25),width:18,height:80,depth:70};
    const current={x:125.5,y:200.25,z:37.5,rotation_deg:0};
    const world={x:(141.3+9)*.01,y:(200.25+40)*.01,z:(37.5+35)*.01+.8};
    expect(transformFromGizmo(part,current,world,.8,true,5)).toEqual({x:140,y:200.25,z:37.5,rotation_deg:0});
    expect(transformFromGizmo(part,current,world,.8,false,5).x).toBeCloseTo(141.3);
  });
  const enclosure = { width: 100, height: 100, depth: 60 };

  it('flags draft overlaps and out-of-enclosure transforms', () => {
    const components = [component('A', 10, 10), component('B', 40, 10), component('C', 70, 70)];
    const warnings = analyzeEditorGeometry(components, {
      A: { x: 35, y: 10, z: 10, rotation_deg: 0 },
      C: { x: 90, y: 90, z: 10, rotation_deg: 0 },
    }, enclosure);
    expect(warnings.some((warning) => warning.type === 'COLLISION')).toBe(true);
    expect(warnings.some((warning) => warning.type === 'BOUNDARY' && warning.componentIds.includes('C'))).toBe(true);
  });

  it('uses the configured prototype DIN rail gap for clearance warnings', () => {
    const warnings = analyzeEditorGeometry([component('A', 10, 10), component('B', 32, 10)], {}, enclosure);
    expect(warnings.some((warning) => warning.type === 'CLEARANCE')).toBe(true);
  });

  it('enforces four millimetres for the reported terminal pair and accepts the generated gap',()=>{
    const a={...component('X001',10,10,8.2,48),category:'TERMINAL'};
    const b={...component('X002',20,10,8.2,48),category:'TERMINAL'};
    const policy={version:'strict-v1',din_clearance_mm:4,plate_clearance_mm:20,wire_clearance_mm:5,thermal_density_limit_w_per_l:.45};
    expect(analyzeEditorGeometry([a,b],{},enclosure,policy).some(w=>w.type==='CLEARANCE')).toBe(true);
    expect(analyzeEditorGeometry([a,{...b,position:{...b.position,x:25}}],{},enclosure,policy)).toEqual([]);
  });

  it('treats edge contact as a clearance failure rather than an overlapping footprint',()=>{
    const warnings=analyzeEditorGeometry([component('A',10,10),component('B',30,10)],{},enclosure);
    expect(warnings.some(w=>w.type==='CLEARANCE')).toBe(true);
    expect(warnings.some(w=>w.type==='COLLISION')).toBe(false);
  });

  it('reads the saved policy rather than using a different editor threshold',()=>{
    const policy={version:'custom',din_clearance_mm:8,plate_clearance_mm:25,wire_clearance_mm:5,thermal_density_limit_w_per_l:.45};
    expect(analyzeEditorGeometry([component('A',10,10),component('B',36,10)],{},enclosure,policy).some(w=>w.type==='CLEARANCE')).toBe(true);
  });
});
