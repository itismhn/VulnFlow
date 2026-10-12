from enum import StrEnum

from app.models.enums import Role


class Perm(StrEnum):
    SCANS_READ = "scans:read"
    SCANS_UPLOAD = "scans:upload"
    SCANS_MANAGE = "scans:manage"
    FINDINGS_READ = "findings:read"
    FINDINGS_UPDATE = "findings:update"
    ASSETS_READ = "assets:read"
    ASSETS_UPDATE = "assets:update"
    NETWORKS_READ = "networks:read"
    NETWORKS_MANAGE = "networks:manage"
    REPORTS_CREATE = "reports:create"
    TEMPLATES_MANAGE = "templates:manage"
    USERS_MANAGE = "users:manage"
    AUDIT_READ = "audit:read"


_VIEWER = {
    Perm.SCANS_READ,
    Perm.FINDINGS_READ,
    Perm.ASSETS_READ,
    Perm.NETWORKS_READ,
    Perm.REPORTS_CREATE,
}
_ANALYST = _VIEWER | {
    Perm.SCANS_UPLOAD,
    Perm.FINDINGS_UPDATE,
    Perm.ASSETS_UPDATE,
    Perm.NETWORKS_MANAGE,
    Perm.TEMPLATES_MANAGE,
}

ROLE_PERMISSIONS: dict[str, frozenset[Perm]] = {
    Role.VIEWER: frozenset(_VIEWER),
    Role.ANALYST: frozenset(_ANALYST),
    Role.ADMIN: frozenset(Perm),
}


def has_perm(role: str, perm: Perm) -> bool:
    return perm in ROLE_PERMISSIONS.get(role, frozenset())
