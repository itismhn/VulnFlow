from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session


def reassign_assets(db: Session, asset_ids: Sequence[int] | None = None) -> None:
    """Point each asset at the most specific network (longest prefix) containing its IP."""
    sql = """
        UPDATE assets a SET network_id = (
            SELECT n.id FROM networks n
            WHERE a.ip <<= n.cidr
            ORDER BY masklen(n.cidr) DESC
            LIMIT 1
        )
    """
    if asset_ids is None:
        db.execute(text(sql))
    elif asset_ids:
        db.execute(text(sql + " WHERE a.id = ANY(:ids)"), {"ids": list(asset_ids)})
