"""Software inventory: which OS, application, package, and service versions run where.

`asset_software` is derived from each asset's current informational findings
(the output each plugin printed in the last scan that saw it) plus the asset's
reported operating system. It is rebuilt per asset after every import and
scan deletion, so it always follows the finding lifecycle: software whose
detection plugin stops firing is auto-fixed there and disappears here.
"""

import ipaddress
import re
from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, delete, func, insert, or_, select
from sqlalchemy.orm import Session

from app.models import Asset, AssetSoftware, Finding, FindingOccurrence, Network, Plugin, User
from app.models.enums import FindingStatus
from app.schemas.software import SoftwareFilters
from app.services.scoping import scope_assets
from app.services.software_extract import OS, Software, extract, split_os, version_key

CHUNK = 200

Identity = tuple[str, str, str, str, int, str, str]


def rebuild(db: Session, asset_ids: Iterable[int] | None = None) -> int:
    """Recompute the inventory of the given assets (all assets when None). Caller commits."""
    ids = sorted(set(asset_ids)) if asset_ids is not None else list(db.scalars(select(Asset.id)))
    total = 0
    for start in range(0, len(ids), CHUNK):
        total += _rebuild_chunk(db, ids[start : start + CHUNK])
    return total


def _identity(asset_id: int, sw: Software, port: int, protocol: str) -> Identity:
    return (str(asset_id), sw.category, sw.vendor, sw.key, port, protocol, f"{sw.version}\x00{sw.path}")


def _rebuild_chunk(db: Session, ids: list[int]) -> int:
    # Keep first_seen across rebuilds so "installed since" survives re-imports
    previous: dict[Identity, datetime | None] = {}
    for r in db.execute(
        select(
            AssetSoftware.asset_id,
            AssetSoftware.category,
            AssetSoftware.vendor,
            AssetSoftware.product,
            AssetSoftware.port,
            AssetSoftware.protocol,
            AssetSoftware.version,
            AssetSoftware.path,
            AssetSoftware.first_seen,
        ).where(AssetSoftware.asset_id.in_(ids))
    ):
        key = (
            str(r.asset_id),
            r.category,
            r.vendor,
            r.product,
            r.port,
            r.protocol,
            f"{r.version}\x00{r.path}",
        )
        previous[key] = r.first_seen
    db.execute(delete(AssetSoftware).where(AssetSoftware.asset_id.in_(ids)))

    rows: dict[Identity, dict[str, Any]] = {}
    os_cpe: dict[int, Software] = {}

    def add(asset_id: int, sw: Software, seen: datetime | None, **extra: Any) -> None:
        port, protocol = extra.get("port", 0), extra.get("protocol", "")
        key = _identity(asset_id, sw, port, protocol)
        if key in rows:
            return
        rows[key] = {
            "asset_id": asset_id,
            "finding_id": extra.get("finding_id"),
            "plugin_id": extra.get("plugin_id"),
            "category": sw.category,
            "name": sw.name,
            "vendor": sw.vendor,
            "product": sw.key[:255],
            "version": sw.version,
            "version_key": version_key(sw.version)[:512],
            "cpe": sw.cpe,
            "port": port,
            "protocol": protocol,
            "path": sw.path,
            "first_seen": previous.get(key) or seen,
            "last_seen": seen,
        }

    output = func.coalesce(FindingOccurrence.plugin_output, Finding.plugin_output)
    findings = db.execute(
        select(
            Finding.id,
            Finding.asset_id,
            Finding.plugin_id,
            Finding.port,
            Finding.protocol,
            Finding.last_seen,
            Plugin.name,
            Plugin.family,
            Plugin.cpe,
            output.label("output"),
        )
        .join(Plugin, Plugin.id == Finding.plugin_id)
        .outerjoin(
            FindingOccurrence,
            and_(
                FindingOccurrence.finding_id == Finding.id,
                FindingOccurrence.scan_id == Finding.last_scan_id,
            ),
        )
        .where(Finding.asset_id.in_(ids), Finding.severity == 0, Finding.status != FindingStatus.FIXED)
        .order_by(Finding.asset_id, Finding.plugin_id, Finding.port)
        .execution_options(yield_per=500)
    )
    for f in findings:
        for sw in extract(f.plugin_id, f.name, f.family, f.cpe, f.output or "", f.port):
            if sw.category == OS:
                # The OS row below comes from the host's properties; keep the CPE for it
                os_cpe.setdefault(f.asset_id, sw)
                continue
            add(
                f.asset_id,
                sw,
                f.last_seen,
                port=f.port,
                protocol=f.protocol if f.port else "",
                finding_id=f.id,
                plugin_id=f.plugin_id,
            )

    for asset_id, os_name, last_seen in db.execute(
        select(Asset.id, Asset.os, Asset.last_seen).where(Asset.id.in_(ids))
    ):
        cpe = os_cpe.get(asset_id)
        if os_name:
            name, version = split_os(os_name)
            sw = Software(
                OS,
                name[:255],
                version[:128],
                vendor=cpe.vendor if cpe else "",
                cpe=cpe.cpe if cpe else "",
            )
        elif cpe:
            sw = cpe
        else:
            continue
        add(asset_id, sw, last_seen)

    values = _merge_duplicates(list(rows.values()))
    if values:
        for start in range(0, len(values), 2000):
            db.execute(insert(AssetSoftware), values[start : start + 2000])
    return len(values)


def _merge_duplicates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One install is often reported by several plugins (CPE list, banner, detection).

    Per asset and version, keep the rows that say where it is (a port or a path)
    and fold the bare ones into them, carrying over the CPE and earliest first_seen.
    """
    groups: dict[tuple[int, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["asset_id"], row["vendor"], row["product"], row["version_key"]), []).append(
            row
        )
    out: list[dict[str, Any]] = []
    for group in groups.values():
        located = [r for r in group if r["port"] or r["path"]]
        keep = located or group[:1]
        cpe = next((r["cpe"] for r in group if r["cpe"]), "")
        seen = [r["first_seen"] for r in group if r["first_seen"]]
        for row in keep:
            row["cpe"] = row["cpe"] or cpe
            row["first_seen"] = min(seen) if seen else None
            # Prefer the shortest name, e.g. "Oracle Database" over "Oracle Database Server"
            row["name"] = min((r["name"] for r in group), key=len)
        out.extend(keep)
    return out


# --- Querying ----------------------------------------------------------------

_VERSION_TERM = re.compile(r"(<=|>=|!=|<|>|=)?\s*([^\s,<>=!]+)")


def version_clauses(expr: str) -> list[Any]:
    """'>=2.0 <2.17.1' -> SQL conditions on version_key. A bare term is a prefix match."""
    conds: list[Any] = []
    col = AssetSoftware.version_key
    for op, raw in _VERSION_TERM.findall(expr):
        wildcard = raw.endswith("*")
        key = version_key(raw.rstrip("*").rstrip("."))
        if not key:
            continue
        if op in ("", "=") and (wildcard or not op):
            conds.append(col.like(f"{key}%"))
        elif op == "=":
            conds.append(col == key)
        elif op == "!=":
            conds.append(col != key)
        else:
            conds.append(
                and_(col != "", {"<": col < key, "<=": col <= key, ">": col > key, ">=": col >= key}[op])
            )
    return conds


def base_query(user: User, *columns: Any) -> Select[Any]:
    stmt = (
        select(*columns)
        .select_from(AssetSoftware)
        .join(Asset, Asset.id == AssetSoftware.asset_id)
        .outerjoin(Network, Network.id == Asset.network_id)
    )
    return scope_assets(stmt, user)


def apply_filters(stmt: Select[Any], f: SoftwareFilters) -> Select[Any]:
    conds: list[Any] = []
    if f.q:
        like = f"%{f.q.strip()}%"
        conds.append(
            or_(
                AssetSoftware.name.ilike(like),
                AssetSoftware.product.ilike(like),
                AssetSoftware.vendor.ilike(like),
                AssetSoftware.cpe.ilike(like),
            )
        )
    if f.category:
        conds.append(AssetSoftware.category.in_(f.category))
    if f.vendor is not None:
        conds.append(AssetSoftware.vendor == f.vendor)
    if f.product:
        conds.append(AssetSoftware.product == f.product)
    if f.version:
        conds.extend(version_clauses(f.version))
    if f.asset_id:
        conds.append(AssetSoftware.asset_id == f.asset_id)
    if f.network_id:
        conds.append(Asset.network_id.in_(f.network_id))
    if f.zone:
        conds.append(Network.zone.in_(f.zone))
    if f.ip:
        net = ipaddress.ip_network(f.ip.strip(), strict=False)
        conds.append(Asset.ip.op("<<=")(str(net)))
    return stmt.where(*conds) if conds else stmt


INSTANCE_COLUMNS = (
    AssetSoftware.id,
    AssetSoftware.asset_id,
    Asset.ip,
    func.coalesce(func.nullif(Asset.hostname, ""), Asset.fqdn).label("hostname"),
    Network.name.label("network_name"),
    Network.zone,
    AssetSoftware.category,
    AssetSoftware.name,
    AssetSoftware.vendor,
    AssetSoftware.product,
    AssetSoftware.version,
    AssetSoftware.cpe,
    AssetSoftware.port,
    AssetSoftware.protocol,
    AssetSoftware.path,
    AssetSoftware.plugin_id,
    AssetSoftware.finding_id,
    AssetSoftware.first_seen,
    AssetSoftware.last_seen,
)

INSTANCE_SORTS: dict[str, Any] = {
    "name": AssetSoftware.name,
    "version": AssetSoftware.version_key,
    "ip": Asset.ip,
    "last_seen": AssetSoftware.last_seen,
}


def instance_query(user: User, f: SoftwareFilters, sort: str = "name") -> Select[Any]:
    col = INSTANCE_SORTS.get(sort.lstrip("-"), INSTANCE_SORTS["name"])
    order = col.desc() if sort.startswith("-") else col.asc()
    return apply_filters(base_query(user, *INSTANCE_COLUMNS), f).order_by(
        order, AssetSoftware.name, AssetSoftware.version_key.desc(), Asset.ip
    )


EXPORT_HEADER = [
    "IP",
    "Hostname",
    "Network",
    "Zone",
    "Category",
    "Software",
    "Vendor",
    "Version",
    "CPE",
    "Port",
    "Protocol",
    "Path",
    "Source plugin",
    "First seen",
    "Last seen",
]


def export_rows(db: Session, user: User, f: SoftwareFilters, limit: int = 500_000) -> Iterator[list[Any]]:
    yield EXPORT_HEADER
    stmt = instance_query(user, f).limit(limit).execution_options(yield_per=2000)
    for r in db.execute(stmt):
        yield [
            str(r.ip),
            r.hostname or "",
            r.network_name or "",
            r.zone or "",
            r.category,
            r.name,
            r.vendor,
            r.version,
            r.cpe,
            r.port or "",
            r.protocol,
            r.path,
            r.plugin_id or "",
            r.first_seen.date().isoformat() if r.first_seen else "",
            r.last_seen.date().isoformat() if r.last_seen else "",
        ]
