"""unique network names (case-insensitive)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09 10:00:00
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing duplicates keep the oldest name; later ones get their CIDR appended
    op.execute(
        """
        UPDATE networks n SET name = left(n.name, 128 - length(n.cidr::text) - 3) || ' (' || n.cidr::text || ')'
        WHERE n.id NOT IN (SELECT min(id) FROM networks GROUP BY lower(name))
        """
    )
    op.execute("CREATE UNIQUE INDEX uq_networks_name_lower ON networks (lower(name))")


def downgrade() -> None:
    op.execute("DROP INDEX uq_networks_name_lower")
