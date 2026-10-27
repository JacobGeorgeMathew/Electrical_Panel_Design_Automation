"""Working project state and optimistic concurrency; existing history is retained."""
from alembic import op

revision = "0002_app"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""
      ALTER TABLE projects ADD COLUMN archetype_version_id uuid REFERENCES panel_archetype_versions(id) ON DELETE RESTRICT;
      ALTER TABLE projects ADD COLUMN current_revision_id uuid;
      ALTER TABLE projects ADD COLUMN configuration jsonb NOT NULL DEFAULT '{}'::jsonb;
      ALTER TABLE projects ADD COLUMN lock_version integer NOT NULL DEFAULT 1 CHECK(lock_version > 0);
      ALTER TABLE projects ADD CONSTRAINT fk_project_current_revision FOREIGN KEY(id,current_revision_id)
        REFERENCES project_revisions(project_id,id) ON DELETE RESTRICT;
      CREATE UNIQUE INDEX uq_project_current_requirement ON project_requirements(project_id,code) WHERE project_revision_id IS NULL;
      ALTER TABLE cem_conductors ADD COLUMN from_terminal_instance_id uuid REFERENCES cem_terminal_instances(id) ON DELETE RESTRICT;
      ALTER TABLE cem_conductors ADD COLUMN to_terminal_instance_id uuid REFERENCES cem_terminal_instances(id) ON DELETE RESTRICT;
      UPDATE projects p SET archetype_version_id=r.archetype_version_id, current_revision_id=r.id
      FROM project_revisions r WHERE r.project_id=p.id AND r.revision_no=(
        SELECT max(r2.revision_no) FROM project_revisions r2 WHERE r2.project_id=p.id);
    """)

def downgrade():
    raise RuntimeError("Use a reviewed data-preserving migration instead of deleting project state.")
