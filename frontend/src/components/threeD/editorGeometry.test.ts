import { describe, expect, it } from 'vitest';
import { PhysicalComponent } from '../../types/pdm';
import { analyzeEditorGeometry } from './editorGeometry';

function component(id: string, x: number, y: number, width = 20, height = 20): PhysicalComponent {
  return {
    id: `PDM-${id}`, cem_component_id: id, name: id, category: 'TEST',
    position: { x, y, z: 10 }, width, height, depth: 20, rotation_deg: 0, rail_id: 'RAIL-01',
    zone_name: 'TEST', heat_loss_watts: 0, cad_model: '', color_hex: '#ffffff', terminals: [],
  };
}

describe('3D editor geometry warnings', () => {
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
});
