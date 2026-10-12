"""Row-level scoping: a scope-restricted user only sees assets inside their networks.

Every query that returns assets, findings, or aggregates over them must pass
through `scope_assets`, so scope cannot be forgotten in one endpoint.
"""

from typing import Any

from sqlalchemy import ColumnElement, and_, exists, select, true
from sqlalchemy.orm import aliased

from app.models import Asset, Network, User, user_networks


def asset_scope_clause(user: User) -> ColumnElement[bool]:
    if not user.scope_restricted:
        return true()
    # Aliased so it never correlates with a Network already joined by the outer query
    granted = aliased(Network)
    return exists(
        select(1)
        .select_from(user_networks.join(granted, granted.id == user_networks.c.network_id))
        .where(
            and_(
                user_networks.c.user_id == user.id,
                Asset.ip.op("<<=")(granted.cidr),
            )
        )
    )


def scope_assets(stmt: Any, user: User) -> Any:
    """Apply the user's scope to a statement that already involves the Asset entity."""
    if not user.scope_restricted:
        return stmt
    return stmt.where(asset_scope_clause(user))
