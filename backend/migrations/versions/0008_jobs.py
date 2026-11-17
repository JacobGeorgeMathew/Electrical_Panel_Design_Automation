"""Durable execution intent and renewable, attempt-fenced job leases.

This is queue storage only. Existing CAD exports remain on their legacy worker
until the durable runner and result attachment are integrated.
"""
from alembic import op

revision = '0008_jobs'
down_revision = '0007_stage_results'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE jobs (
            id uuid PRIMARY KEY,
            execution_key text NOT NULL UNIQUE CHECK (length(execution_key) > 0),
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
            document_id text NOT NULL,
            base_sequence bigint NOT NULL CHECK (base_sequence >= 0),
            revision_id uuid,
            kind text NOT NULL CHECK (length(kind) > 0),
            input_signature char(64) NOT NULL CHECK (input_signature ~ '^[0-9a-f]{64}$'),
            inputs jsonb NOT NULL CHECK (jsonb_typeof(inputs) = 'object'),
            artifact_intent jsonb NOT NULL CHECK (jsonb_typeof(artifact_intent) = 'object'),
            state text NOT NULL DEFAULT 'QUEUED' CHECK
                (state IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
            attempts integer NOT NULL DEFAULT 0,
            max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 100),
            lease_owner text,
            lease_token uuid UNIQUE,
            lease_expires_at timestamptz,
            result jsonb CHECK (jsonb_typeof(result) = 'object'),
            error jsonb CHECK (jsonb_typeof(error) = 'object'),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            started_at timestamptz,
            completed_at timestamptz,
            CONSTRAINT fk_jobs_document FOREIGN KEY (project_id, document_id)
                REFERENCES design_documents(project_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_jobs_revision FOREIGN KEY (project_id, revision_id)
                REFERENCES project_revisions(project_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_jobs_attempts CHECK (attempts BETWEEN 0 AND max_attempts),
            CONSTRAINT ck_jobs_queued CHECK (state <> 'QUEUED' OR attempts < max_attempts),
            CONSTRAINT ck_jobs_started CHECK (
                (attempts = 0) = (started_at IS NULL) AND
                (state NOT IN ('RUNNING', 'SUCCEEDED') OR attempts > 0)),
            CONSTRAINT ck_jobs_lease CHECK (
                (state = 'RUNNING' AND lease_owner IS NOT NULL AND length(lease_owner) > 0
                    AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
                OR (state <> 'RUNNING' AND lease_owner IS NULL
                    AND lease_token IS NULL AND lease_expires_at IS NULL)),
            CONSTRAINT ck_jobs_completed CHECK (
                (state IN ('SUCCEEDED', 'FAILED', 'CANCELLED')) = (completed_at IS NOT NULL)),
            CONSTRAINT ck_jobs_result CHECK (result IS NULL OR state = 'SUCCEEDED'),
            CONSTRAINT ck_jobs_error CHECK ((state = 'FAILED') = (error IS NOT NULL))
        );
        CREATE INDEX ix_jobs_queue ON jobs (created_at, id) WHERE state = 'QUEUED';
        CREATE INDEX ix_jobs_expiry ON jobs (lease_expires_at, id) WHERE state = 'RUNNING';
        CREATE INDEX ix_jobs_document ON jobs (document_id, created_at DESC);
    """)


def downgrade():
    raise RuntimeError('Use a data-preserving forward migration for durable jobs.')
