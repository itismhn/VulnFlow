from fastapi import APIRouter

from app.api.v1 import (
    assets,
    auth,
    dashboard,
    findings,
    misc,
    networks,
    notifications,
    reports,
    risk,
    scans,
    settings,
    sla,
    suppressions,
    users,
    views,
    vulnerabilities,
)

api_router = APIRouter(prefix="/api/v1")
for module in (
    auth,
    users,
    scans,
    findings,
    vulnerabilities,
    assets,
    networks,
    dashboard,
    reports,
    sla,
    risk,
    suppressions,
    views,
    notifications,
    settings,
    misc,
):
    api_router.include_router(module.router)
