import type { CanonicalEngineeringModel } from './cem';
import type { PhysicalDesignModel, ValidationViolation } from './pdm';

export interface Artifact {
  id: string; file_format: string; sha256: string | null; byte_size: number | null;
  status: string; type: string | null; project_revision_id: string | null; url: string | null;
  generator_name?: string; generator_version?: string; error?: { code: string; message: string } | null;
}
export interface ProjectConfiguration { enclosure_id?: string; enclosure_parameters?: Record<string, number>; }
export interface ProjectRecord {
  id: string; database_id: string; name: string; status: string; archetype: string; archetype_version_id: string;
  requirements: Record<string, any>; configuration: ProjectConfiguration; lock_version: number;
  current_revision_id: string | null; created_at: string;
}
export interface RevisionSummary { id: string; revision_no: number; parent_revision_id: string | null; created_at: string; status: string; content_sha256: string; }
export interface Question {
  id: string; question_id: string; label: string; type: string; unit?: string; default: any; options: any[] | null;
  required: boolean; depends_on: { field: string; operator: string; value: any }[]; validation: { min?: number; max?: number };
  help_text?: string;
}
export interface RequirementSuggestions {
  suggestions: Record<string,{value:number;reason:string}>;
  estimates: {phase_connected_current_a?:number[];estimated_max_phase_demand_a?:number;spare_feeder_spaces?:number;planning_total_feeder_spaces?:number};
  assumptions?:string[];message?:string;
}
export interface Archetype { id: string; code: string; name: string; version_id: string; version_no: number; supported: boolean; }
export interface CadParameter { code: string; value_type: string; unit_code: string | null; default_value: any; min_value: number | null; max_value: number | null; editable: boolean; derived: boolean; }
export interface CadModel { id: string; version_no: number; parameters: CadParameter[]; assets: Artifact[]; }
export interface CatalogComponent {
  id: string; code: string; name: string; category: string; component_version_id: string; version_no: number;
  current_rating: number; rated_voltage_v: number | null; breaking_capacity: number; poles: number;
  width: number; height: number; depth: number; mounting: string; manufacturer: string | null; sku: string | null;
  specification: Record<string, any>; terminals: Record<string, any>[]; cad_models?: CadModel[];
}
export interface CatalogPage { items: CatalogComponent[]; total: number; page: number; page_size: number; }
export interface Enclosure extends CatalogComponent { parameters: CadModel[]; mounting_plate_width: number; mounting_plate_height: number; }
export interface DesignPackage {
  cem: CanonicalEngineeringModel; pdm: PhysicalDesignModel; schematic: any; cad: any; bom: Record<string, any>[];
  validation_errors: ValidationViolation[]; revision_id: string; revision_no: number; lock_version: number;
  snapshot_sha256: string; manifest: Record<string, any>; artifacts: Artifact[]; is_stale: boolean;
}
