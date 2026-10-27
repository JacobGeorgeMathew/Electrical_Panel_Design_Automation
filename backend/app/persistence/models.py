"""Generated from the frozen DDL and Alembic head by tools/build_schema_models.py. Do not hand-edit."""
from sqlalchemy import *
from sqlalchemy.dialects.postgresql import *
from sqlalchemy.orm import declarative_base, relationship
metadata = MetaData()

archetype_defaults = Table('archetype_defaults', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('archetype_version_id', UUID(), nullable=False),
    Column('code', TEXT(), nullable=False),
    Column('value', JSONB(astext_type=Text()), nullable=False),
    Column('unit_code', TEXT(), nullable=True),
    ForeignKeyConstraint(['archetype_version_id'], ['panel_archetype_versions.id'], name='archetype_defaults_archetype_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['archetype_version_id', 'code'], name='archetype_defaults_archetype_version_id_code_key'),
)

archetype_electrical_templates = Table('archetype_electrical_templates', metadata,
    Column('archetype_version_id', UUID(), primary_key=True, nullable=False),
    Column('template_version_id', UUID(), primary_key=True, nullable=False),
    Column('sequence_no', INTEGER(), nullable=False, server_default=text('0')),
    Column('required', BOOLEAN(), nullable=False, server_default=text('true')),
    ForeignKeyConstraint(['archetype_version_id'], ['panel_archetype_versions.id'], name='archetype_electrical_templates_archetype_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['template_version_id'], ['electrical_template_versions.id'], name='archetype_electrical_templates_template_version_id_fkey', **{'ondelete': 'RESTRICT'}),
)

archetype_modules = Table('archetype_modules', metadata,
    Column('archetype_version_id', UUID(), primary_key=True, nullable=False),
    Column('module_version_id', UUID(), primary_key=True, nullable=False),
    Column('sequence_no', INTEGER(), nullable=False, server_default=text('0')),
    Column('required', BOOLEAN(), nullable=False, server_default=text('true')),
    Column('configuration', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['archetype_version_id'], ['panel_archetype_versions.id'], name='archetype_modules_archetype_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['module_version_id'], ['functional_module_versions.id'], name='archetype_modules_module_version_id_fkey', **{'ondelete': 'RESTRICT'}),
)

archetype_questionnaires = Table('archetype_questionnaires', metadata,
    Column('archetype_version_id', UUID(), primary_key=True, nullable=False),
    Column('questionnaire_version_id', UUID(), primary_key=True, nullable=False),
    Column('sequence_no', INTEGER(), nullable=False, server_default=text('0')),
    ForeignKeyConstraint(['archetype_version_id'], ['panel_archetype_versions.id'], name='archetype_questionnaires_archetype_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['questionnaire_version_id'], ['questionnaire_versions.id'], name='archetype_questionnaires_questionnaire_version_id_fkey', **{'ondelete': 'RESTRICT'}),
)

cad_assemblies = Table('cad_assemblies', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('code', TEXT(), nullable=False),
    Column('name', TEXT(), nullable=False),
    UniqueConstraint(*['code'], name='cad_assemblies_code_key'),
)

cad_assembly_members = Table('cad_assembly_members', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('assembly_version_id', UUID(), nullable=False),
    Column('member_cad_model_version_id', UUID(), nullable=False),
    Column('member_code', TEXT(), nullable=False),
    Column('quantity', INTEGER(), nullable=False, server_default=text('1')),
    Column('transform', JSONB(astext_type=Text()), nullable=False),
    Column('parameter_defaults', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['assembly_version_id'], ['cad_assembly_versions.id'], name='cad_assembly_members_assembly_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['member_cad_model_version_id'], ['cad_model_versions.id'], name='cad_assembly_members_member_cad_model_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['assembly_version_id', 'member_code'], name='cad_assembly_members_assembly_version_id_member_code_key'),
    CheckConstraint('quantity > 0', name='cad_assembly_members_quantity_check'),
)

cad_assembly_versions = Table('cad_assembly_versions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('assembly_id', UUID(), nullable=False),
    Column('version_no', INTEGER(), nullable=False),
    Column('status', TEXT(), nullable=False),
    ForeignKeyConstraint(['assembly_id'], ['cad_assemblies.id'], name='cad_assembly_versions_assembly_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['assembly_id', 'version_no'], name='cad_assembly_versions_assembly_id_version_no_key'),
    CheckConstraint("status = ANY (ARRAY['DRAFT'::text, 'PUBLISHED'::text, 'WITHDRAWN'::text])", name='cad_assembly_versions_status_check'),
    CheckConstraint('version_no > 0', name='cad_assembly_versions_version_no_check'),
)

cad_assets = Table('cad_assets', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('cad_model_version_id', UUID(), nullable=False),
    Column('asset_role', TEXT(), nullable=False),
    Column('file_format', TEXT(), nullable=False),
    Column('storage_backend', TEXT(), nullable=False, server_default=text("'LOCAL'::text")),
    Column('storage_key', TEXT(), nullable=False),
    Column('sha256', CHAR(length=64), nullable=False),
    Column('byte_size', BIGINT(), nullable=False),
    Column('media_type', TEXT(), nullable=True),
    Column('source_asset_id', UUID(), nullable=True),
    Column('generator_name', TEXT(), nullable=True),
    Column('generator_version', TEXT(), nullable=True),
    Column('generation_status', TEXT(), nullable=False, server_default=text("'READY'::text")),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    ForeignKeyConstraint(['cad_model_version_id'], ['cad_model_versions.id'], name='cad_assets_cad_model_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['source_asset_id'], ['cad_assets.id'], name='cad_assets_source_asset_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['storage_backend', 'storage_key'], name='cad_assets_storage_backend_storage_key_key'),
    CheckConstraint('byte_size >= 0', name='cad_assets_byte_size_check'),
    CheckConstraint("file_format = ANY (ARRAY['FCSTD'::text, 'STEP'::text, 'STP'::text, 'GLB'::text, 'GLTF'::text, 'JSON'::text, 'OTHER'::text])", name='cad_assets_file_format_check'),
    CheckConstraint("generation_status = ANY (ARRAY['PENDING'::text, 'READY'::text, 'FAILED'::text, 'MISSING'::text, 'CORRUPT'::text])", name='cad_assets_generation_status_check'),
    CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'::text", name='cad_assets_sha256_check'),
)

cad_features = Table('cad_features', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('cad_model_version_id', UUID(), nullable=False),
    Column('code', TEXT(), nullable=False),
    Column('sequence_no', INTEGER(), nullable=False),
    Column('operation_code', TEXT(), nullable=False),
    Column('feature_definition', JSONB(astext_type=Text()), nullable=False),
    Column('depends_on_codes', ARRAY(TEXT()), nullable=False, server_default=text("'{}'::text[]")),
    ForeignKeyConstraint(['cad_model_version_id'], ['cad_model_versions.id'], name='cad_features_cad_model_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['cad_model_version_id', 'code'], name='cad_features_cad_model_version_id_code_key'),
    UniqueConstraint(*['cad_model_version_id', 'sequence_no'], name='cad_features_cad_model_version_id_sequence_no_key'),
    CheckConstraint('sequence_no >= 0', name='cad_features_sequence_no_check'),
)

cad_model_versions = Table('cad_model_versions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('cad_model_id', UUID(), nullable=False),
    Column('version_no', INTEGER(), nullable=False),
    Column('status', TEXT(), nullable=False),
    Column('coordinate_system', JSONB(astext_type=Text()), nullable=False, server_default=text('\'{"handedness": "right", "length_unit": "mm"}\'::jsonb')),
    Column('feature_definition', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('generator_name', TEXT(), nullable=True),
    Column('generator_version', TEXT(), nullable=True),
    Column('dependency_manifest', JSONB(astext_type=Text()), nullable=False, server_default=text("'[]'::jsonb")),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    ForeignKeyConstraint(['cad_model_id'], ['cad_models.id'], name='cad_model_versions_cad_model_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['cad_model_id', 'version_no'], name='cad_model_versions_cad_model_id_version_no_key'),
    CheckConstraint("status = ANY (ARRAY['DRAFT'::text, 'PUBLISHED'::text, 'WITHDRAWN'::text])", name='cad_model_versions_status_check'),
    CheckConstraint('version_no > 0', name='cad_model_versions_version_no_check'),
)

cad_models = Table('cad_models', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('code', TEXT(), nullable=False),
    Column('name', TEXT(), nullable=False),
    Column('model_kind', TEXT(), nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    UniqueConstraint(*['code'], name='cad_models_code_key'),
    CheckConstraint("model_kind = ANY (ARRAY['PART'::text, 'ASSEMBLY'::text, 'ACCESSORY'::text])", name='cad_models_model_kind_check'),
)

cad_parameter_definitions = Table('cad_parameter_definitions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('cad_model_version_id', UUID(), nullable=False),
    Column('code', TEXT(), nullable=False),
    Column('value_type', TEXT(), nullable=False),
    Column('unit_code', TEXT(), nullable=True),
    Column('default_value', JSONB(astext_type=Text()), nullable=True),
    Column('min_value', NUMERIC(), nullable=True),
    Column('max_value', NUMERIC(), nullable=True),
    Column('allowed_values', JSONB(astext_type=Text()), nullable=True),
    Column('editable', BOOLEAN(), nullable=False, server_default=text('true')),
    Column('derived', BOOLEAN(), nullable=False, server_default=text('false')),
    Column('expression', TEXT(), nullable=True),
    Column('dependencies', ARRAY(TEXT()), nullable=False, server_default=text("'{}'::text[]")),
    Column('description', TEXT(), nullable=True),
    ForeignKeyConstraint(['cad_model_version_id'], ['cad_model_versions.id'], name='cad_parameter_definitions_cad_model_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['cad_model_version_id', 'code'], name='cad_parameter_definitions_cad_model_version_id_code_key'),
    CheckConstraint('min_value IS NULL OR max_value IS NULL OR max_value >= min_value', name='cad_parameter_definitions_check'),
    CheckConstraint('NOT (editable AND derived)', name='cad_parameter_definitions_check1'),
    CheckConstraint("value_type = ANY (ARRAY['STRING'::text, 'INTEGER'::text, 'DECIMAL'::text, 'BOOLEAN'::text, 'ENUM'::text, 'OBJECT'::text])", name='cad_parameter_definitions_value_type_check'),
)

cem_component_instances = Table('cem_component_instances', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('stable_key', TEXT(), nullable=False),
    Column('role_code', TEXT(), nullable=False),
    Column('component_version_id', UUID(), nullable=True),
    Column('product_version_id', UUID(), nullable=True),
    Column('display_name', TEXT(), nullable=False),
    Column('parameters', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('properties', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('source_template_role_id', UUID(), nullable=True),
    ForeignKeyConstraint(['component_version_id'], ['component_versions.id'], name='cem_component_instances_component_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['product_version_id'], ['product_versions.id'], name='cem_component_instances_product_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='cem_component_instances_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['source_template_role_id'], ['template_component_roles.id'], name='cem_component_instances_source_template_role_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_revision_id', 'stable_key'], name='cem_component_instances_project_revision_id_stable_key_key'),
    CheckConstraint('component_version_id IS NOT NULL OR product_version_id IS NOT NULL', name='cem_component_instances_check'),
)

cem_conductors = Table('cem_conductors', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('net_id', UUID(), nullable=False),
    Column('conductor_code', TEXT(), nullable=False),
    Column('conductor_type', TEXT(), nullable=False),
    Column('cross_section_mm2', NUMERIC(), nullable=True),
    Column('insulation', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('properties', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('from_terminal_instance_id', UUID(), nullable=True),
    Column('to_terminal_instance_id', UUID(), nullable=True),
    ForeignKeyConstraint(['from_terminal_instance_id'], ['cem_terminal_instances.id'], name='cem_conductors_from_terminal_instance_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['net_id'], ['cem_nets.id'], name='cem_conductors_net_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['to_terminal_instance_id'], ['cem_terminal_instances.id'], name='cem_conductors_to_terminal_instance_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['net_id', 'conductor_code'], name='cem_conductors_net_id_conductor_code_key'),
    CheckConstraint('cross_section_mm2 IS NULL OR cross_section_mm2 > 0::numeric', name='cem_conductors_cross_section_mm2_check'),
)

cem_net_terminals = Table('cem_net_terminals', metadata,
    Column('net_id', UUID(), primary_key=True, nullable=False),
    Column('terminal_instance_id', UUID(), primary_key=True, nullable=False),
    Column('connection_role', TEXT(), nullable=True),
    ForeignKeyConstraint(['net_id'], ['cem_nets.id'], name='cem_net_terminals_net_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['terminal_instance_id'], ['cem_terminal_instances.id'], name='cem_net_terminals_terminal_instance_id_fkey', **{'ondelete': 'RESTRICT'}),
)

cem_nets = Table('cem_nets', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('stable_key', TEXT(), nullable=False),
    Column('net_code', TEXT(), nullable=True),
    Column('wire_class', TEXT(), nullable=False),
    Column('nominal_voltage_v', NUMERIC(), nullable=True),
    Column('properties', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='cem_nets_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_revision_id', 'stable_key'], name='cem_nets_project_revision_id_stable_key_key'),
    CheckConstraint('nominal_voltage_v IS NULL OR nominal_voltage_v >= 0::numeric', name='cem_nets_nominal_voltage_v_check'),
)

cem_snapshots = Table('cem_snapshots', metadata,
    Column('project_revision_id', UUID(), primary_key=True, nullable=False),
    Column('schema_version', INTEGER(), nullable=False),
    Column('snapshot', JSONB(astext_type=Text()), nullable=False),
    Column('sha256', CHAR(length=64), nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='cem_snapshots_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'::text", name='cem_snapshots_sha256_check'),
    CheckConstraint("jsonb_typeof(snapshot) = 'object'::text", name='cem_snapshots_snapshot_check'),
)

cem_terminal_instances = Table('cem_terminal_instances', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('component_instance_id', UUID(), nullable=False),
    Column('stable_key', TEXT(), nullable=False),
    Column('terminal_code', TEXT(), nullable=False),
    Column('terminal_role', TEXT(), nullable=True),
    Column('electrical_properties', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['component_instance_id'], ['cem_component_instances.id'], name='cem_terminal_instances_component_instance_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['component_instance_id', 'stable_key'], name='cem_terminal_instances_component_instance_id_stable_key_key'),
)

component_accessories = Table('component_accessories', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('component_version_id', UUID(), nullable=False),
    Column('accessory_component_version_id', UUID(), nullable=False),
    Column('relation_code', TEXT(), nullable=False, server_default=text("'COMPATIBLE'::text")),
    Column('constraints', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['accessory_component_version_id'], ['component_versions.id'], name='component_accessories_accessory_component_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['component_version_id'], ['component_versions.id'], name='component_accessories_component_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['component_version_id', 'accessory_component_version_id', 'relation_code'], name='component_accessories_component_version_id_accessory_compon_key'),
    CheckConstraint('component_version_id <> accessory_component_version_id', name='component_accessories_check'),
)

component_cad_models = Table('component_cad_models', metadata,
    Column('component_version_id', UUID(), primary_key=True, nullable=False),
    Column('cad_model_version_id', UUID(), primary_key=True, nullable=False),
    Column('representation_role', TEXT(), primary_key=True, nullable=False, server_default=text("'PRIMARY'::text")),
    ForeignKeyConstraint(['cad_model_version_id'], ['cad_model_versions.id'], name='component_cad_models_cad_model_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['component_version_id'], ['component_versions.id'], name='component_cad_models_component_version_id_fkey', **{'ondelete': 'RESTRICT'}),
)

component_clearances = Table('component_clearances', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('component_version_id', UUID(), nullable=False),
    Column('direction_code', TEXT(), nullable=False),
    Column('distance_mm', NUMERIC(), nullable=False),
    Column('provenance', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['component_version_id'], ['component_versions.id'], name='component_clearances_component_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['component_version_id', 'direction_code'], name='component_clearances_component_version_id_direction_code_key'),
    CheckConstraint('distance_mm >= 0::numeric', name='component_clearances_distance_mm_check'),
)

component_documents = Table('component_documents', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('component_version_id', UUID(), nullable=False),
    Column('document_type', TEXT(), nullable=False),
    Column('title', TEXT(), nullable=False),
    Column('uri', TEXT(), nullable=True),
    Column('asset_hash', CHAR(length=64), nullable=True),
    Column('language_code', TEXT(), nullable=True),
    Column('provenance', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['component_version_id'], ['component_versions.id'], name='component_documents_component_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    CheckConstraint("asset_hash IS NULL OR asset_hash ~ '^[0-9a-f]{64}$'::text", name='component_documents_asset_hash_check'),
)

component_mounting = Table('component_mounting', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('component_version_id', UUID(), nullable=False),
    Column('mounting_code', TEXT(), nullable=False),
    Column('footprint_asset_hint', TEXT(), nullable=True),
    Column('mounting_parameters', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['component_version_id'], ['component_versions.id'], name='component_mounting_component_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['component_version_id', 'mounting_code'], name='component_mounting_component_version_id_mounting_code_key'),
)

component_terminals = Table('component_terminals', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('component_version_id', UUID(), nullable=False),
    Column('code', TEXT(), nullable=False),
    Column('terminal_kind', TEXT(), nullable=False),
    Column('electrical_role', TEXT(), nullable=True),
    Column('connection_type', TEXT(), nullable=True),
    Column('conductor_min_mm2', NUMERIC(), nullable=True),
    Column('conductor_max_mm2', NUMERIC(), nullable=True),
    Column('coordinate_mm', JSONB(astext_type=Text()), nullable=True),
    Column('orientation', JSONB(astext_type=Text()), nullable=True),
    ForeignKeyConstraint(['component_version_id'], ['component_versions.id'], name='component_terminals_component_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['component_version_id', 'code'], name='component_terminals_component_version_id_code_key'),
    CheckConstraint('conductor_max_mm2 IS NULL OR conductor_max_mm2 >= conductor_min_mm2', name='component_terminals_check'),
    CheckConstraint('conductor_min_mm2 IS NULL OR conductor_min_mm2 >= 0::numeric', name='component_terminals_conductor_min_mm2_check'),
    CheckConstraint("coordinate_mm IS NULL OR jsonb_typeof(coordinate_mm) = 'object'::text", name='component_terminals_coordinate_mm_check'),
)

component_thermal_specs = Table('component_thermal_specs', metadata,
    Column('component_version_id', UUID(), primary_key=True, nullable=False),
    Column('heat_loss_w', NUMERIC(), nullable=True),
    Column('operating_temperature_min_c', NUMERIC(), nullable=True),
    Column('operating_temperature_max_c', NUMERIC(), nullable=True),
    Column('details', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['component_version_id'], ['component_versions.id'], name='component_thermal_specs_component_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    CheckConstraint('operating_temperature_max_c IS NULL OR operating_temperature_min_c IS NULL OR operating_temperature_max_c >= operating_temperature_min_c', name='component_thermal_specs_check'),
    CheckConstraint('heat_loss_w IS NULL OR heat_loss_w >= 0::numeric', name='component_thermal_specs_heat_loss_w_check'),
)

component_versions = Table('component_versions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('component_id', UUID(), nullable=False),
    Column('version_no', INTEGER(), nullable=False),
    Column('schema_version', INTEGER(), nullable=False, server_default=text('1')),
    Column('status', TEXT(), nullable=False),
    Column('rated_voltage_v', NUMERIC(), nullable=True),
    Column('rated_current_a', NUMERIC(), nullable=True),
    Column('breaking_capacity_ka', NUMERIC(), nullable=True),
    Column('pole_count', SMALLINT(), nullable=True),
    Column('width_mm', NUMERIC(), nullable=True),
    Column('height_mm', NUMERIC(), nullable=True),
    Column('depth_mm', NUMERIC(), nullable=True),
    Column('mass_kg', NUMERIC(), nullable=True),
    Column('specification', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('valid_from', TIMESTAMP(timezone=True), nullable=True),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    Column('created_by', TEXT(), nullable=True),
    ForeignKeyConstraint(['component_id'], ['components.id'], name='component_versions_component_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['component_id', 'version_no'], name='component_versions_component_id_version_no_key'),
    CheckConstraint('breaking_capacity_ka IS NULL OR breaking_capacity_ka >= 0::numeric', name='component_versions_breaking_capacity_ka_check'),
    CheckConstraint('depth_mm IS NULL OR depth_mm >= 0::numeric', name='component_versions_depth_mm_check'),
    CheckConstraint('height_mm IS NULL OR height_mm >= 0::numeric', name='component_versions_height_mm_check'),
    CheckConstraint('mass_kg IS NULL OR mass_kg >= 0::numeric', name='component_versions_mass_kg_check'),
    CheckConstraint('pole_count IS NULL OR pole_count > 0', name='component_versions_pole_count_check'),
    CheckConstraint('rated_current_a IS NULL OR rated_current_a >= 0::numeric', name='component_versions_rated_current_a_check'),
    CheckConstraint('rated_voltage_v IS NULL OR rated_voltage_v >= 0::numeric', name='component_versions_rated_voltage_v_check'),
    CheckConstraint('schema_version > 0', name='component_versions_schema_version_check'),
    CheckConstraint("jsonb_typeof(specification) = 'object'::text", name='component_versions_specification_check'),
    CheckConstraint("status = ANY (ARRAY['DRAFT'::text, 'PUBLISHED'::text, 'WITHDRAWN'::text])", name='component_versions_status_check'),
    CheckConstraint('version_no > 0', name='component_versions_version_no_check'),
    CheckConstraint('width_mm IS NULL OR width_mm >= 0::numeric', name='component_versions_width_mm_check'),
)

components = Table('components', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('code', TEXT(), nullable=False),
    Column('name', TEXT(), nullable=False),
    Column('category_code', TEXT(), nullable=False),
    Column('component_kind', TEXT(), nullable=False),
    Column('lifecycle_status', TEXT(), nullable=False, server_default=text("'ACTIVE'::text")),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    UniqueConstraint(*['code'], name='components_code_key'),
    CheckConstraint("lifecycle_status = ANY (ARRAY['ACTIVE'::text, 'OBSOLETE'::text, 'DRAFT'::text])", name='components_lifecycle_status_check'),
)

design_rule_versions = Table('design_rule_versions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('rule_id', UUID(), nullable=False),
    Column('version_no', INTEGER(), nullable=False),
    Column('status', TEXT(), nullable=False),
    Column('severity', TEXT(), nullable=False),
    Column('hardness', TEXT(), nullable=False),
    Column('priority', INTEGER(), nullable=False, server_default=text('100')),
    Column('parameters', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('provenance', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['rule_id'], ['design_rules.id'], name='design_rule_versions_rule_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['rule_id', 'version_no'], name='design_rule_versions_rule_id_version_no_key'),
    CheckConstraint("hardness = ANY (ARRAY['HARD'::text, 'SOFT'::text])", name='design_rule_versions_hardness_check'),
    CheckConstraint("severity = ANY (ARRAY['INFO'::text, 'WARNING'::text, 'ERROR'::text])", name='design_rule_versions_severity_check'),
    CheckConstraint("status = ANY (ARRAY['DRAFT'::text, 'PUBLISHED'::text, 'WITHDRAWN'::text])", name='design_rule_versions_status_check'),
    CheckConstraint('version_no > 0', name='design_rule_versions_version_no_check'),
)

design_rules = Table('design_rules', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('code', TEXT(), nullable=False),
    Column('name', TEXT(), nullable=False),
    Column('engine_handler', TEXT(), nullable=False),
    UniqueConstraint(*['code'], name='design_rules_code_key'),
)

electrical_template_versions = Table('electrical_template_versions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('template_id', UUID(), nullable=False),
    Column('version_no', INTEGER(), nullable=False),
    Column('status', TEXT(), nullable=False),
    Column('validation_rules', JSONB(astext_type=Text()), nullable=False, server_default=text("'[]'::jsonb")),
    ForeignKeyConstraint(['template_id'], ['electrical_templates.id'], name='electrical_template_versions_template_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['template_id', 'version_no'], name='electrical_template_versions_template_id_version_no_key'),
    CheckConstraint("status = ANY (ARRAY['DRAFT'::text, 'PUBLISHED'::text, 'WITHDRAWN'::text])", name='electrical_template_versions_status_check'),
    CheckConstraint('version_no > 0', name='electrical_template_versions_version_no_check'),
)

electrical_templates = Table('electrical_templates', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('code', TEXT(), nullable=False),
    Column('name', TEXT(), nullable=False),
    UniqueConstraint(*['code'], name='electrical_templates_code_key'),
)

functional_module_versions = Table('functional_module_versions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('module_id', UUID(), nullable=False),
    Column('version_no', INTEGER(), nullable=False),
    Column('status', TEXT(), nullable=False),
    ForeignKeyConstraint(['module_id'], ['functional_modules.id'], name='functional_module_versions_module_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['module_id', 'version_no'], name='functional_module_versions_module_id_version_no_key'),
    CheckConstraint("status = ANY (ARRAY['DRAFT'::text, 'PUBLISHED'::text, 'WITHDRAWN'::text])", name='functional_module_versions_status_check'),
    CheckConstraint('version_no > 0', name='functional_module_versions_version_no_check'),
)

functional_modules = Table('functional_modules', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('code', TEXT(), nullable=False),
    Column('name', TEXT(), nullable=False),
    Column('description', TEXT(), nullable=True),
    UniqueConstraint(*['code'], name='functional_modules_code_key'),
)

generated_artifacts = Table('generated_artifacts', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('artifact_type', TEXT(), nullable=False),
    Column('file_format', TEXT(), nullable=False),
    Column('storage_backend', TEXT(), nullable=False, server_default=text("'LOCAL'::text")),
    Column('storage_key', TEXT(), nullable=True),
    Column('sha256', CHAR(length=64), nullable=True),
    Column('byte_size', BIGINT(), nullable=True),
    Column('generator_name', TEXT(), nullable=False),
    Column('generator_version', TEXT(), nullable=False),
    Column('source_model_kind', TEXT(), nullable=False),
    Column('source_model_sha256', CHAR(length=64), nullable=True),
    Column('generation_status', TEXT(), nullable=False),
    Column('error', JSONB(astext_type=Text()), nullable=True),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    Column('completed_at', TIMESTAMP(timezone=True), nullable=True),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='generated_artifacts_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    CheckConstraint('byte_size IS NULL OR byte_size >= 0', name='generated_artifacts_byte_size_check'),
    CheckConstraint("generation_status <> 'READY'::text OR storage_key IS NOT NULL AND sha256 IS NOT NULL", name='generated_artifacts_check'),
    CheckConstraint("generation_status = ANY (ARRAY['PENDING'::text, 'READY'::text, 'FAILED'::text, 'MISSING'::text, 'CORRUPT'::text])", name='generated_artifacts_generation_status_check'),
    CheckConstraint("sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'::text", name='generated_artifacts_sha256_check'),
    CheckConstraint("source_model_sha256 IS NULL OR source_model_sha256 ~ '^[0-9a-f]{64}$'::text", name='generated_artifacts_source_model_sha256_check'),
)

manufacturers = Table('manufacturers', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('code', TEXT(), nullable=False),
    Column('name', TEXT(), nullable=False),
    Column('website', TEXT(), nullable=True),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    UniqueConstraint(*['code'], name='manufacturers_code_key'),
    UniqueConstraint(*['name'], name='manufacturers_name_key'),
)

module_role_requirements = Table('module_role_requirements', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('module_version_id', UUID(), nullable=False),
    Column('role_code', TEXT(), nullable=False),
    Column('quantity_min', INTEGER(), nullable=False, server_default=text('1')),
    Column('quantity_max', INTEGER(), nullable=True),
    Column('required_properties', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('selection_policy', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['module_version_id'], ['functional_module_versions.id'], name='module_role_requirements_module_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['module_version_id', 'role_code'], name='module_role_requirements_module_version_id_role_code_key'),
    CheckConstraint('quantity_max IS NULL OR quantity_max >= quantity_min', name='module_role_requirements_check'),
    CheckConstraint('quantity_min >= 0', name='module_role_requirements_quantity_min_check'),
)

panel_archetype_versions = Table('panel_archetype_versions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('archetype_id', UUID(), nullable=False),
    Column('version_no', INTEGER(), nullable=False),
    Column('status', TEXT(), nullable=False),
    Column('defaults', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    ForeignKeyConstraint(['archetype_id'], ['panel_archetypes.id'], name='panel_archetype_versions_archetype_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['archetype_id', 'version_no'], name='panel_archetype_versions_archetype_id_version_no_key'),
    CheckConstraint("status = ANY (ARRAY['DRAFT'::text, 'PUBLISHED'::text, 'WITHDRAWN'::text])", name='panel_archetype_versions_status_check'),
    CheckConstraint('version_no > 0', name='panel_archetype_versions_version_no_check'),
)

panel_archetypes = Table('panel_archetypes', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('code', TEXT(), nullable=False),
    Column('name', TEXT(), nullable=False),
    Column('description', TEXT(), nullable=True),
    UniqueConstraint(*['code'], name='panel_archetypes_code_key'),
)

pdm_clearance_regions = Table('pdm_clearance_regions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('stable_key', TEXT(), nullable=False),
    Column('owner_component_instance_id', UUID(), nullable=True),
    Column('region_kind', TEXT(), nullable=False),
    Column('geometry_ref', JSONB(astext_type=Text()), nullable=False),
    Column('provenance', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['owner_component_instance_id'], ['pdm_component_instances.id'], name='pdm_clearance_regions_owner_component_instance_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='pdm_clearance_regions_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_revision_id', 'stable_key'], name='pdm_clearance_regions_project_revision_id_stable_key_key'),
)

pdm_component_instances = Table('pdm_component_instances', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('cem_component_instance_id', UUID(), nullable=False),
    Column('cad_model_version_id', UUID(), nullable=True),
    Column('stable_key', TEXT(), nullable=False),
    Column('instance_kind', TEXT(), nullable=False, server_default=text("'COMPONENT'::text")),
    Column('parameters', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['cad_model_version_id'], ['cad_model_versions.id'], name='pdm_component_instances_cad_model_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['cem_component_instance_id'], ['cem_component_instances.id'], name='pdm_component_instances_cem_component_instance_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='pdm_component_instances_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_revision_id', 'stable_key'], name='pdm_component_instances_project_revision_id_stable_key_key'),
)

pdm_enclosures = Table('pdm_enclosures', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('component_version_id', UUID(), nullable=True),
    Column('cad_model_version_id', UUID(), nullable=True),
    Column('stable_key', TEXT(), nullable=False),
    Column('width_mm', NUMERIC(), nullable=False),
    Column('height_mm', NUMERIC(), nullable=False),
    Column('depth_mm', NUMERIC(), nullable=False),
    Column('coordinate_frame', JSONB(astext_type=Text()), nullable=False),
    Column('parameters', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['cad_model_version_id'], ['cad_model_versions.id'], name='pdm_enclosures_cad_model_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['component_version_id'], ['component_versions.id'], name='pdm_enclosures_component_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='pdm_enclosures_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_revision_id', 'stable_key'], name='pdm_enclosures_project_revision_id_stable_key_key'),
    CheckConstraint('depth_mm > 0::numeric', name='pdm_enclosures_depth_mm_check'),
    CheckConstraint('height_mm > 0::numeric', name='pdm_enclosures_height_mm_check'),
    CheckConstraint('width_mm > 0::numeric', name='pdm_enclosures_width_mm_check'),
)

pdm_mounting_structures = Table('pdm_mounting_structures', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('enclosure_id', UUID(), nullable=False),
    Column('stable_key', TEXT(), nullable=False),
    Column('structure_kind', TEXT(), nullable=False),
    Column('component_version_id', UUID(), nullable=True),
    Column('transform', JSONB(astext_type=Text()), nullable=False),
    Column('dimensions_mm', JSONB(astext_type=Text()), nullable=False),
    Column('parameters', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['component_version_id'], ['component_versions.id'], name='pdm_mounting_structures_component_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['enclosure_id'], ['pdm_enclosures.id'], name='pdm_mounting_structures_enclosure_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='pdm_mounting_structures_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_revision_id', 'stable_key'], name='pdm_mounting_structures_project_revision_id_stable_key_key'),
    CheckConstraint("structure_kind = ANY (ARRAY['BACKPLATE'::text, 'DIN_RAIL'::text, 'WIRE_DUCT'::text, 'BUSBAR'::text, 'SUPPORT'::text, 'OTHER'::text])", name='pdm_mounting_structures_structure_kind_check'),
)

pdm_placements = Table('pdm_placements', metadata,
    Column('pdm_component_instance_id', UUID(), primary_key=True, nullable=False),
    Column('mounting_structure_id', UUID(), nullable=True),
    Column('transform', JSONB(astext_type=Text()), nullable=False),
    Column('bounding_box_mm', JSONB(astext_type=Text()), nullable=True),
    Column('zone_code', TEXT(), nullable=True),
    Column('placement_source', TEXT(), nullable=False, server_default=text("'OPTIMIZER'::text")),
    Column('evaluated_geometry_hash', CHAR(length=64), nullable=True),
    ForeignKeyConstraint(['mounting_structure_id'], ['pdm_mounting_structures.id'], name='pdm_placements_mounting_structure_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['pdm_component_instance_id'], ['pdm_component_instances.id'], name='pdm_placements_pdm_component_instance_id_fkey', **{'ondelete': 'RESTRICT'}),
    CheckConstraint("placement_source = ANY (ARRAY['OPTIMIZER'::text, 'ENGINEER'::text, 'TEMPLATE'::text, 'IMPORT'::text])", name='pdm_placements_placement_source_check'),
)

pdm_routes = Table('pdm_routes', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('stable_key', TEXT(), nullable=False),
    Column('net_id', UUID(), nullable=False),
    Column('conductor_id', UUID(), nullable=True),
    Column('route_kind', TEXT(), nullable=False, server_default=text("'WIRE'::text")),
    Column('waypoints_mm', JSONB(astext_type=Text()), nullable=False),
    Column('length_mm', NUMERIC(), nullable=True),
    Column('routing_constraints', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['conductor_id'], ['cem_conductors.id'], name='pdm_routes_conductor_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['net_id'], ['cem_nets.id'], name='pdm_routes_net_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='pdm_routes_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_revision_id', 'stable_key'], name='pdm_routes_project_revision_id_stable_key_key'),
    CheckConstraint('length_mm IS NULL OR length_mm >= 0::numeric', name='pdm_routes_length_mm_check'),
    CheckConstraint("jsonb_typeof(waypoints_mm) = 'array'::text", name='pdm_routes_waypoints_mm_check'),
)

pdm_snapshots = Table('pdm_snapshots', metadata,
    Column('project_revision_id', UUID(), primary_key=True, nullable=False),
    Column('schema_version', INTEGER(), nullable=False),
    Column('snapshot', JSONB(astext_type=Text()), nullable=False),
    Column('sha256', CHAR(length=64), nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='pdm_snapshots_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'::text", name='pdm_snapshots_sha256_check'),
    CheckConstraint("jsonb_typeof(snapshot) = 'object'::text", name='pdm_snapshots_snapshot_check'),
)

product_families = Table('product_families', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('manufacturer_id', UUID(), nullable=True),
    Column('code', TEXT(), nullable=False),
    Column('name', TEXT(), nullable=False),
    Column('description', TEXT(), nullable=True),
    ForeignKeyConstraint(['manufacturer_id'], ['manufacturers.id'], name='product_families_manufacturer_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['manufacturer_id', 'code'], name='product_families_manufacturer_id_code_key'),
)

product_versions = Table('product_versions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('product_id', UUID(), nullable=False),
    Column('component_version_id', UUID(), nullable=False),
    Column('version_no', INTEGER(), nullable=False),
    Column('status', TEXT(), nullable=False),
    Column('lifecycle_status', TEXT(), nullable=False, server_default=text("'AVAILABLE'::text")),
    Column('datasheet_uri', TEXT(), nullable=True),
    Column('specification', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    ForeignKeyConstraint(['component_version_id'], ['component_versions.id'], name='product_versions_component_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['product_id'], ['products.id'], name='product_versions_product_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['product_id', 'version_no'], name='product_versions_product_id_version_no_key'),
    CheckConstraint("lifecycle_status = ANY (ARRAY['AVAILABLE'::text, 'LIMITED'::text, 'DISCONTINUED'::text, 'UNKNOWN'::text])", name='product_versions_lifecycle_status_check'),
    CheckConstraint("jsonb_typeof(specification) = 'object'::text", name='product_versions_specification_check'),
    CheckConstraint("status = ANY (ARRAY['DRAFT'::text, 'PUBLISHED'::text, 'WITHDRAWN'::text])", name='product_versions_status_check'),
    CheckConstraint('version_no > 0', name='product_versions_version_no_check'),
)

products = Table('products', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('manufacturer_id', UUID(), nullable=False),
    Column('family_id', UUID(), nullable=True),
    Column('manufacturer_sku', TEXT(), nullable=False),
    Column('display_name', TEXT(), nullable=False),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    ForeignKeyConstraint(['family_id'], ['product_families.id'], name='products_family_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['manufacturer_id'], ['manufacturers.id'], name='products_manufacturer_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['manufacturer_id', 'manufacturer_sku'], name='products_manufacturer_id_manufacturer_sku_key'),
)

project_cad_assembly_instances = Table('project_cad_assembly_instances', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('assembly_version_id', UUID(), nullable=False),
    Column('stable_key', TEXT(), nullable=False),
    Column('transform', JSONB(astext_type=Text()), nullable=False),
    Column('generation_status', TEXT(), nullable=False, server_default=text("'PENDING'::text")),
    ForeignKeyConstraint(['assembly_version_id'], ['cad_assembly_versions.id'], name='project_cad_assembly_instances_assembly_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='project_cad_assembly_instances_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_revision_id', 'stable_key'], name='project_cad_assembly_instance_project_revision_id_stable_ke_key'),
    CheckConstraint("generation_status = ANY (ARRAY['PENDING'::text, 'READY'::text, 'FAILED'::text, 'STALE'::text])", name='project_cad_assembly_instances_generation_status_check'),
)

project_cad_assembly_members = Table('project_cad_assembly_members', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('assembly_instance_id', UUID(), nullable=False),
    Column('assembly_member_id', UUID(), nullable=False),
    Column('member_cad_model_version_id', UUID(), nullable=False),
    Column('transform', JSONB(astext_type=Text()), nullable=False),
    Column('parameter_values', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['assembly_instance_id'], ['project_cad_assembly_instances.id'], name='project_cad_assembly_members_assembly_instance_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['assembly_member_id'], ['cad_assembly_members.id'], name='project_cad_assembly_members_assembly_member_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['member_cad_model_version_id'], ['cad_model_versions.id'], name='project_cad_assembly_members_member_cad_model_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['assembly_instance_id', 'assembly_member_id'], name='project_cad_assembly_members_assembly_instance_id_assembly__key'),
)

project_cad_instances = Table('project_cad_instances', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('cad_model_version_id', UUID(), nullable=False),
    Column('stable_key', TEXT(), nullable=False),
    Column('supplied_values', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('derived_values', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('evaluated_values', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('generation_status', TEXT(), nullable=False, server_default=text("'PENDING'::text")),
    ForeignKeyConstraint(['cad_model_version_id'], ['cad_model_versions.id'], name='project_cad_instances_cad_model_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='project_cad_instances_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_revision_id', 'stable_key'], name='project_cad_instances_project_revision_id_stable_key_key'),
    CheckConstraint("generation_status = ANY (ARRAY['PENDING'::text, 'READY'::text, 'FAILED'::text, 'STALE'::text])", name='project_cad_instances_generation_status_check'),
)

project_parameter_overrides = Table('project_parameter_overrides', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('target_kind', TEXT(), nullable=False),
    Column('target_code', TEXT(), nullable=False),
    Column('value', JSONB(astext_type=Text()), nullable=False),
    Column('unit_code', TEXT(), nullable=True),
    Column('source_kind', TEXT(), nullable=False),
    Column('provenance', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='project_parameter_overrides_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_revision_id', 'target_kind', 'target_code'], name='project_parameter_overrides_project_revision_id_target_kind_key'),
    CheckConstraint("source_kind = ANY (ARRAY['USER'::text, 'ENGINEER'::text, 'IMPORT'::text])", name='project_parameter_overrides_source_kind_check'),
)

project_requirements = Table('project_requirements', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_id', UUID(), nullable=False),
    Column('project_revision_id', UUID(), nullable=True),
    Column('code', TEXT(), nullable=False),
    Column('operator_code', TEXT(), nullable=False),
    Column('value', JSONB(astext_type=Text()), nullable=False),
    Column('unit_code', TEXT(), nullable=True),
    Column('resolution_status', TEXT(), nullable=False, server_default=text("'UNRESOLVED'::text")),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    ForeignKeyConstraint(['project_id'], ['projects.id'], name='project_requirements_project_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='project_requirements_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_revision_id', 'code'], name='project_requirements_project_revision_id_code_key'),
    CheckConstraint("operator_code = ANY (ARRAY['EQ'::text, 'MIN'::text, 'MAX'::text, 'RANGE'::text, 'IN'::text, 'NOT_IN'::text, 'QUANTITY'::text])", name='project_requirements_operator_code_check'),
    CheckConstraint("resolution_status = ANY (ARRAY['UNRESOLVED'::text, 'RESOLVED'::text, 'CONFLICT'::text, 'WAIVED'::text])", name='project_requirements_resolution_status_check'),
)

project_revisions = Table('project_revisions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_id', UUID(), nullable=False),
    Column('revision_no', INTEGER(), nullable=False),
    Column('parent_revision_id', UUID(), nullable=True),
    Column('status', TEXT(), nullable=False),
    Column('archetype_version_id', UUID(), nullable=True),
    Column('rule_set_version_id', UUID(), nullable=True),
    Column('questionnaire_version_ids', ARRAY(UUID()), nullable=False, server_default=text("'{}'::uuid[]")),
    Column('model_manifest', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('schema_version', INTEGER(), nullable=False, server_default=text('1')),
    Column('content_sha256', CHAR(length=64), nullable=True),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    Column('created_by', TEXT(), nullable=True),
    ForeignKeyConstraint(['archetype_version_id'], ['panel_archetype_versions.id'], name='project_revisions_archetype_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['parent_revision_id'], ['project_revisions.id'], name='project_revisions_parent_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['project_id'], ['projects.id'], name='project_revisions_project_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['rule_set_version_id'], ['rule_set_versions.id'], name='project_revisions_rule_set_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_id', 'id'], name='project_revisions_project_id_id_key'),
    UniqueConstraint(*['project_id', 'revision_no'], name='project_revisions_project_id_revision_no_key'),
    CheckConstraint("content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'::text", name='project_revisions_content_sha256_check'),
    CheckConstraint('revision_no > 0', name='project_revisions_revision_no_check'),
    CheckConstraint("status = ANY (ARRAY['DRAFT'::text, 'PUBLISHED'::text, 'SUPERSEDED'::text])", name='project_revisions_status_check'),
)

projects = Table('projects', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_code', TEXT(), nullable=True),
    Column('name', TEXT(), nullable=False),
    Column('status', TEXT(), nullable=False, server_default=text("'ACTIVE'::text")),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    Column('updated_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    Column('created_by', TEXT(), nullable=True),
    Column('archetype_version_id', UUID(), nullable=True),
    Column('current_revision_id', UUID(), nullable=True),
    Column('configuration', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('lock_version', INTEGER(), nullable=False, server_default=text('1')),
    ForeignKeyConstraint(['id', 'current_revision_id'], ['project_revisions.project_id', 'project_revisions.id'], name='fk_project_current_revision', **{'ondelete': 'RESTRICT', 'use_alter': True}),
    ForeignKeyConstraint(['archetype_version_id'], ['panel_archetype_versions.id'], name='projects_archetype_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_code'], name='projects_project_code_key'),
    CheckConstraint('lock_version > 0', name='projects_lock_version_check'),
    CheckConstraint("status = ANY (ARRAY['ACTIVE'::text, 'ARCHIVED'::text, 'CLOSED'::text])", name='projects_status_check'),
)

provenance = Table('provenance', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_id', UUID(), nullable=True),
    Column('project_revision_id', UUID(), nullable=True),
    Column('subject_kind', TEXT(), nullable=False),
    Column('subject_key', TEXT(), nullable=False),
    Column('source_kind', TEXT(), nullable=False),
    Column('source_ref', TEXT(), nullable=True),
    Column('actor_id', TEXT(), nullable=True),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    Column('details', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['project_id'], ['projects.id'], name='provenance_project_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='provenance_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    CheckConstraint("source_kind = ANY (ARRAY['USER'::text, 'MANUFACTURER'::text, 'ENGINEER'::text, 'RULE'::text, 'OPTIMIZER'::text, 'CAD_GENERATOR'::text, 'IMPORT'::text])", name='provenance_source_kind_check'),
)

question_answers = Table('question_answers', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('session_id', UUID(), nullable=False),
    Column('question_id', UUID(), nullable=False),
    Column('answer_value', JSONB(astext_type=Text()), nullable=False),
    Column('answered_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    Column('actor_id', TEXT(), nullable=True),
    ForeignKeyConstraint(['question_id'], ['questions.id'], name='question_answers_question_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['session_id'], ['questionnaire_sessions.id'], name='question_answers_session_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['session_id', 'question_id'], name='question_answers_session_id_question_id_key'),
)

question_dependencies = Table('question_dependencies', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('question_id', UUID(), nullable=False),
    Column('depends_on_question_id', UUID(), nullable=False),
    Column('operator_code', TEXT(), nullable=False),
    Column('expected_value', JSONB(astext_type=Text()), nullable=False),
    ForeignKeyConstraint(['depends_on_question_id'], ['questions.id'], name='question_dependencies_depends_on_question_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['question_id'], ['questions.id'], name='question_dependencies_question_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['question_id', 'depends_on_question_id'], name='question_dependencies_question_id_depends_on_question_id_key'),
    CheckConstraint('question_id <> depends_on_question_id', name='question_dependencies_check'),
)

question_options = Table('question_options', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('question_id', UUID(), nullable=False),
    Column('option_code', TEXT(), nullable=False),
    Column('label', TEXT(), nullable=False),
    Column('value', JSONB(astext_type=Text()), nullable=False),
    Column('sequence_no', INTEGER(), nullable=False, server_default=text('0')),
    ForeignKeyConstraint(['question_id'], ['questions.id'], name='question_options_question_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['question_id', 'option_code'], name='question_options_question_id_option_code_key'),
)

question_validation_rules = Table('question_validation_rules', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('question_id', UUID(), nullable=False),
    Column('rule_code', TEXT(), nullable=False),
    Column('parameters', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('message', TEXT(), nullable=True),
    ForeignKeyConstraint(['question_id'], ['questions.id'], name='question_validation_rules_question_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['question_id', 'rule_code'], name='question_validation_rules_question_id_rule_code_key'),
)

questionnaire_sections = Table('questionnaire_sections', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('questionnaire_version_id', UUID(), nullable=False),
    Column('code', TEXT(), nullable=False),
    Column('title', TEXT(), nullable=False),
    Column('sequence_no', INTEGER(), nullable=False, server_default=text('0')),
    ForeignKeyConstraint(['questionnaire_version_id'], ['questionnaire_versions.id'], name='questionnaire_sections_questionnaire_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['questionnaire_version_id', 'code'], name='questionnaire_sections_questionnaire_version_id_code_key'),
)

questionnaire_sessions = Table('questionnaire_sessions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_id', UUID(), nullable=False),
    Column('questionnaire_version_id', UUID(), nullable=False),
    Column('status', TEXT(), nullable=False, server_default=text("'IN_PROGRESS'::text")),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    Column('submitted_at', TIMESTAMP(timezone=True), nullable=True),
    ForeignKeyConstraint(['project_id'], ['projects.id'], name='questionnaire_sessions_project_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['questionnaire_version_id'], ['questionnaire_versions.id'], name='questionnaire_sessions_questionnaire_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    CheckConstraint("status = ANY (ARRAY['IN_PROGRESS'::text, 'SUBMITTED'::text, 'SUPERSEDED'::text])", name='questionnaire_sessions_status_check'),
)

questionnaire_versions = Table('questionnaire_versions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('questionnaire_id', UUID(), nullable=False),
    Column('version_no', INTEGER(), nullable=False),
    Column('status', TEXT(), nullable=False),
    Column('schema_version', INTEGER(), nullable=False, server_default=text('1')),
    ForeignKeyConstraint(['questionnaire_id'], ['questionnaires.id'], name='questionnaire_versions_questionnaire_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['questionnaire_id', 'version_no'], name='questionnaire_versions_questionnaire_id_version_no_key'),
    CheckConstraint("status = ANY (ARRAY['DRAFT'::text, 'PUBLISHED'::text, 'WITHDRAWN'::text])", name='questionnaire_versions_status_check'),
    CheckConstraint('version_no > 0', name='questionnaire_versions_version_no_check'),
)

questionnaires = Table('questionnaires', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('code', TEXT(), nullable=False),
    Column('name', TEXT(), nullable=False),
    UniqueConstraint(*['code'], name='questionnaires_code_key'),
)

questions = Table('questions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('questionnaire_version_id', UUID(), nullable=False),
    Column('section_id', UUID(), nullable=True),
    Column('code', TEXT(), nullable=False),
    Column('prompt', TEXT(), nullable=False),
    Column('value_type', TEXT(), nullable=False),
    Column('unit_code', TEXT(), nullable=True),
    Column('required', BOOLEAN(), nullable=False, server_default=text('false')),
    Column('sequence_no', INTEGER(), nullable=False, server_default=text('0')),
    Column('validation', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['questionnaire_version_id'], ['questionnaire_versions.id'], name='questions_questionnaire_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['section_id'], ['questionnaire_sections.id'], name='questions_section_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['questionnaire_version_id', 'code'], name='questions_questionnaire_version_id_code_key'),
    CheckConstraint("value_type = ANY (ARRAY['TEXT'::text, 'INTEGER'::text, 'DECIMAL'::text, 'BOOLEAN'::text, 'SINGLE_SELECT'::text, 'MULTI_SELECT'::text, 'QUANTITY'::text, 'MEASUREMENT'::text, 'OBJECT'::text])", name='questions_value_type_check'),
)

requirement_role_mappings = Table('requirement_role_mappings', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('requirement_code', TEXT(), nullable=False),
    Column('role_code', TEXT(), nullable=False),
    Column('mapping_operator', TEXT(), nullable=False),
    Column('mapping', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    UniqueConstraint(*['requirement_code', 'role_code'], name='requirement_role_mappings_requirement_code_role_code_key'),
)

requirement_sources = Table('requirement_sources', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('requirement_id', UUID(), nullable=False),
    Column('source_kind', TEXT(), nullable=False),
    Column('question_answer_id', UUID(), nullable=True),
    Column('source_ref', TEXT(), nullable=True),
    Column('details', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['question_answer_id'], ['question_answers.id'], name='requirement_sources_question_answer_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['requirement_id'], ['project_requirements.id'], name='requirement_sources_requirement_id_fkey', **{'ondelete': 'RESTRICT'}),
    CheckConstraint("source_kind <> 'ANSWER'::text OR question_answer_id IS NOT NULL", name='requirement_sources_check'),
    CheckConstraint("source_kind = ANY (ARRAY['ANSWER'::text, 'MANUFACTURER'::text, 'ENGINEER'::text, 'RULE'::text, 'OPTIMIZER'::text, 'IMPORT'::text])", name='requirement_sources_source_kind_check'),
)

revision_components = Table('revision_components', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('component_version_id', UUID(), nullable=True),
    Column('product_version_id', UUID(), nullable=True),
    Column('role_code', TEXT(), nullable=False),
    Column('selected_by', TEXT(), nullable=False),
    Column('selection_evidence', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['component_version_id'], ['component_versions.id'], name='revision_components_component_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['product_version_id'], ['product_versions.id'], name='revision_components_product_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='revision_components_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    CheckConstraint('component_version_id IS NOT NULL OR product_version_id IS NOT NULL', name='revision_components_check'),
    CheckConstraint("selected_by = ANY (ARRAY['ENGINEER'::text, 'SELECTOR'::text, 'TEMPLATE'::text, 'IMPORT'::text])", name='revision_components_selected_by_check'),
)

revision_dependencies = Table('revision_dependencies', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('source_kind', TEXT(), nullable=False),
    Column('source_key', TEXT(), nullable=False),
    Column('target_kind', TEXT(), nullable=False),
    Column('target_key', TEXT(), nullable=False),
    Column('dependency_kind', TEXT(), nullable=False),
    Column('input_sha256', CHAR(length=64), nullable=True),
    Column('output_sha256', CHAR(length=64), nullable=True),
    Column('status', TEXT(), nullable=False, server_default=text("'CURRENT'::text")),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='revision_dependencies_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['project_revision_id', 'source_kind', 'source_key', 'target_kind', 'target_key', 'dependency_kind'], name='revision_dependencies_project_revision_id_source_kind_sourc_key'),
    CheckConstraint("status = ANY (ARRAY['CURRENT'::text, 'STALE'::text, 'FAILED'::text])", name='revision_dependencies_status_check'),
)

rule_applicability = Table('rule_applicability', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('rule_version_id', UUID(), nullable=False),
    Column('target_kind', TEXT(), nullable=False),
    Column('predicate', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['rule_version_id'], ['design_rule_versions.id'], name='rule_applicability_rule_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['rule_version_id', 'target_kind'], name='rule_applicability_rule_version_id_target_kind_key'),
)

rule_set_members = Table('rule_set_members', metadata,
    Column('rule_set_version_id', UUID(), primary_key=True, nullable=False),
    Column('rule_version_id', UUID(), primary_key=True, nullable=False),
    Column('enabled', BOOLEAN(), nullable=False, server_default=text('true')),
    ForeignKeyConstraint(['rule_set_version_id'], ['rule_set_versions.id'], name='rule_set_members_rule_set_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['rule_version_id'], ['design_rule_versions.id'], name='rule_set_members_rule_version_id_fkey', **{'ondelete': 'RESTRICT'}),
)

rule_set_versions = Table('rule_set_versions', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('rule_set_id', UUID(), nullable=False),
    Column('version_no', INTEGER(), nullable=False),
    Column('status', TEXT(), nullable=False),
    ForeignKeyConstraint(['rule_set_id'], ['rule_sets.id'], name='rule_set_versions_rule_set_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['rule_set_id', 'version_no'], name='rule_set_versions_rule_set_id_version_no_key'),
    CheckConstraint("status = ANY (ARRAY['DRAFT'::text, 'PUBLISHED'::text, 'WITHDRAWN'::text])", name='rule_set_versions_status_check'),
    CheckConstraint('version_no > 0', name='rule_set_versions_version_no_check'),
)

rule_sets = Table('rule_sets', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('code', TEXT(), nullable=False),
    Column('name', TEXT(), nullable=False),
    UniqueConstraint(*['code'], name='rule_sets_code_key'),
)

template_component_roles = Table('template_component_roles', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('template_version_id', UUID(), nullable=False),
    Column('role_code', TEXT(), nullable=False),
    Column('component_category', TEXT(), nullable=True),
    Column('required_properties', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['template_version_id'], ['electrical_template_versions.id'], name='template_component_roles_template_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['template_version_id', 'role_code'], name='template_component_roles_template_version_id_role_code_key'),
)

template_connections = Table('template_connections', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('template_version_id', UUID(), nullable=False),
    Column('from_template_terminal_id', UUID(), nullable=False),
    Column('to_template_terminal_id', UUID(), nullable=False),
    Column('connection_code', TEXT(), nullable=False),
    Column('connection_type', TEXT(), nullable=False),
    Column('directionality', TEXT(), nullable=False, server_default=text("'UNDIRECTED'::text")),
    Column('properties', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    ForeignKeyConstraint(['from_template_terminal_id'], ['template_terminals.id'], name='template_connections_from_template_terminal_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['template_version_id'], ['electrical_template_versions.id'], name='template_connections_template_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['to_template_terminal_id'], ['template_terminals.id'], name='template_connections_to_template_terminal_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['template_version_id', 'connection_code'], name='template_connections_template_version_id_connection_code_key'),
    CheckConstraint('from_template_terminal_id <> to_template_terminal_id', name='template_connections_check'),
    CheckConstraint("directionality = ANY (ARRAY['DIRECTED'::text, 'UNDIRECTED'::text])", name='template_connections_directionality_check'),
)

template_terminals = Table('template_terminals', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('template_role_id', UUID(), nullable=False),
    Column('terminal_code', TEXT(), nullable=False),
    Column('terminal_role', TEXT(), nullable=True),
    ForeignKeyConstraint(['template_role_id'], ['template_component_roles.id'], name='template_terminals_template_role_id_fkey', **{'ondelete': 'RESTRICT'}),
    UniqueConstraint(*['template_role_id', 'terminal_code'], name='template_terminals_template_role_id_terminal_code_key'),
)

validation_results = Table('validation_results', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('validation_run_id', UUID(), nullable=False),
    Column('rule_version_id', UUID(), nullable=True),
    Column('rule_code', TEXT(), nullable=False),
    Column('result_status', TEXT(), nullable=False),
    Column('affected_entities', JSONB(astext_type=Text()), nullable=False, server_default=text("'[]'::jsonb")),
    Column('measured_values', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('message', TEXT(), nullable=False),
    Column('evidence', JSONB(astext_type=Text()), nullable=False, server_default=text("'{}'::jsonb")),
    Column('created_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    ForeignKeyConstraint(['rule_version_id'], ['design_rule_versions.id'], name='validation_results_rule_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['validation_run_id'], ['validation_runs.id'], name='validation_results_validation_run_id_fkey', **{'ondelete': 'RESTRICT'}),
    CheckConstraint("result_status = ANY (ARRAY['PASS'::text, 'FAIL'::text, 'WARNING'::text, 'SKIPPED'::text])", name='validation_results_result_status_check'),
)

validation_runs = Table('validation_runs', metadata,
    Column('id', UUID(), primary_key=True, nullable=False, server_default=text('gen_random_uuid()')),
    Column('project_revision_id', UUID(), nullable=False),
    Column('rule_set_version_id', UUID(), nullable=True),
    Column('engine_name', TEXT(), nullable=False),
    Column('engine_version', TEXT(), nullable=False),
    Column('status', TEXT(), nullable=False),
    Column('input_sha256', CHAR(length=64), nullable=True),
    Column('started_at', TIMESTAMP(timezone=True), nullable=False, server_default=text('now()')),
    Column('completed_at', TIMESTAMP(timezone=True), nullable=True),
    ForeignKeyConstraint(['project_revision_id'], ['project_revisions.id'], name='validation_runs_project_revision_id_fkey', **{'ondelete': 'RESTRICT'}),
    ForeignKeyConstraint(['rule_set_version_id'], ['rule_set_versions.id'], name='validation_runs_rule_set_version_id_fkey', **{'ondelete': 'RESTRICT'}),
    CheckConstraint('completed_at IS NULL OR completed_at >= started_at', name='validation_runs_check'),
    CheckConstraint("status = ANY (ARRAY['RUNNING'::text, 'PASSED'::text, 'FAILED'::text, 'COMPLETED_WITH_WARNINGS'::text])", name='validation_runs_status_check'),
)

Index('ix_cad_assets_version_role', cad_assets.c['cad_model_version_id'], cad_assets.c['asset_role'], unique=False, postgresql_include=[])
Index('ix_terminal_component_role', component_terminals.c['component_version_id'], component_terminals.c['electrical_role'], unique=False, postgresql_include=[])
Index('ix_component_version_rating', component_versions.c['rated_current_a'], component_versions.c['rated_voltage_v'], component_versions.c['breaking_capacity_ka'], unique=False, postgresql_include=[])
Index('ix_component_catalog_category', components.c['category_code'], components.c['component_kind'], unique=False, postgresql_include=[])
Index('ix_generated_artifact_revision_type', generated_artifacts.c['project_revision_id'], generated_artifacts.c['artifact_type'], generated_artifacts.c['created_at'].desc(), unique=False, postgresql_include=[])
Index('ix_pdm_component_cem', pdm_component_instances.c['cem_component_instance_id'], unique=False, postgresql_include=[])
Index('ix_product_versions_component', product_versions.c['component_version_id'], product_versions.c['status'], unique=False, postgresql_include=[])
Index('uq_project_current_requirement', project_requirements.c['project_id'], project_requirements.c['code'], unique=True, postgresql_where=text('(project_revision_id IS NULL)'), postgresql_include=[])
Index('ix_project_revision_latest', project_revisions.c['project_id'], project_revisions.c['revision_no'].desc(), unique=False, postgresql_include=[])
Index('ix_provenance_subject', provenance.c['subject_kind'], provenance.c['subject_key'], unique=False, postgresql_include=[])
Index('ix_revision_dependency_target', revision_dependencies.c['project_revision_id'], revision_dependencies.c['target_kind'], revision_dependencies.c['target_key'], unique=False, postgresql_include=[])
Index('ix_validation_results_run_status', validation_results.c['validation_run_id'], validation_results.c['result_status'], unique=False, postgresql_include=[])
Base = declarative_base(metadata=metadata)

class ArchetypeDefaults(Base):
    __table__ = archetype_defaults

class ArchetypeElectricalTemplates(Base):
    __table__ = archetype_electrical_templates

class ArchetypeModules(Base):
    __table__ = archetype_modules

class ArchetypeQuestionnaires(Base):
    __table__ = archetype_questionnaires

class CadAssemblies(Base):
    __table__ = cad_assemblies

class CadAssemblyMembers(Base):
    __table__ = cad_assembly_members

class CadAssemblyVersions(Base):
    __table__ = cad_assembly_versions

class CadAssets(Base):
    __table__ = cad_assets

class CadFeatures(Base):
    __table__ = cad_features

class CadModelVersions(Base):
    __table__ = cad_model_versions

class CadModels(Base):
    __table__ = cad_models

class CadParameterDefinitions(Base):
    __table__ = cad_parameter_definitions

class CemComponentInstances(Base):
    __table__ = cem_component_instances

class CemConductors(Base):
    __table__ = cem_conductors

class CemNetTerminals(Base):
    __table__ = cem_net_terminals

class CemNets(Base):
    __table__ = cem_nets

class CemSnapshots(Base):
    __table__ = cem_snapshots

class CemTerminalInstances(Base):
    __table__ = cem_terminal_instances

class ComponentAccessories(Base):
    __table__ = component_accessories

class ComponentCadModels(Base):
    __table__ = component_cad_models

class ComponentClearances(Base):
    __table__ = component_clearances

class ComponentDocuments(Base):
    __table__ = component_documents

class ComponentMounting(Base):
    __table__ = component_mounting

class ComponentTerminals(Base):
    __table__ = component_terminals

class ComponentThermalSpecs(Base):
    __table__ = component_thermal_specs

class ComponentVersions(Base):
    __table__ = component_versions

class Components(Base):
    __table__ = components

class DesignRuleVersions(Base):
    __table__ = design_rule_versions

class DesignRules(Base):
    __table__ = design_rules

class ElectricalTemplateVersions(Base):
    __table__ = electrical_template_versions

class ElectricalTemplates(Base):
    __table__ = electrical_templates

class FunctionalModuleVersions(Base):
    __table__ = functional_module_versions

class FunctionalModules(Base):
    __table__ = functional_modules

class GeneratedArtifacts(Base):
    __table__ = generated_artifacts

class Manufacturers(Base):
    __table__ = manufacturers

class ModuleRoleRequirements(Base):
    __table__ = module_role_requirements

class PanelArchetypeVersions(Base):
    __table__ = panel_archetype_versions

class PanelArchetypes(Base):
    __table__ = panel_archetypes

class PdmClearanceRegions(Base):
    __table__ = pdm_clearance_regions

class PdmComponentInstances(Base):
    __table__ = pdm_component_instances

class PdmEnclosures(Base):
    __table__ = pdm_enclosures

class PdmMountingStructures(Base):
    __table__ = pdm_mounting_structures

class PdmPlacements(Base):
    __table__ = pdm_placements

class PdmRoutes(Base):
    __table__ = pdm_routes

class PdmSnapshots(Base):
    __table__ = pdm_snapshots

class ProductFamilies(Base):
    __table__ = product_families

class ProductVersions(Base):
    __table__ = product_versions

class Products(Base):
    __table__ = products

class ProjectCadAssemblyInstances(Base):
    __table__ = project_cad_assembly_instances

class ProjectCadAssemblyMembers(Base):
    __table__ = project_cad_assembly_members

class ProjectCadInstances(Base):
    __table__ = project_cad_instances

class ProjectParameterOverrides(Base):
    __table__ = project_parameter_overrides

class ProjectRequirements(Base):
    __table__ = project_requirements

class ProjectRevisions(Base):
    __table__ = project_revisions

class Projects(Base):
    __table__ = projects

class Provenance(Base):
    __table__ = provenance

class QuestionAnswers(Base):
    __table__ = question_answers

class QuestionDependencies(Base):
    __table__ = question_dependencies

class QuestionOptions(Base):
    __table__ = question_options

class QuestionValidationRules(Base):
    __table__ = question_validation_rules

class QuestionnaireSections(Base):
    __table__ = questionnaire_sections

class QuestionnaireSessions(Base):
    __table__ = questionnaire_sessions

class QuestionnaireVersions(Base):
    __table__ = questionnaire_versions

class Questionnaires(Base):
    __table__ = questionnaires

class Questions(Base):
    __table__ = questions

class RequirementRoleMappings(Base):
    __table__ = requirement_role_mappings

class RequirementSources(Base):
    __table__ = requirement_sources

class RevisionComponents(Base):
    __table__ = revision_components

class RevisionDependencies(Base):
    __table__ = revision_dependencies

class RuleApplicability(Base):
    __table__ = rule_applicability

class RuleSetMembers(Base):
    __table__ = rule_set_members

class RuleSetVersions(Base):
    __table__ = rule_set_versions

class RuleSets(Base):
    __table__ = rule_sets

class TemplateComponentRoles(Base):
    __table__ = template_component_roles

class TemplateConnections(Base):
    __table__ = template_connections

class TemplateTerminals(Base):
    __table__ = template_terminals

class ValidationResults(Base):
    __table__ = validation_results

class ValidationRuns(Base):
    __table__ = validation_runs

Projects.revisions = relationship(ProjectRevisions, foreign_keys=[project_revisions.c.project_id], viewonly=True, order_by=project_revisions.c.revision_no)
CemComponentInstances.terminals = relationship(CemTerminalInstances, viewonly=True)
CadModelVersions.parameters = relationship(CadParameterDefinitions, viewonly=True)
ValidationRuns.results = relationship(ValidationResults, viewonly=True)
