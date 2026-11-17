"""Disposable stage cache and document-local validity clocks, separate from history.

Results are append-only. An explicit execution may append a replacement for a
corrupt entry; no cache operation updates revision snapshots or shared assets.
"""
from alembic import op

revision = '0007_stage_results'
down_revision = '0006_operations'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE stage_results (
            id uuid PRIMARY KEY,
            stage_id text NOT NULL CHECK (stage_id IN
                ('requirements', 'calculations', 'selection', 'connectivity', 'schematic',
                 'placement', 'routes', 'physical_validation', 'bom', 'cad')),
            adapter text NOT NULL CHECK (length(adapter) > 0),
            input_signature char(64) NOT NULL CHECK (input_signature ~ '^[0-9a-f]{64}$'),
            signature jsonb NOT NULL CHECK (jsonb_typeof(signature) = 'object'),
            result jsonb NOT NULL CHECK (jsonb_typeof(result) = 'object'),
            assets jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(assets) = 'array'),
            result_sha256 char(64) NOT NULL CHECK (result_sha256 ~ '^[0-9a-f]{64}$'),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_stage_results_reference UNIQUE (id, adapter, input_signature),
            CONSTRAINT ck_stage_results_identity CHECK (
                signature @> jsonb_build_object('adapter', adapter, 'stage_id', stage_id)
            )
        );
        CREATE INDEX ix_stage_results_signature ON stage_results
            (input_signature, created_at DESC, id DESC);

        CREATE TABLE document_stage_states (
            document_id text NOT NULL REFERENCES design_documents(id) ON DELETE RESTRICT,
            adapter text NOT NULL,
            stage_id text NOT NULL CHECK (stage_id IN
                ('requirements', 'calculations', 'selection', 'connectivity', 'schematic',
                 'placement', 'routes', 'physical_validation', 'bom', 'cad')),
            document_sequence bigint NOT NULL CHECK (document_sequence >= 0),
            input_version bigint NOT NULL CHECK (input_version > 0),
            output_version bigint NOT NULL DEFAULT 0 CHECK (output_version >= 0),
            input_signature char(64) NOT NULL CHECK (input_signature ~ '^[0-9a-f]{64}$'),
            output_signature char(64) CHECK (output_signature ~ '^[0-9a-f]{64}$'),
            result_id uuid,
            status text NOT NULL CHECK (status IN ('DIRTY', 'BLOCKED', 'FAILED', 'VALID')),
            integrity text NOT NULL CHECK (integrity IN ('MISSING', 'VALID', 'CORRUPT')),
            blocked_by jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(blocked_by) = 'array'),
            failure_code text,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (document_id, adapter),
            CONSTRAINT fk_document_stage_result FOREIGN KEY (result_id, adapter, output_signature)
                REFERENCES stage_results(id, adapter, input_signature) ON DELETE RESTRICT,
            CONSTRAINT ck_document_stage_output CHECK (
                (result_id IS NULL AND output_signature IS NULL AND output_version = 0)
                OR (result_id IS NOT NULL AND output_signature IS NOT NULL AND output_version > 0)
            ),
            CONSTRAINT ck_document_stage_valid CHECK (
                status <> 'VALID' OR (integrity = 'VALID' AND result_id IS NOT NULL
                    AND output_signature = input_signature)
            ),
            CONSTRAINT ck_document_stage_blocked CHECK (
                (status = 'BLOCKED') = (jsonb_array_length(blocked_by) > 0)
            ),
            CONSTRAINT ck_document_stage_failed CHECK (
                (status = 'FAILED') = (failure_code IS NOT NULL)
            )
        );
    """)


def downgrade():
    raise RuntimeError('Use a data-preserving forward migration for stage cache records.')
