import React from 'react';
import { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Layout2DViewer } from './Layout2DViewer';
import { useProjectStore } from '../../stores/projectStore';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

describe('2D layout viewport fit', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.append(host);
    root = createRoot(host);
    const pdm = {
      id: 'PDM-01', project_id: 'PROJ-01', panel_id: 'DB-01', enclosure_id: 'ENC-01', ip_rating: 'IP54',
      enclosure_width: 800, enclosure_height: 1000, enclosure_depth: 300,
      mounting_plate_x: 20, mounting_plate_y: 20, mounting_plate_width: 760, mounting_plate_height: 960,
      mounting_plate_z: 0, zones: [], components: [{ id: 'PDM-QF001', cem_component_id: 'QF001', name: 'Feeder breaker',
        category: 'MCB', position: { x: 100, y: 150, z: 20 }, width: 20, height: 45, depth: 35, rotation_deg: 0,
        rail_id: 'RAIL-01', zone_name: 'DISTRIBUTION', heat_loss_watts: 1, cad_model: 'demo', color_hex: '#3B82F6', terminals: [] }],
      rails: [], routes: [], validation_results: [], total_heat_loss_watts: 1, thermal_density_index: 0,
    };
    useProjectStore.setState({ pdm: pdm as any, pdmBaseline: pdm as any, editorTransforms: {}, selectedObjectId: null });
  });

  afterEach(() => {
    act(() => root.unmount());
    host.remove();
    vi.unstubAllGlobals();
  });

  it('scales the whole enclosure drawing into the available viewport', () => {
    act(() => root.render(<Layout2DViewer />));
    const canvas = host.querySelector('svg[viewBox="0 0 800 1000"]') as SVGSVGElement;
    expect(canvas.getAttribute('width')).toBe('100%');
    expect(canvas.getAttribute('height')).toBe('100%');
    expect(canvas.getAttribute('viewBox')).toBe('0 0 800 1000');
    expect(canvas.getAttribute('preserveAspectRatio')).toBe('xMidYMid meet');
    expect(canvas.parentElement?.className).toContain('min-h-0');
  });

  it('writes aligned placement to the PDM and sends it to the existing validator', async () => {
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const sentPdm = JSON.parse(String(init.body));
      return { ok: true, json: async () => ({ pdm: sentPdm, validation_results: [], is_valid: true }) } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    act(() => root.render(<Layout2DViewer />));
    const component = host.querySelector('[aria-label="Move QF001"]') as SVGGElement;
    act(() => component.dispatchEvent(new MouseEvent('click', { bubbles: true })));
    const alignLeft = Array.from(host.querySelectorAll('button')).find((button) => button.textContent?.includes('Align left'))!;
    await act(async () => {
      alignLeft.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(useProjectStore.getState().editorTransforms.QF001.x).toBe(20);
    expect(useProjectStore.getState().pdm?.components[0].position.x).toBe(20);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body)).components[0].position.x).toBe(20);
  });
});
