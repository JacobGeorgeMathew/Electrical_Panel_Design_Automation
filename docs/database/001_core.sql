-- PostgreSQL 15+. Immutable published versions and project revisions are enforced
-- by repository policy (and production DB roles); this file provides structural checks.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE manufacturers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE,
  name text NOT NULL, website text, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (name)
);
CREATE TABLE product_families (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), manufacturer_id uuid REFERENCES manufacturers(id) ON DELETE RESTRICT,
  code text NOT NULL, name text NOT NULL, description text,
  UNIQUE (manufacturer_id, code)
);
CREATE TABLE components (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE,
  name text NOT NULL, category_code text NOT NULL, component_kind text NOT NULL,
  lifecycle_status text NOT NULL DEFAULT 'ACTIVE' CHECK (lifecycle_status IN ('ACTIVE','OBSOLETE','DRAFT')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE component_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), component_id uuid NOT NULL REFERENCES components(id) ON DELETE RESTRICT,
  version_no integer NOT NULL CHECK (version_no > 0), schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version > 0),
  status text NOT NULL CHECK (status IN ('DRAFT','PUBLISHED','WITHDRAWN')),
  rated_voltage_v numeric CHECK (rated_voltage_v IS NULL OR rated_voltage_v >= 0),
  rated_current_a numeric CHECK (rated_current_a IS NULL OR rated_current_a >= 0),
  breaking_capacity_ka numeric CHECK (breaking_capacity_ka IS NULL OR breaking_capacity_ka >= 0),
  pole_count smallint CHECK (pole_count IS NULL OR pole_count > 0),
  width_mm numeric CHECK (width_mm IS NULL OR width_mm >= 0), height_mm numeric CHECK (height_mm IS NULL OR height_mm >= 0),
  depth_mm numeric CHECK (depth_mm IS NULL OR depth_mm >= 0), mass_kg numeric CHECK (mass_kg IS NULL OR mass_kg >= 0),
  specification jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(specification) = 'object'),
  valid_from timestamptz, created_at timestamptz NOT NULL DEFAULT now(), created_by text,
  UNIQUE(component_id, version_no)
);
-- Category is on components; this composite index supports common selector filters.
CREATE INDEX ix_component_catalog_category ON components(category_code, component_kind);
CREATE INDEX ix_component_version_rating ON component_versions(rated_current_a, rated_voltage_v, breaking_capacity_ka);
CREATE TABLE products (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), manufacturer_id uuid NOT NULL REFERENCES manufacturers(id) ON DELETE RESTRICT,
  family_id uuid REFERENCES product_families(id) ON DELETE RESTRICT, manufacturer_sku text NOT NULL,
  display_name text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(manufacturer_id, manufacturer_sku)
);
CREATE TABLE product_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), product_id uuid NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  component_version_id uuid NOT NULL REFERENCES component_versions(id) ON DELETE RESTRICT,
  version_no integer NOT NULL CHECK(version_no > 0), status text NOT NULL CHECK(status IN ('DRAFT','PUBLISHED','WITHDRAWN')),
  lifecycle_status text NOT NULL DEFAULT 'AVAILABLE' CHECK(lifecycle_status IN ('AVAILABLE','LIMITED','DISCONTINUED','UNKNOWN')),
  datasheet_uri text, specification jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(specification)='object'),
  created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(product_id, version_no)
);
CREATE INDEX ix_product_versions_component ON product_versions(component_version_id, status);
CREATE TABLE component_terminals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), component_version_id uuid NOT NULL REFERENCES component_versions(id) ON DELETE RESTRICT,
  code text NOT NULL, terminal_kind text NOT NULL, electrical_role text, connection_type text,
  conductor_min_mm2 numeric CHECK(conductor_min_mm2 IS NULL OR conductor_min_mm2 >= 0),
  conductor_max_mm2 numeric CHECK(conductor_max_mm2 IS NULL OR conductor_max_mm2 >= conductor_min_mm2),
  coordinate_mm jsonb CHECK(coordinate_mm IS NULL OR jsonb_typeof(coordinate_mm)='object'), orientation jsonb,
  UNIQUE(component_version_id, code)
);
CREATE INDEX ix_terminal_component_role ON component_terminals(component_version_id, electrical_role);
CREATE TABLE component_mounting (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), component_version_id uuid NOT NULL REFERENCES component_versions(id) ON DELETE RESTRICT,
  mounting_code text NOT NULL, footprint_asset_hint text, mounting_parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(component_version_id, mounting_code)
);
CREATE TABLE component_accessories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), component_version_id uuid NOT NULL REFERENCES component_versions(id) ON DELETE RESTRICT,
  accessory_component_version_id uuid NOT NULL REFERENCES component_versions(id) ON DELETE RESTRICT,
  relation_code text NOT NULL DEFAULT 'COMPATIBLE', constraints jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(component_version_id, accessory_component_version_id, relation_code), CHECK(component_version_id <> accessory_component_version_id)
);
CREATE TABLE component_clearances (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), component_version_id uuid NOT NULL REFERENCES component_versions(id) ON DELETE RESTRICT,
  direction_code text NOT NULL, distance_mm numeric NOT NULL CHECK(distance_mm >= 0), provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(component_version_id, direction_code)
);
CREATE TABLE component_thermal_specs (
  component_version_id uuid PRIMARY KEY REFERENCES component_versions(id) ON DELETE RESTRICT,
  heat_loss_w numeric CHECK(heat_loss_w IS NULL OR heat_loss_w >= 0), operating_temperature_min_c numeric,
  operating_temperature_max_c numeric CHECK(operating_temperature_max_c IS NULL OR operating_temperature_min_c IS NULL OR operating_temperature_max_c >= operating_temperature_min_c),
  details jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE component_documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), component_version_id uuid NOT NULL REFERENCES component_versions(id) ON DELETE RESTRICT,
  document_type text NOT NULL, title text NOT NULL, uri text, asset_hash char(64), language_code text,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb, CHECK(asset_hash IS NULL OR asset_hash ~ '^[0-9a-f]{64}$')
);

CREATE TABLE cad_models (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE, name text NOT NULL,
  model_kind text NOT NULL CHECK(model_kind IN ('PART','ASSEMBLY','ACCESSORY')), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE cad_model_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), cad_model_id uuid NOT NULL REFERENCES cad_models(id) ON DELETE RESTRICT,
  version_no integer NOT NULL CHECK(version_no > 0), status text NOT NULL CHECK(status IN ('DRAFT','PUBLISHED','WITHDRAWN')),
  coordinate_system jsonb NOT NULL DEFAULT '{"handedness":"right","length_unit":"mm"}'::jsonb,
  feature_definition jsonb NOT NULL DEFAULT '{}'::jsonb, generator_name text, generator_version text,
  dependency_manifest jsonb NOT NULL DEFAULT '[]'::jsonb, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(cad_model_id, version_no)
);
CREATE TABLE cad_parameter_definitions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), cad_model_version_id uuid NOT NULL REFERENCES cad_model_versions(id) ON DELETE RESTRICT,
  code text NOT NULL, value_type text NOT NULL CHECK(value_type IN ('STRING','INTEGER','DECIMAL','BOOLEAN','ENUM','OBJECT')),
  unit_code text, default_value jsonb, min_value numeric, max_value numeric, allowed_values jsonb,
  editable boolean NOT NULL DEFAULT true, derived boolean NOT NULL DEFAULT false, expression text,
  dependencies text[] NOT NULL DEFAULT '{}', description text,
  UNIQUE(cad_model_version_id, code), CHECK(min_value IS NULL OR max_value IS NULL OR max_value >= min_value),
  CHECK(NOT (editable AND derived))
);
CREATE TABLE cad_features (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), cad_model_version_id uuid NOT NULL REFERENCES cad_model_versions(id) ON DELETE RESTRICT,
  code text NOT NULL, sequence_no integer NOT NULL CHECK(sequence_no >= 0), operation_code text NOT NULL,
  feature_definition jsonb NOT NULL, depends_on_codes text[] NOT NULL DEFAULT '{}',
  UNIQUE(cad_model_version_id, code), UNIQUE(cad_model_version_id, sequence_no)
);
CREATE TABLE cad_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), cad_model_version_id uuid NOT NULL REFERENCES cad_model_versions(id) ON DELETE RESTRICT,
  asset_role text NOT NULL, file_format text NOT NULL CHECK(file_format IN ('FCSTD','STEP','STP','GLB','GLTF','JSON','OTHER')),
  storage_backend text NOT NULL DEFAULT 'LOCAL', storage_key text NOT NULL, sha256 char(64) NOT NULL,
  byte_size bigint NOT NULL CHECK(byte_size >= 0), media_type text, source_asset_id uuid REFERENCES cad_assets(id) ON DELETE RESTRICT,
  generator_name text, generator_version text, generation_status text NOT NULL DEFAULT 'READY' CHECK(generation_status IN ('PENDING','READY','FAILED','MISSING','CORRUPT')),
  created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(storage_backend, storage_key), CHECK(sha256 ~ '^[0-9a-f]{64}$')
);
CREATE INDEX ix_cad_assets_version_role ON cad_assets(cad_model_version_id, asset_role);
CREATE TABLE component_cad_models (
  component_version_id uuid NOT NULL REFERENCES component_versions(id) ON DELETE RESTRICT,
  cad_model_version_id uuid NOT NULL REFERENCES cad_model_versions(id) ON DELETE RESTRICT,
  representation_role text NOT NULL DEFAULT 'PRIMARY', PRIMARY KEY(component_version_id, cad_model_version_id, representation_role)
);
CREATE TABLE cad_assemblies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE, name text NOT NULL
);
CREATE TABLE cad_assembly_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), assembly_id uuid NOT NULL REFERENCES cad_assemblies(id) ON DELETE RESTRICT,
  version_no integer NOT NULL CHECK(version_no > 0), status text NOT NULL CHECK(status IN ('DRAFT','PUBLISHED','WITHDRAWN')),
  UNIQUE(assembly_id, version_no)
);
CREATE TABLE cad_assembly_members (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), assembly_version_id uuid NOT NULL REFERENCES cad_assembly_versions(id) ON DELETE RESTRICT,
  member_cad_model_version_id uuid NOT NULL REFERENCES cad_model_versions(id) ON DELETE RESTRICT,
  member_code text NOT NULL, quantity integer NOT NULL DEFAULT 1 CHECK(quantity > 0), transform jsonb NOT NULL,
  parameter_defaults jsonb NOT NULL DEFAULT '{}'::jsonb, UNIQUE(assembly_version_id, member_code)
);

CREATE TABLE panel_archetypes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE, name text NOT NULL, description text
);
CREATE TABLE panel_archetype_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), archetype_id uuid NOT NULL REFERENCES panel_archetypes(id) ON DELETE RESTRICT,
  version_no integer NOT NULL CHECK(version_no > 0), status text NOT NULL CHECK(status IN ('DRAFT','PUBLISHED','WITHDRAWN')),
  defaults jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(archetype_id, version_no)
);
CREATE TABLE functional_modules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE, name text NOT NULL, description text
);
CREATE TABLE functional_module_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), module_id uuid NOT NULL REFERENCES functional_modules(id) ON DELETE RESTRICT,
  version_no integer NOT NULL CHECK(version_no > 0), status text NOT NULL CHECK(status IN ('DRAFT','PUBLISHED','WITHDRAWN')),
  UNIQUE(module_id, version_no)
);
CREATE TABLE archetype_modules (
  archetype_version_id uuid NOT NULL REFERENCES panel_archetype_versions(id) ON DELETE RESTRICT,
  module_version_id uuid NOT NULL REFERENCES functional_module_versions(id) ON DELETE RESTRICT,
  sequence_no integer NOT NULL DEFAULT 0, required boolean NOT NULL DEFAULT true, configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY(archetype_version_id, module_version_id)
);
CREATE TABLE module_role_requirements (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), module_version_id uuid NOT NULL REFERENCES functional_module_versions(id) ON DELETE RESTRICT,
  role_code text NOT NULL, quantity_min integer NOT NULL DEFAULT 1 CHECK(quantity_min >= 0), quantity_max integer,
  required_properties jsonb NOT NULL DEFAULT '{}'::jsonb, selection_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK(quantity_max IS NULL OR quantity_max >= quantity_min), UNIQUE(module_version_id, role_code)
);
CREATE TABLE archetype_defaults (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), archetype_version_id uuid NOT NULL REFERENCES panel_archetype_versions(id) ON DELETE RESTRICT,
  code text NOT NULL, value jsonb NOT NULL, unit_code text, UNIQUE(archetype_version_id, code)
);
CREATE TABLE electrical_templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE, name text NOT NULL
);
CREATE TABLE electrical_template_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), template_id uuid NOT NULL REFERENCES electrical_templates(id) ON DELETE RESTRICT,
  version_no integer NOT NULL CHECK(version_no > 0), status text NOT NULL CHECK(status IN ('DRAFT','PUBLISHED','WITHDRAWN')),
  validation_rules jsonb NOT NULL DEFAULT '[]'::jsonb, UNIQUE(template_id, version_no)
);
CREATE TABLE archetype_electrical_templates (
  archetype_version_id uuid NOT NULL REFERENCES panel_archetype_versions(id) ON DELETE RESTRICT,
  template_version_id uuid NOT NULL REFERENCES electrical_template_versions(id) ON DELETE RESTRICT,
  sequence_no integer NOT NULL DEFAULT 0, required boolean NOT NULL DEFAULT true,
  PRIMARY KEY(archetype_version_id, template_version_id)
);
CREATE TABLE template_component_roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), template_version_id uuid NOT NULL REFERENCES electrical_template_versions(id) ON DELETE RESTRICT,
  role_code text NOT NULL, component_category text, required_properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(template_version_id, role_code)
);
CREATE TABLE template_terminals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), template_role_id uuid NOT NULL REFERENCES template_component_roles(id) ON DELETE RESTRICT,
  terminal_code text NOT NULL, terminal_role text, UNIQUE(template_role_id, terminal_code)
);
CREATE TABLE template_connections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), template_version_id uuid NOT NULL REFERENCES electrical_template_versions(id) ON DELETE RESTRICT,
  from_template_terminal_id uuid NOT NULL REFERENCES template_terminals(id) ON DELETE RESTRICT,
  to_template_terminal_id uuid NOT NULL REFERENCES template_terminals(id) ON DELETE RESTRICT,
  connection_code text NOT NULL, connection_type text NOT NULL, directionality text NOT NULL DEFAULT 'UNDIRECTED' CHECK(directionality IN ('DIRECTED','UNDIRECTED')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb, UNIQUE(template_version_id, connection_code), CHECK(from_template_terminal_id <> to_template_terminal_id)
);

CREATE TABLE questionnaires (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE, name text NOT NULL
);
CREATE TABLE questionnaire_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), questionnaire_id uuid NOT NULL REFERENCES questionnaires(id) ON DELETE RESTRICT,
  version_no integer NOT NULL CHECK(version_no > 0), status text NOT NULL CHECK(status IN ('DRAFT','PUBLISHED','WITHDRAWN')),
  schema_version integer NOT NULL DEFAULT 1, UNIQUE(questionnaire_id, version_no)
);
CREATE TABLE questionnaire_sections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), questionnaire_version_id uuid NOT NULL REFERENCES questionnaire_versions(id) ON DELETE RESTRICT,
  code text NOT NULL, title text NOT NULL, sequence_no integer NOT NULL DEFAULT 0, UNIQUE(questionnaire_version_id, code)
);
CREATE TABLE questions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), questionnaire_version_id uuid NOT NULL REFERENCES questionnaire_versions(id) ON DELETE RESTRICT,
  section_id uuid REFERENCES questionnaire_sections(id) ON DELETE RESTRICT, code text NOT NULL, prompt text NOT NULL,
  value_type text NOT NULL CHECK(value_type IN ('TEXT','INTEGER','DECIMAL','BOOLEAN','SINGLE_SELECT','MULTI_SELECT','QUANTITY','MEASUREMENT','OBJECT')),
  unit_code text, required boolean NOT NULL DEFAULT false, sequence_no integer NOT NULL DEFAULT 0,
  validation jsonb NOT NULL DEFAULT '{}'::jsonb, UNIQUE(questionnaire_version_id, code)
);
CREATE TABLE question_options (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), question_id uuid NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
  option_code text NOT NULL, label text NOT NULL, value jsonb NOT NULL, sequence_no integer NOT NULL DEFAULT 0,
  UNIQUE(question_id, option_code)
);
CREATE TABLE question_dependencies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), question_id uuid NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
  depends_on_question_id uuid NOT NULL REFERENCES questions(id) ON DELETE RESTRICT, operator_code text NOT NULL,
  expected_value jsonb NOT NULL, CHECK(question_id <> depends_on_question_id), UNIQUE(question_id, depends_on_question_id)
);
CREATE TABLE question_validation_rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), question_id uuid NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
  rule_code text NOT NULL, parameters jsonb NOT NULL DEFAULT '{}'::jsonb, message text, UNIQUE(question_id, rule_code)
);
CREATE TABLE archetype_questionnaires (
  archetype_version_id uuid NOT NULL REFERENCES panel_archetype_versions(id) ON DELETE RESTRICT,
  questionnaire_version_id uuid NOT NULL REFERENCES questionnaire_versions(id) ON DELETE RESTRICT,
  sequence_no integer NOT NULL DEFAULT 0, PRIMARY KEY(archetype_version_id, questionnaire_version_id)
);

CREATE TABLE rule_sets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE, name text NOT NULL
);
CREATE TABLE rule_set_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), rule_set_id uuid NOT NULL REFERENCES rule_sets(id) ON DELETE RESTRICT,
  version_no integer NOT NULL CHECK(version_no > 0), status text NOT NULL CHECK(status IN ('DRAFT','PUBLISHED','WITHDRAWN')),
  UNIQUE(rule_set_id, version_no)
);
CREATE TABLE design_rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE, name text NOT NULL, engine_handler text NOT NULL
);
CREATE TABLE design_rule_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), rule_id uuid NOT NULL REFERENCES design_rules(id) ON DELETE RESTRICT,
  version_no integer NOT NULL CHECK(version_no > 0), status text NOT NULL CHECK(status IN ('DRAFT','PUBLISHED','WITHDRAWN')),
  severity text NOT NULL CHECK(severity IN ('INFO','WARNING','ERROR')), hardness text NOT NULL CHECK(hardness IN ('HARD','SOFT')),
  priority integer NOT NULL DEFAULT 100, parameters jsonb NOT NULL DEFAULT '{}'::jsonb, provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(rule_id, version_no)
);
CREATE TABLE rule_set_members (
  rule_set_version_id uuid NOT NULL REFERENCES rule_set_versions(id) ON DELETE RESTRICT,
  rule_version_id uuid NOT NULL REFERENCES design_rule_versions(id) ON DELETE RESTRICT,
  enabled boolean NOT NULL DEFAULT true, PRIMARY KEY(rule_set_version_id, rule_version_id)
);
CREATE TABLE rule_applicability (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), rule_version_id uuid NOT NULL REFERENCES design_rule_versions(id) ON DELETE RESTRICT,
  target_kind text NOT NULL, predicate jsonb NOT NULL DEFAULT '{}'::jsonb, UNIQUE(rule_version_id, target_kind)
);

CREATE TABLE projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_code text UNIQUE, name text NOT NULL,
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','ARCHIVED','CLOSED')),
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), created_by text
);
CREATE TABLE project_revisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  revision_no integer NOT NULL CHECK(revision_no > 0), parent_revision_id uuid REFERENCES project_revisions(id) ON DELETE RESTRICT,
  status text NOT NULL CHECK(status IN ('DRAFT','PUBLISHED','SUPERSEDED')),
  archetype_version_id uuid REFERENCES panel_archetype_versions(id) ON DELETE RESTRICT,
  rule_set_version_id uuid REFERENCES rule_set_versions(id) ON DELETE RESTRICT,
  questionnaire_version_ids uuid[] NOT NULL DEFAULT '{}', model_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  schema_version integer NOT NULL DEFAULT 1, content_sha256 char(64), created_at timestamptz NOT NULL DEFAULT now(), created_by text,
  UNIQUE(project_id, revision_no), UNIQUE(project_id, id), CHECK(content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$')
);
CREATE INDEX ix_project_revision_latest ON project_revisions(project_id, revision_no DESC);
CREATE TABLE questionnaire_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  questionnaire_version_id uuid NOT NULL REFERENCES questionnaire_versions(id) ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'IN_PROGRESS' CHECK(status IN ('IN_PROGRESS','SUBMITTED','SUPERSEDED')),
  created_at timestamptz NOT NULL DEFAULT now(), submitted_at timestamptz
);
CREATE TABLE question_answers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), session_id uuid NOT NULL REFERENCES questionnaire_sessions(id) ON DELETE RESTRICT,
  question_id uuid NOT NULL REFERENCES questions(id) ON DELETE RESTRICT, answer_value jsonb NOT NULL,
  answered_at timestamptz NOT NULL DEFAULT now(), actor_id text, UNIQUE(session_id, question_id)
);
CREATE TABLE project_requirements (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  project_revision_id uuid REFERENCES project_revisions(id) ON DELETE RESTRICT, code text NOT NULL,
  operator_code text NOT NULL CHECK(operator_code IN ('EQ','MIN','MAX','RANGE','IN','NOT_IN','QUANTITY')),
  value jsonb NOT NULL, unit_code text, resolution_status text NOT NULL DEFAULT 'UNRESOLVED' CHECK(resolution_status IN ('UNRESOLVED','RESOLVED','CONFLICT','WAIVED')),
  created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(project_revision_id, code)
);
CREATE TABLE requirement_sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), requirement_id uuid NOT NULL REFERENCES project_requirements(id) ON DELETE RESTRICT,
  source_kind text NOT NULL CHECK(source_kind IN ('ANSWER','MANUFACTURER','ENGINEER','RULE','OPTIMIZER','IMPORT')),
  question_answer_id uuid REFERENCES question_answers(id) ON DELETE RESTRICT, source_ref text, details jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK(source_kind <> 'ANSWER' OR question_answer_id IS NOT NULL)
);
CREATE TABLE requirement_role_mappings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), requirement_code text NOT NULL, role_code text NOT NULL,
  mapping_operator text NOT NULL, mapping jsonb NOT NULL DEFAULT '{}'::jsonb, UNIQUE(requirement_code, role_code)
);

CREATE TABLE revision_components (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  component_version_id uuid REFERENCES component_versions(id) ON DELETE RESTRICT,
  product_version_id uuid REFERENCES product_versions(id) ON DELETE RESTRICT, role_code text NOT NULL,
  selected_by text NOT NULL CHECK(selected_by IN ('ENGINEER','SELECTOR','TEMPLATE','IMPORT')),
  selection_evidence jsonb NOT NULL DEFAULT '{}'::jsonb, CHECK(component_version_id IS NOT NULL OR product_version_id IS NOT NULL)
);
CREATE TABLE project_parameter_overrides (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  target_kind text NOT NULL, target_code text NOT NULL, value jsonb NOT NULL, unit_code text,
  source_kind text NOT NULL CHECK(source_kind IN ('USER','ENGINEER','IMPORT')), provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(project_revision_id, target_kind, target_code)
);
CREATE TABLE cem_snapshots (
  project_revision_id uuid PRIMARY KEY REFERENCES project_revisions(id) ON DELETE RESTRICT,
  schema_version integer NOT NULL, snapshot jsonb NOT NULL CHECK(jsonb_typeof(snapshot)='object'),
  sha256 char(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE cem_component_instances (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  stable_key text NOT NULL, role_code text NOT NULL, component_version_id uuid REFERENCES component_versions(id) ON DELETE RESTRICT,
  product_version_id uuid REFERENCES product_versions(id) ON DELETE RESTRICT, display_name text NOT NULL,
  parameters jsonb NOT NULL DEFAULT '{}'::jsonb, properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_template_role_id uuid REFERENCES template_component_roles(id) ON DELETE RESTRICT,
  UNIQUE(project_revision_id, stable_key), CHECK(component_version_id IS NOT NULL OR product_version_id IS NOT NULL)
);
CREATE TABLE cem_terminal_instances (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), component_instance_id uuid NOT NULL REFERENCES cem_component_instances(id) ON DELETE RESTRICT,
  stable_key text NOT NULL, terminal_code text NOT NULL, terminal_role text, electrical_properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(component_instance_id, stable_key)
);
CREATE TABLE cem_nets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  stable_key text NOT NULL, net_code text, wire_class text NOT NULL, nominal_voltage_v numeric CHECK(nominal_voltage_v IS NULL OR nominal_voltage_v >= 0),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb, UNIQUE(project_revision_id, stable_key)
);
CREATE TABLE cem_net_terminals (
  net_id uuid NOT NULL REFERENCES cem_nets(id) ON DELETE RESTRICT,
  terminal_instance_id uuid NOT NULL REFERENCES cem_terminal_instances(id) ON DELETE RESTRICT,
  connection_role text, PRIMARY KEY(net_id, terminal_instance_id)
);
CREATE TABLE cem_conductors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), net_id uuid NOT NULL REFERENCES cem_nets(id) ON DELETE RESTRICT,
  conductor_code text NOT NULL, conductor_type text NOT NULL, cross_section_mm2 numeric CHECK(cross_section_mm2 IS NULL OR cross_section_mm2 > 0),
  insulation jsonb NOT NULL DEFAULT '{}'::jsonb, properties jsonb NOT NULL DEFAULT '{}'::jsonb, UNIQUE(net_id, conductor_code)
);

CREATE TABLE pdm_snapshots (
  project_revision_id uuid PRIMARY KEY REFERENCES project_revisions(id) ON DELETE RESTRICT,
  schema_version integer NOT NULL, snapshot jsonb NOT NULL CHECK(jsonb_typeof(snapshot)='object'),
  sha256 char(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE pdm_enclosures (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  component_version_id uuid REFERENCES component_versions(id) ON DELETE RESTRICT, cad_model_version_id uuid REFERENCES cad_model_versions(id) ON DELETE RESTRICT,
  stable_key text NOT NULL, width_mm numeric NOT NULL CHECK(width_mm > 0), height_mm numeric NOT NULL CHECK(height_mm > 0), depth_mm numeric NOT NULL CHECK(depth_mm > 0),
  coordinate_frame jsonb NOT NULL, parameters jsonb NOT NULL DEFAULT '{}'::jsonb, UNIQUE(project_revision_id, stable_key)
);
CREATE TABLE pdm_mounting_structures (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  enclosure_id uuid NOT NULL REFERENCES pdm_enclosures(id) ON DELETE RESTRICT, stable_key text NOT NULL,
  structure_kind text NOT NULL CHECK(structure_kind IN ('BACKPLATE','DIN_RAIL','WIRE_DUCT','BUSBAR','SUPPORT','OTHER')),
  component_version_id uuid REFERENCES component_versions(id) ON DELETE RESTRICT,
  transform jsonb NOT NULL, dimensions_mm jsonb NOT NULL, parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(project_revision_id, stable_key)
);
CREATE TABLE pdm_component_instances (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  cem_component_instance_id uuid NOT NULL REFERENCES cem_component_instances(id) ON DELETE RESTRICT,
  cad_model_version_id uuid REFERENCES cad_model_versions(id) ON DELETE RESTRICT, stable_key text NOT NULL,
  instance_kind text NOT NULL DEFAULT 'COMPONENT', parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(project_revision_id, stable_key)
);
CREATE INDEX ix_pdm_component_cem ON pdm_component_instances(cem_component_instance_id);
CREATE TABLE pdm_placements (
  pdm_component_instance_id uuid PRIMARY KEY REFERENCES pdm_component_instances(id) ON DELETE RESTRICT,
  mounting_structure_id uuid REFERENCES pdm_mounting_structures(id) ON DELETE RESTRICT,
  transform jsonb NOT NULL, bounding_box_mm jsonb, zone_code text, placement_source text NOT NULL DEFAULT 'OPTIMIZER'
    CHECK(placement_source IN ('OPTIMIZER','ENGINEER','TEMPLATE','IMPORT')),
  evaluated_geometry_hash char(64)
);
CREATE TABLE pdm_clearance_regions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  stable_key text NOT NULL, owner_component_instance_id uuid REFERENCES pdm_component_instances(id) ON DELETE RESTRICT,
  region_kind text NOT NULL, geometry_ref jsonb NOT NULL, provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(project_revision_id, stable_key)
);
CREATE TABLE pdm_routes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  stable_key text NOT NULL, net_id uuid NOT NULL REFERENCES cem_nets(id) ON DELETE RESTRICT,
  conductor_id uuid REFERENCES cem_conductors(id) ON DELETE RESTRICT, route_kind text NOT NULL DEFAULT 'WIRE',
  waypoints_mm jsonb NOT NULL CHECK(jsonb_typeof(waypoints_mm)='array'), length_mm numeric CHECK(length_mm IS NULL OR length_mm >= 0),
  routing_constraints jsonb NOT NULL DEFAULT '{}'::jsonb, UNIQUE(project_revision_id, stable_key)
);

CREATE TABLE project_cad_instances (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  cad_model_version_id uuid NOT NULL REFERENCES cad_model_versions(id) ON DELETE RESTRICT,
  stable_key text NOT NULL, supplied_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  derived_values jsonb NOT NULL DEFAULT '{}'::jsonb, evaluated_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  generation_status text NOT NULL DEFAULT 'PENDING' CHECK(generation_status IN ('PENDING','READY','FAILED','STALE')),
  UNIQUE(project_revision_id, stable_key)
);
CREATE TABLE project_cad_assembly_instances (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  assembly_version_id uuid NOT NULL REFERENCES cad_assembly_versions(id) ON DELETE RESTRICT,
  stable_key text NOT NULL, transform jsonb NOT NULL,
  generation_status text NOT NULL DEFAULT 'PENDING' CHECK(generation_status IN ('PENDING','READY','FAILED','STALE')),
  UNIQUE(project_revision_id, stable_key)
);
CREATE TABLE project_cad_assembly_members (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), assembly_instance_id uuid NOT NULL REFERENCES project_cad_assembly_instances(id) ON DELETE RESTRICT,
  assembly_member_id uuid NOT NULL REFERENCES cad_assembly_members(id) ON DELETE RESTRICT,
  member_cad_model_version_id uuid NOT NULL REFERENCES cad_model_versions(id) ON DELETE RESTRICT,
  transform jsonb NOT NULL, parameter_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(assembly_instance_id, assembly_member_id)
);
CREATE TABLE revision_dependencies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  source_kind text NOT NULL, source_key text NOT NULL, target_kind text NOT NULL, target_key text NOT NULL,
  dependency_kind text NOT NULL, input_sha256 char(64), output_sha256 char(64), status text NOT NULL DEFAULT 'CURRENT' CHECK(status IN ('CURRENT','STALE','FAILED')),
  UNIQUE(project_revision_id, source_kind, source_key, target_kind, target_key, dependency_kind)
);
CREATE INDEX ix_revision_dependency_target ON revision_dependencies(project_revision_id, target_kind, target_key);
CREATE TABLE provenance (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_id uuid REFERENCES projects(id) ON DELETE RESTRICT,
  project_revision_id uuid REFERENCES project_revisions(id) ON DELETE RESTRICT,
  subject_kind text NOT NULL, subject_key text NOT NULL,
  source_kind text NOT NULL CHECK(source_kind IN ('USER','MANUFACTURER','ENGINEER','RULE','OPTIMIZER','CAD_GENERATOR','IMPORT')),
  source_ref text, actor_id text, created_at timestamptz NOT NULL DEFAULT now(), details jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ix_provenance_subject ON provenance(subject_kind, subject_key);
CREATE TABLE validation_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  rule_set_version_id uuid REFERENCES rule_set_versions(id) ON DELETE RESTRICT,
  engine_name text NOT NULL, engine_version text NOT NULL,
  status text NOT NULL CHECK(status IN ('RUNNING','PASSED','FAILED','COMPLETED_WITH_WARNINGS')),
  input_sha256 char(64), started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
  CHECK(completed_at IS NULL OR completed_at >= started_at)
);
CREATE TABLE validation_results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), validation_run_id uuid NOT NULL REFERENCES validation_runs(id) ON DELETE RESTRICT,
  rule_version_id uuid REFERENCES design_rule_versions(id) ON DELETE RESTRICT, rule_code text NOT NULL,
  result_status text NOT NULL CHECK(result_status IN ('PASS','FAIL','WARNING','SKIPPED')),
  affected_entities jsonb NOT NULL DEFAULT '[]'::jsonb, measured_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  message text NOT NULL, evidence jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_validation_results_run_status ON validation_results(validation_run_id, result_status);
CREATE TABLE generated_artifacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), project_revision_id uuid NOT NULL REFERENCES project_revisions(id) ON DELETE RESTRICT,
  artifact_type text NOT NULL, file_format text NOT NULL, storage_backend text NOT NULL DEFAULT 'LOCAL', storage_key text,
  sha256 char(64), byte_size bigint CHECK(byte_size IS NULL OR byte_size >= 0), generator_name text NOT NULL,
  generator_version text NOT NULL, source_model_kind text NOT NULL, source_model_sha256 char(64),
  generation_status text NOT NULL CHECK(generation_status IN ('PENDING','READY','FAILED','MISSING','CORRUPT')),
  error jsonb, created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
  CHECK(sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
  CHECK(source_model_sha256 IS NULL OR source_model_sha256 ~ '^[0-9a-f]{64}$'),
  CHECK(generation_status <> 'READY' OR (storage_key IS NOT NULL AND sha256 IS NOT NULL))
);
CREATE INDEX ix_generated_artifact_revision_type ON generated_artifacts(project_revision_id, artifact_type, created_at DESC);

-- Immutable revision snapshot consistency is additionally checked in the application:
-- compute canonical JSON SHA-256 and set project_revisions.content_sha256, cem/pdm.sha256
-- in the same transaction as the corresponding projections and dependencies.
