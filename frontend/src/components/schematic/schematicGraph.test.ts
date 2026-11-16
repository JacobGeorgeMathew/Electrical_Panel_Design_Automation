import { describe, expect, it } from 'vitest';
import { buildSchematicGraph, documentSchematicGraph, validateSchematicGraph, type SchematicGraphData } from './schematicGraph';
import fixture from '../../types/fixtures/document-v1.json';
import type {DocumentView} from '../../types/document';

it('projects typed page IDs and CEM conductors without changing any snapshot',()=>{
  const view={...structuredClone(fixture),content_sha256:'a'.repeat(64)} as DocumentView;
  const before=structuredClone(view);
  const graph=buildSchematicGraph(documentSchematicGraph(view)!);
  expect(graph.nodes[0]).toMatchObject({id:'symbol-1',position:{x:100,y:100}});
  expect(graph.nodes[0].data.terminals[0].id).toBe('pin-1');
  expect(graph.edges[0]).toMatchObject({id:'wire-1',source:'symbol-1',sourceHandle:'source:pin-1',target:'symbol-2',targetHandle:'target:pin-2',data:{conductor_id:'N-PE-C01'}});
  expect(view).toEqual(before);
});

const graphFixture: SchematicGraphData = {
  width: 400, height: 300,
  symbols: [
    { id: 'QF001', name: 'Incomer', type: 'MCCB', category: 'MCCB', x: 100, y: 20, width: 60, height: 80, label: 'QF001\n250A', terminals: [{ id: 'OUT', x: 130, y: 100 }] },
    { id: 'BUS001', name: 'Busbar', type: 'BUSBAR', category: 'BUSBAR', x: 20, y: 150, width: 240, height: 20, label: 'Main busbar', terminals: [{ id: 'IN', x: 140, y: 150 }] },
    { id: 'QF002', name: 'Feeder A', type: 'MCB', category: 'MCB', x: 300, y: 150, width: 40, height: 60, label: 'QF002', terminals: [{ id: 'IN', x: 320, y: 150 }] },
  ],
  wires: [
    { id: 'CONN-01', net_id: 'NET-L1', net_name: 'L1', from: 'QF001', from_terminal: 'OUT', to: 'BUS001', to_terminal: 'IN', wire_class: 'POWER' },
    { id: 'CONN-02', net_id: 'NET-L1', net_name: 'L1', from: 'BUS001', from_terminal: 'IN', to: 'QF002', to_terminal: 'IN', wire_class: 'POWER' },
  ],
};

describe('schematic graph mapping and rules', () => {
  it('preserves backend topology and never invents junctions for fan-out', () => {
    const result=buildSchematicGraph(graphFixture);
    expect(result.nodes.map(n=>n.id)).toEqual(graphFixture.symbols.map(s=>s.id));
    expect(result.edges.map(e=>e.id)).toEqual(['CONN-01','CONN-02']);
    expect(result.edges[0].sourceHandle).toBe('source:OUT');
    expect(validateSchematicGraph(result.nodes,result.edges)).toEqual([]);
    const path='M 130 100 L 130 125 L 140 125 L 140 150';
    const routed=buildSchematicGraph({...graphFixture,wires:[{...graphFixture.wires[0],svg_path:path,waypoints:[{x:130,y:100},{x:130,y:125},{x:140,y:125},{x:140,y:150}]}]});
    expect(routed.edges[0].data?.svg_path).toBe(path);
    expect(routed.nodes[0].style).toEqual({width:60,height:80});
  });

  it('reports invalid terminal references, missing labels, and mixed-class rule violations', () => {
    const result = buildSchematicGraph(graphFixture);
    const edge = { ...result.edges[0], sourceHandle: 'source:MISSING', data: { ...result.edges[0].data!, net_name: '' } };
    const errors = validateSchematicGraph(result.nodes, [edge]);
    expect(errors.map((error) => error.code)).toContain('MISSING_TERMINAL');
    expect(errors.map((error) => error.code)).toContain('MISSING_NET');
  });
});
