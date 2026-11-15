"""Working documents and frozen revision outputs, without converting history.

Absence of an output manifest means legacy/incomplete output storage. This
migration deliberately creates no documents, manifests or replacement snapshots
for existing projects. Publication and compatibility conversion are separate
application operations. JSON integrity and contract validation belong at those
boundaries; these tables enforce storage shape, ownership and version domains.
"""
from alembic import op

revision = '0005_design_documents'
down_revision = '0004_projects'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE design_documents (
            id text PRIMARY KEY CHECK (length(id) > 0),
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
            panel_id text NOT NULL CHECK (length(panel_id) > 0),
            schema_version text NOT NULL DEFAULT '1.0.0' CHECK (length(schema_version) > 0),
            document_sequence bigint NOT NULL DEFAULT 0 CHECK (document_sequence >= 0),
            base_revision_id uuid,
            document jsonb NOT NULL CHECK (jsonb_typeof(document) = 'object'),
            content_sha256 char(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_design_documents_project UNIQUE (project_id),
            CONSTRAINT uq_design_documents_project_id UNIQUE (project_id, id),
            CONSTRAINT fk_design_documents_base_revision FOREIGN KEY (project_id, base_revision_id)
                REFERENCES project_revisions(project_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_design_documents_metadata CHECK (
                document @> jsonb_build_object('document_id', id, 'project_id', project_id::text,
                    'panel_id', panel_id, 'schema_version', schema_version,
                    'document_sequence', document_sequence)
            )
        );

        CREATE TABLE design_document_snapshots (
            document_id text NOT NULL REFERENCES design_documents(id) ON DELETE RESTRICT,
            model_kind text NOT NULL CHECK (model_kind IN ('REQUIREMENTS', 'CEM', 'PDM', 'SCHEMATIC')),
            schema_version integer NOT NULL CHECK (schema_version > 0),
            sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot) = 'object'),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (document_id, model_kind, schema_version, sha256)
        );

        CREATE TABLE revision_output_manifests (
            project_revision_id uuid PRIMARY KEY,
            project_id uuid NOT NULL,
            schema_version text NOT NULL DEFAULT '1.0.0' CHECK (length(schema_version) > 0),
            source_document_id text NOT NULL,
            source_document_sequence bigint NOT NULL CHECK (source_document_sequence >= 0),
            source_document_sha256 char(64) NOT NULL CHECK (source_document_sha256 ~ '^[0-9a-f]{64}$'),
            manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest) = 'object'),
            sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_revision_output_manifests_revision FOREIGN KEY (project_id, project_revision_id)
                REFERENCES project_revisions(project_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_revision_output_manifests_document FOREIGN KEY (project_id, source_document_id)
                REFERENCES design_documents(project_id, id) ON DELETE RESTRICT
        );

        CREATE TABLE revision_output_snapshots (
            project_revision_id uuid NOT NULL REFERENCES revision_output_manifests(project_revision_id) ON DELETE RESTRICT,
            output_kind text NOT NULL CHECK (output_kind IN
                ('DOCUMENT', 'REQUIREMENTS', 'CEM', 'PDM', 'SCHEMATIC', 'BOM', 'CAD', 'VALIDATION', 'INPUTS_AND_PINS')),
            schema_version integer NOT NULL CHECK (schema_version > 0),
            snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot) IN ('object', 'array')),
            sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (project_revision_id, output_kind)
        );
    """)


def downgrade():
    raise RuntimeError('Use a data-preserving forward migration for design documents and revision outputs.')
