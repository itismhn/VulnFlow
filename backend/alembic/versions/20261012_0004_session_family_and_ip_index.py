"""session family for refresh tokens, audit ip index

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-12 19:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('refresh_tokens', sa.Column('family_id', sa.Uuid(), nullable=True))
    op.execute("UPDATE refresh_tokens SET family_id = id")
    op.alter_column('refresh_tokens', 'family_id', nullable=False)
    op.create_index(op.f('ix_refresh_tokens_family_id'), 'refresh_tokens', ['family_id'], unique=False)
    op.create_index('ix_audit_logs_ip_created_at', 'audit_logs', ['ip', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_audit_logs_ip_created_at', table_name='audit_logs')
    op.drop_index(op.f('ix_refresh_tokens_family_id'), table_name='refresh_tokens')
    op.drop_column('refresh_tokens', 'family_id')
