"""Append-only operation batches, ordered members and durable retry receipts.

No existing document, snapshot, revision or asset is rewritten. State references
resolve to retained document snapshots, including intermediate member states.
"""
from alembic import op

revision = '0006_operations'
down_revision = '0005_design_documents'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE operation_batches (
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
            id uuid NOT NULL,
            document_id text NOT NULL,
            schema_version text NOT NULL CHECK (schema_version = '1.0.0'),
            idempotency_key text NOT NULL CHECK (
                length(idempotency_key) BETWEEN 1 AND 200
                AND idempotency_key = btrim(idempotency_key)
                AND idempotency_key !~ '[[:cntrl:]]'),
            payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
            payload_sha256 char(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
            base_sequence bigint NOT NULL CHECK (base_sequence >= 0),
            document_sequence bigint NOT NULL,
            base_lock_version bigint NOT NULL CHECK (base_lock_version >= 1),
            lock_version bigint NOT NULL,
            before_state jsonb NOT NULL CHECK (jsonb_typeof(before_state) = 'object'),
            after_state jsonb NOT NULL CHECK (jsonb_typeof(after_state) = 'object'),
            before_content_sha256 char(64) NOT NULL CHECK (before_content_sha256 ~ '^[0-9a-f]{64}$'),
            after_content_sha256 char(64) NOT NULL CHECK (after_content_sha256 ~ '^[0-9a-f]{64}$'),
            operation_count integer NOT NULL CHECK (operation_count BETWEEN 1 AND 100),
            result jsonb NOT NULL CHECK (jsonb_typeof(result) = 'object'),
            result_sha256 char(64) NOT NULL CHECK (result_sha256 ~ '^[0-9a-f]{64}$'),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (project_id, id),
            CONSTRAINT uq_operation_batches_key UNIQUE (project_id, idempotency_key),
            CONSTRAINT uq_operation_batches_document UNIQUE (project_id, id, document_id),
            CONSTRAINT fk_operation_batches_document FOREIGN KEY (project_id, document_id)
                REFERENCES design_documents(project_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_operation_batches_versions CHECK (
                (document_sequence = base_sequence AND lock_version = base_lock_version)
                OR (document_sequence = base_sequence + 1 AND lock_version = base_lock_version + 1)
            )
        );

        CREATE TABLE document_operations (
            project_id uuid NOT NULL,
            sequence bigint NOT NULL CHECK (sequence > 0),
            operation_id uuid NOT NULL,
            batch_id uuid NOT NULL,
            batch_index integer NOT NULL CHECK (batch_index BETWEEN 0 AND 99),
            document_id text NOT NULL,
            operation_type text NOT NULL CHECK (length(operation_type) > 0),
            origin jsonb NOT NULL CHECK (jsonb_typeof(origin) = 'object'),
            payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
            payload_sha256 char(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
            model_kind text NOT NULL,
            schema_version integer NOT NULL CHECK (schema_version > 0),
            before_sha256 char(64) NOT NULL,
            after_sha256 char(64) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (project_id, sequence),
            CONSTRAINT uq_document_operations_id UNIQUE (project_id, operation_id),
            CONSTRAINT uq_document_operations_batch_index UNIQUE (project_id, batch_id, batch_index),
            CONSTRAINT fk_document_operations_batch FOREIGN KEY (project_id, batch_id, document_id)
                REFERENCES operation_batches(project_id, id, document_id) ON DELETE RESTRICT,
            CONSTRAINT fk_document_operations_before FOREIGN KEY
                (document_id, model_kind, schema_version, before_sha256)
                REFERENCES design_document_snapshots(document_id, model_kind, schema_version, sha256)
                ON DELETE RESTRICT,
            CONSTRAINT fk_document_operations_after FOREIGN KEY
                (document_id, model_kind, schema_version, after_sha256)
                REFERENCES design_document_snapshots(document_id, model_kind, schema_version, sha256)
                ON DELETE RESTRICT
        );
    """)


def downgrade():
    raise RuntimeError('Use a data-preserving forward migration for operation history.')
