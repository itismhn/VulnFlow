"""Keep the exact template settings used by each report job."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_jobs", sa.Column("template_snapshot", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("report_jobs", "template_snapshot")
