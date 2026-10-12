"""Runtime settings stored in the database, with typed defaults."""

from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSetting

DEFAULTS: dict[str, Any] = {
    # An admin may approve their own risk-acceptance request
    "risk_self_approval": False,
    # Longest allowed acceptance, in days
    "risk_max_days": 365,
    # Audit rows older than this are deleted by the daily job (0 = keep forever)
    "audit_retention_days": 730,
    # Defaults for new report templates
    "branding_company": "",
    "branding_classification": "CONFIDENTIAL - INTERNAL",
}


def get_setting(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    return row.value if row is not None else DEFAULTS[key]


def all_settings(db: Session) -> dict[str, Any]:
    stored = {r.key: r.value for r in db.query(AppSetting).filter(AppSetting.key.in_(DEFAULTS))}
    return {**DEFAULTS, **stored}


def set_settings(db: Session, values: dict[str, Any], user_id: int | None) -> dict[str, Any]:
    for key, value in values.items():
        if key not in DEFAULTS:
            continue
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value, updated_by_id=user_id))
        else:
            row.value = value
            row.updated_by_id = user_id
    db.flush()
    return all_settings(db)
