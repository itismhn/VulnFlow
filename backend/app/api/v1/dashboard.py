from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import DB, require
from app.core.permissions import Perm
from app.models import User
from app.schemas.finding import FindingFilters
from app.services.dashboard import Dashboard, build_dashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=Dashboard)
def dashboard(
    user: Annotated[User, Depends(require(Perm.FINDINGS_READ))],
    db: DB,
    network_id: Annotated[list[int] | None, Query()] = None,
    zone: Annotated[list[str] | None, Query()] = None,
    days: Annotated[int, Query(ge=28, le=730)] = 180,
) -> Dashboard:
    return build_dashboard(db, user, FindingFilters(network_id=network_id, zone=zone), days)
