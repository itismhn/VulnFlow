"""Import a parsed scan into the database and drive the finding lifecycle.

One import runs in a single transaction. Imports are serialized with a Postgres
advisory lock, so concurrent workers can never race on asset or finding upserts.

Lifecycle rules (per host the scan covered):
  * new (asset, plugin, port, protocol)             -> finding created as `open`
  * seen again in a newer scan                      -> `last_seen` bumped; `fixed` becomes `reopened`
  * seen in an older scan (out-of-order import)     -> only `first_seen` may move earlier
  * active finding missing from a newer scan        -> `fixed`, unless:
      - its plugin family was disabled in this scan's policy, or
      - this host scan was uncredentialed but the last sighting was credentialed
  * `risk_accepted` / `false_positive` are never changed by imports
"""

import logging
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    Asset,
    Finding,
    FindingEvent,
    FindingOccurrence,
    Plugin,
    Scan,
    ScanHost,
)
from app.models.enums import ACTIVE_STATUSES, FindingEventKind, FindingStatus, ScanStatus
from app.services import networks
from app.services.parsers import ParsedHost, get_parser
from app.services.parsers.base import ParsedItem

log = logging.getLogger(__name__)

BATCH_HOSTS = 100
_INGEST_LOCK_KEY = 0x5E55  # arbitrary constant shared by all ingest workers

FindingKey = tuple[int, int, int, str]


@dataclass
class IngestStats:
    hosts: int = 0
    new: int = 0
    reopened: int = 0
    fixed: int = 0
    first_time: datetime | None = None
    last_time: datetime | None = None
    asset_ids: list[int] = field(default_factory=list)

    def observe(self, start: datetime, end: datetime | None) -> None:
        self.first_time = min(filter(None, (self.first_time, start)))
        self.last_time = max(filter(None, (self.last_time, end or start)))


def ingest_scan(db: Session, scan: Scan, progress: Callable[[int], None] | None = None) -> IngestStats:
    """Parse `scan.file_path` and merge it into findings. Caller commits."""
    db.execute(select(func.pg_advisory_xact_lock(_INGEST_LOCK_KEY)))

    path = Path(scan.file_path)
    parser = get_parser(path)
    total_bytes = max(path.stat().st_size, 1)
    fallback_time = scan.created_at or datetime.now(UTC)
    stats = IngestStats()

    # Re-ingest: drop what this scan contributed before
    db.execute(delete(FindingOccurrence).where(FindingOccurrence.scan_id == scan.id))
    db.execute(delete(ScanHost).where(ScanHost.scan_id == scan.id))

    batch: list[ParsedHost] = []
    for host in parser.iter_hosts(path):
        batch.append(host)
        if len(batch) >= BATCH_HOSTS:
            _process_batch(db, scan, batch, stats, fallback_time)
            batch = []
            if progress:
                progress(min(95, int(parser.position * 100 / total_bytes)))
    if batch:
        _process_batch(db, scan, batch, stats, fallback_time)

    stats.fixed = _auto_fix(db, scan, fallback_time)
    networks.reassign_assets(db, stats.asset_ids)
    _finalize_scan(db, scan, parser.meta, stats)
    return stats


def _merge_hosts(hosts: Iterable[ParsedHost]) -> list[ParsedHost]:
    by_ip: dict[str, ParsedHost] = {}
    for host in hosts:
        if host.ip in by_ip:
            by_ip[host.ip].items.extend(host.items)
        else:
            by_ip[host.ip] = host
    return sorted(by_ip.values(), key=lambda h: h.ip)


def _upsert_assets(db: Session, hosts: list[ParsedHost], times: dict[str, datetime]) -> dict[str, int]:
    rows = [
        {
            "ip": h.ip,
            "hostname": h.hostname[:255],
            "fqdn": h.fqdn[:255],
            "netbios": h.netbios[:128],
            "mac": h.mac[:255],
            "os": h.os[:255],
            "first_seen": times[h.ip],
            "last_seen": times[h.ip],
            "tags": [],
        }
        for h in hosts
    ]
    stmt = insert(Asset).values(rows)
    ex = stmt.excluded
    keep = lambda col: func.coalesce(func.nullif(getattr(ex, col), ""), getattr(Asset, col))  # noqa: E731
    upsert = stmt.on_conflict_do_update(
        index_elements=[Asset.ip],
        set_={
            "hostname": keep("hostname"),
            "fqdn": keep("fqdn"),
            "netbios": keep("netbios"),
            "mac": keep("mac"),
            "os": keep("os"),
            "first_seen": func.least(Asset.first_seen, ex.first_seen),
            "last_seen": func.greatest(Asset.last_seen, ex.last_seen),
            "updated_at": func.now(),
        },
    ).returning(Asset.id, Asset.ip)
    return {str(ip): asset_id for asset_id, ip in db.execute(upsert)}


def _upsert_plugins(db: Session, items: Iterable[ParsedItem]) -> None:
    plugins = {item.plugin.id: item.plugin for item in items}
    if not plugins:
        return
    rows = [asdict(p) for p in sorted(plugins.values(), key=lambda p: p.id)]
    for row in rows:
        row["name"] = row["name"][:512]
        row["family"] = row["family"][:128]
    stmt = insert(Plugin).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Plugin.id],
        set_={**{k: getattr(stmt.excluded, k) for k in rows[0] if k != "id"}, "updated_at": func.now()},
    )
    db.execute(stmt)


def _process_batch(
    db: Session,
    scan: Scan,
    raw_hosts: list[ParsedHost],
    stats: IngestStats,
    fallback_time: datetime,
) -> None:
    hosts = _merge_hosts(raw_hosts)
    times = {h.ip: h.started_at or h.ended_at or fallback_time for h in hosts}
    for h in hosts:
        stats.observe(times[h.ip], h.ended_at)
    stats.hosts += len(hosts)

    asset_ids = _upsert_assets(db, hosts, times)
    stats.asset_ids.extend(asset_ids.values())

    db.execute(
        insert(ScanHost)
        .values(
            [
                {
                    "scan_id": scan.id,
                    "asset_id": asset_ids[h.ip],
                    "started_at": times[h.ip],
                    "ended_at": h.ended_at,
                    "credentialed": h.credentialed,
                    "os": h.os[:255],
                }
                for h in hosts
            ]
        )
        .on_conflict_do_nothing()
    )

    all_items = [item for h in hosts for item in h.items]
    _upsert_plugins(db, all_items)

    # Deduplicate (asset, plugin, port, protocol) within the batch
    observed: dict[FindingKey, tuple[ParsedItem, datetime]] = {}
    for h in hosts:
        for item in h.items:
            key = (asset_ids[h.ip], item.plugin.id, item.port, item.protocol)
            if key in observed:
                prev, t = observed[key]
                if item.output and item.output not in prev.output:
                    prev.output = f"{prev.output}\n\n{item.output}".strip()
                prev.severity = max(prev.severity, item.severity)
            else:
                observed[key] = (item, times[h.ip])
    if not observed:
        return

    existing = {
        (f.asset_id, f.plugin_id, f.port, f.protocol): f
        for f in db.execute(
            select(
                Finding.id,
                Finding.asset_id,
                Finding.plugin_id,
                Finding.port,
                Finding.protocol,
                Finding.status,
                Finding.first_seen,
                Finding.last_seen,
                Finding.reopen_count,
            ).where(Finding.asset_id.in_(set(asset_ids.values())))
        )
    }

    new_rows: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    finding_ids: dict[FindingKey, int] = {}

    for key, (item, t) in observed.items():
        current = existing.get(key)
        if current is None:
            new_rows.append(
                {
                    "asset_id": key[0],
                    "plugin_id": key[1],
                    "port": key[2],
                    "protocol": key[3],
                    "service": item.service,
                    "severity": item.severity,
                    "status": FindingStatus.OPEN,
                    "first_seen": t,
                    "last_seen": t,
                    "plugin_output": item.output,
                    "last_scan_id": scan.id,
                }
            )
            continue

        finding_ids[key] = current.id
        if t >= current.last_seen:
            row: dict[str, Any] = {
                "id": current.id,
                "last_seen": t,
                "severity": item.severity,
                "service": item.service,
                "plugin_output": item.output,
                "last_scan_id": scan.id,
                "first_seen": min(current.first_seen, t),
            }
            if current.status == FindingStatus.FIXED:
                row.update(
                    status=FindingStatus.REOPENED,
                    fixed_at=None,
                    reopen_count=current.reopen_count + 1,
                )
                events.append(
                    {
                        "finding_id": current.id,
                        "kind": FindingEventKind.STATUS,
                        "from_status": FindingStatus.FIXED,
                        "to_status": FindingStatus.REOPENED,
                        "scan_id": scan.id,
                        "note": "Detected again by scan",
                    }
                )
                stats.reopened += 1
            updates.append(row)
        elif t < current.first_seen:
            updates.append({"id": current.id, "first_seen": t})

    if new_rows:
        inserted = db.execute(
            insert(Finding)
            .values(new_rows)
            .returning(Finding.id, Finding.asset_id, Finding.plugin_id, Finding.port, Finding.protocol)
        )
        for fid, asset_id, plugin_id, port, protocol in inserted:
            key = (asset_id, plugin_id, port, protocol)
            finding_ids[key] = fid
            events.append(
                {
                    "finding_id": fid,
                    "kind": FindingEventKind.DETECTED,
                    "to_status": FindingStatus.OPEN,
                    "scan_id": scan.id,
                    "note": "First detected",
                }
            )
        stats.new += len(new_rows)

    if updates:
        # Group by key-set: bulk UPDATE requires homogeneous parameter dicts
        groups: dict[frozenset[str], list[dict[str, Any]]] = {}
        for row in updates:
            groups.setdefault(frozenset(row), []).append(row)
        for rows in groups.values():
            db.execute(update(Finding), rows)

    db.execute(
        insert(FindingOccurrence)
        .values(
            [
                {
                    "finding_id": finding_ids[key],
                    "scan_id": scan.id,
                    "severity": item.severity,
                    "plugin_output": item.output,
                }
                for key, (item, _t) in observed.items()
            ]
        )
        .on_conflict_do_nothing()
    )
    if events:
        # Multi-row VALUES needs identical keys in every row
        defaults = {"from_status": None, "to_status": None, "note": "", "scan_id": scan.id}
        db.execute(insert(FindingEvent).values([{**defaults, **e} for e in events]))


_AUTO_FIX_CANDIDATES = text(
    """
    SELECT f.id, f.status, sh.started_at AS observed_at
    FROM findings f
    JOIN scan_hosts sh ON sh.asset_id = f.asset_id AND sh.scan_id = :scan_id
    JOIN plugins p ON p.id = f.plugin_id
    WHERE f.status = ANY(:active)
      AND f.last_seen < sh.started_at
      AND NOT (p.family = ANY(:disabled))
      AND NOT EXISTS (
          SELECT 1 FROM finding_occurrences o
          WHERE o.finding_id = f.id AND o.scan_id = :scan_id
      )
      AND (
          sh.credentialed
          OR NOT EXISTS (
              SELECT 1 FROM scan_hosts prev
              WHERE prev.scan_id = f.last_scan_id
                AND prev.asset_id = f.asset_id
                AND prev.credentialed
          )
      )
    """
)


def _auto_fix(db: Session, scan: Scan, fallback_time: datetime) -> int:
    candidates = db.execute(
        _AUTO_FIX_CANDIDATES,
        {
            "scan_id": scan.id,
            "active": [s.value for s in ACTIVE_STATUSES],
            "disabled": scan.disabled_families or [],
        },
    ).all()
    if not candidates:
        return 0
    db.execute(
        update(Finding),
        [
            {"id": c.id, "status": FindingStatus.FIXED, "fixed_at": c.observed_at or fallback_time}
            for c in candidates
        ],
    )
    db.execute(
        insert(FindingEvent).values(
            [
                {
                    "finding_id": c.id,
                    "kind": FindingEventKind.STATUS,
                    "from_status": c.status,
                    "to_status": FindingStatus.FIXED,
                    "scan_id": scan.id,
                    "note": "Not detected by a newer scan of this host",
                }
                for c in candidates
            ]
        )
    )
    return len(candidates)


def _finalize_scan(db: Session, scan: Scan, meta: Any, stats: IngestStats) -> None:
    counts = dict(
        db.execute(
            select(FindingOccurrence.severity, func.count())
            .where(FindingOccurrence.scan_id == scan.id)
            .group_by(FindingOccurrence.severity)
        ).all()
    )
    scan.policy_name = meta.policy_name[:255]
    scan.disabled_families = meta.disabled_families
    scan.skipped_hosts = meta.skipped_hosts
    if meta.report_name and scan.name == scan.filename:
        scan.name = meta.report_name[:255]
    scan.started_at = stats.first_time
    scan.finished_at = stats.last_time
    scan.host_count = stats.hosts
    scan.info_count = counts.get(0, 0)
    scan.low_count = counts.get(1, 0)
    scan.medium_count = counts.get(2, 0)
    scan.high_count = counts.get(3, 0)
    scan.critical_count = counts.get(4, 0)
    scan.finding_count = sum(v for k, v in counts.items() if k > 0)
    scan.new_count = stats.new
    scan.fixed_count = stats.fixed
    scan.reopened_count = stats.reopened
    scan.status = ScanStatus.DONE
    scan.progress = 100
    scan.error = ""
    scan.parsed_at = datetime.now(UTC)


def recompute_after_scan_delete(db: Session, asset_ids: list[int]) -> None:
    """After a scan's occurrences are gone, drop orphaned findings and fix seen-dates."""
    if not asset_ids:
        return
    db.execute(
        text(
            """
            DELETE FROM findings f
            WHERE f.asset_id = ANY(:ids)
              AND NOT EXISTS (SELECT 1 FROM finding_occurrences o WHERE o.finding_id = f.id)
            """
        ),
        {"ids": asset_ids},
    )
    db.execute(
        text(
            """
            UPDATE findings f SET
                first_seen = agg.first_seen,
                last_seen = agg.last_seen,
                last_scan_id = agg.last_scan_id
            FROM (
                SELECT o.finding_id,
                       min(sh.started_at) AS first_seen,
                       max(sh.started_at) AS last_seen,
                       (array_agg(o.scan_id ORDER BY sh.started_at DESC))[1] AS last_scan_id
                FROM finding_occurrences o
                JOIN findings f2 ON f2.id = o.finding_id
                JOIN scan_hosts sh ON sh.scan_id = o.scan_id AND sh.asset_id = f2.asset_id
                WHERE f2.asset_id = ANY(:ids)
                GROUP BY o.finding_id
            ) agg
            WHERE f.id = agg.finding_id
            """
        ),
        {"ids": asset_ids},
    )
    db.execute(
        text(
            """
            DELETE FROM assets a
            WHERE a.id = ANY(:ids)
              AND NOT EXISTS (SELECT 1 FROM scan_hosts sh WHERE sh.asset_id = a.id)
            """
        ),
        {"ids": asset_ids},
    )
