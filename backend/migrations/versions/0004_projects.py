"""Project metadata, saved editor state, and versioned recovery checkpoints."""
from alembic import op

revision = '0004_projects'
down_revision = '0003_constraints'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE projects ADD COLUMN description text NOT NULL DEFAULT '';
        ALTER TABLE projects ADD COLUMN location text NOT NULL DEFAULT '';
        ALTER TABLE projects ADD COLUMN last_opened_at timestamptz;
        ALTER TABLE projects ADD COLUMN deleted_at timestamptz;
        ALTER TABLE projects ADD COLUMN workspace jsonb NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE projects ADD COLUMN recovery jsonb;
        ALTER TABLE projects ADD COLUMN recovery_version integer NOT NULL DEFAULT 0;
        CREATE INDEX ix_projects_recent ON projects(last_opened_at DESC) WHERE deleted_at IS NULL;
    """)


def downgrade():
    raise RuntimeError('Use a data-preserving forward migration for project documents.')
