from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import audit
from app.core.deps import DB, CurrentUser, require
from app.core.permissions import Perm
from app.models import User
from app.schemas.finding import FiltersQuery
from app.schemas.workflow import SettingsOut, SettingsUpdate
from app.services.app_settings import all_settings, set_settings
from app.services.metrics import Metrics, build_metrics

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsOut)
def get_settings(_: CurrentUser, db: DB) -> SettingsOut:
    return SettingsOut(**all_settings(db))


@router.put("/settings", response_model=SettingsOut)
def update_settings(
    body: SettingsUpdate,
    request: Request,
    user: Annotated[User, Depends(require(Perm.SETTINGS_MANAGE))],
    db: DB,
) -> SettingsOut:
    changes = body.model_dump(exclude_none=True)
    values = set_settings(db, changes, user.id)
    audit(db, "settings.updated", request=request, user=user, entity_type="settings", details=changes)
    db.commit()
    return SettingsOut(**values)


@router.get("/metrics", response_model=Metrics)
def metrics(
    user: Annotated[User, Depends(require(Perm.FINDINGS_READ))],
    db: DB,
    filters: FiltersQuery,
    weeks: Annotated[int, Query(ge=4, le=52)] = 12,
) -> Metrics:
    return build_metrics(db, user, filters, weeks)
