import { describe, expect, it } from 'vitest';
import fixture from './fixtures/document-v1.json';
import type { DocumentSave, DocumentView, ResolvedDocument, SchematicPresentation, WorkingDocument } from './document';

// JSON imports widen literal strings/numbers. Check the complete structural shape
// without a cast; literal compatibility is also checked on typed metadata below.
type JsonShape<T> = T extends string ? string : T extends number ? number
  : T extends (infer Item)[] ? JsonShape<Item>[]
  : T extends object ? { [Key in keyof T]: JsonShape<T[Key]> } : T;
const sharedFixture: JsonShape<ResolvedDocument> = fixture;
const reference = { schema_version: 1, sha256: 'a'.repeat(64) } as const;
const document: WorkingDocument = {
  schema_version: '1.0.0', document_id: 'document-1', project_id: 'project-1', panel_id: 'panel-1',
  archetype: 'DB', document_sequence: 7, lock_version: 3, base_revision_id: null,
  models: { requirements: reference, cem: null, pdm: null, schematic: null },
  configuration: {}, dirty_stages: ['routes', 'cad'], enclosure_interfaces: [],
  pins: { engine_version: 'db-pipeline-4', generator: { name: 'panelstudio-primitives', version: '3' },
    catalog_manifest_sha256: 'a'.repeat(64), validation_policy_version: 'strict-v1', catalog_versions: {}, model_versions: {} },
  provenance: { origin: 'MANUAL', actor_id: 'local-user', last_operation_id: null,
    source_revision_id: null, proposal_id: null, job_id: null },
};
const schematic: SchematicPresentation = {
  schema_version: '1.0.0', id: 'schematic-1', project_id: 'project-1', panel_id: 'panel-1', page_id: 'page-1',
  coordinate_system: 'schematic-mm-top-left', width_mm: 1200, height_mm: 1000,
  symbols: [{ id: 'symbol-1', component_id: 'QF001', position: { x: 100, y: 100 },
    width_mm: 100, height_mm: 70, rotation_deg: 0, label: '', pins: [{ id: 'pin-1', terminal_id: 'OUT',
      position: { x: 150, y: 170 }, direction: 'BOTTOM', label: '' }] }], wires: [],
};

describe('versioned document contract fixtures', () => {
  it('carries independent Save fences and input-only edits', () => {
    const view: JsonShape<DocumentView> = { ...fixture, content_sha256: 'a'.repeat(64) };
    const save: DocumentSave = {
      document_id: view.document.document_id, expected_version: view.document.lock_version,
      expected_document_sequence: view.document.document_sequence,
      requirements: { project_id: 'project-1', archetype: 'DB', items: [], is_valid: false,
        validation_errors: [], validation_warnings: [] }, configuration: {},
    };
    expect(JSON.parse(JSON.stringify(save))).toEqual(save);
    expect(save.expected_document_sequence).toBe(7);
    expect(save.expected_version).toBe(3);
  });
  it('preserves shared backend IDs, requirement states and enclosure mm on round trip', () => {
    expect(JSON.parse(JSON.stringify(sharedFixture))).toEqual(fixture);
    expect(fixture.snapshots.pdm.components[0].position).toEqual({ x: 125.5, y: 200.25, z: 37.5 });
    expect(fixture.snapshots.requirements.items[0].state).toBe('CONFIRMED');
    expect(fixture.snapshots.schematic.wires[0].conductor_id).toBe(fixture.snapshots.cem.connections[0].id);
  });
  it('type checks versioned metadata and presentation independently of net connectivity', () => {
    expect(JSON.parse(JSON.stringify(document))).toEqual(document);
    expect(schematic.symbols[0]).toEqual(fixture.snapshots.schematic.symbols[0]);
    expect(document.document_sequence).toBe(fixture.document.document_sequence);
  });
});
