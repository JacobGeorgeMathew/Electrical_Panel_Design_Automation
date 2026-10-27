"""Frozen baseline of the existing 78-table PostgreSQL design."""
from pathlib import Path
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.get_bind().exec_driver_sql(Path(__file__).with_name("0001_baseline.sql").read_text(encoding="utf-8"))

def downgrade():
    raise RuntimeError("Baseline removal would destroy engineering history; restore a backup explicitly.")
