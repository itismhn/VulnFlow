"""Risk acceptance: request → approve/reject → expire or revoke.

An approved acceptance moves the finding to `risk_accepted`. When it ends
(expiry or revocation) the finding returns to the status it had before.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Perm, has_perm
from app.models import Finding, FindingEvent, RiskAcceptance, User
from app.models.enums import (
    ACTIVE_STATUSES,
    AcceptanceStatus,
    FindingEventKind,
    FindingStatus,
    NotificationKind,
)
from app.services.app_settings import get_setting
from app.services.notifications import finding_link, notify, users_with


def _error(code: int, msg: str) -> HTTPException:
    return HTTPException(code, msg)


def _event(db: Session, finding: Finding, to_status: str, note: str, actor: User | None) -> None:
    db.add(
        FindingEvent(
            finding_id=finding.id,
            kind=FindingEventKind.STATUS if to_status != finding.status else FindingEventKind.RISK,
            from_status=finding.status if to_status != finding.status else None,
            to_status=to_status if to_status != finding.status else None,
            note=note,
            actor_id=actor.id if actor else None,
        )
    )


def _label(finding: Finding) -> str:
    return f"{finding.plugin.name} on {finding.asset.ip}"


def request_acceptance(
    db: Session, finding: Finding, justification: str, expires_at: date, actor: User
) -> RiskAcceptance:
    justification = justification.strip()
    if not justification:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "A justification is required")
    if finding.status not in ACTIVE_STATUSES:
        raise _error(status.HTTP_409_CONFLICT, "Only open findings can be risk-accepted")
    today = date.today()
    max_days = int(get_setting(db, "risk_max_days"))
    if expires_at <= today:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "Expiry must be in the future")
    if expires_at > today + timedelta(days=max_days):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Expiry can be at most {max_days} days from today"
        )
    pending = db.scalar(
        select(RiskAcceptance.id).where(
            RiskAcceptance.finding_id == finding.id, RiskAcceptance.status == AcceptanceStatus.PENDING
        )
    )
    if pending:
        raise _error(status.HTTP_409_CONFLICT, "A request is already pending for this finding")

    ra = RiskAcceptance(
        finding_id=finding.id,
        justification=justification,
        expires_at=expires_at,
        previous_status=finding.status,
        requested_by_id=actor.id,
    )
    db.add(ra)
    _event(
        db, finding, finding.status, f"Risk acceptance requested until {expires_at}: {justification}", actor
    )
    db.flush()
    notify(
        db,
        [u.id for u in users_with(db, Perm.RISK_APPROVE)],
        NotificationKind.RISK_REQUESTED,
        f"Risk acceptance requested: {_label(finding)}",
        body=justification,
        link="/approvals",
        actor=actor,
    )
    return ra


def decide(db: Session, ra: RiskAcceptance, approve: bool, note: str, actor: User) -> RiskAcceptance:
    if ra.status != AcceptanceStatus.PENDING:
        raise _error(status.HTTP_409_CONFLICT, "This request has already been decided")
    if approve and ra.requested_by_id == actor.id and not get_setting(db, "risk_self_approval"):
        raise _error(status.HTTP_403_FORBIDDEN, "Another admin must approve your own request")
    finding = db.get(Finding, ra.finding_id)
    assert finding is not None
    if approve and ra.expires_at <= date.today():
        raise _error(status.HTTP_409_CONFLICT, "The requested expiry date has already passed")
    if approve and finding.status not in ACTIVE_STATUSES:
        raise _error(status.HTTP_409_CONFLICT, f"The finding is now {finding.status}; reject this request")

    ra.status = AcceptanceStatus.APPROVED if approve else AcceptanceStatus.REJECTED
    ra.decided_by_id = actor.id
    ra.decided_at = datetime.now(UTC)
    ra.decision_note = note.strip()
    verb = "approved" if approve else "rejected"
    text = f"Risk acceptance {verb}" + (f": {ra.decision_note}" if ra.decision_note else "")
    if approve:
        ra.previous_status = finding.status
        _event(db, finding, FindingStatus.RISK_ACCEPTED, f"{text} (until {ra.expires_at})", actor)
        finding.status = FindingStatus.RISK_ACCEPTED
        finding.fixed_at = None
    else:
        _event(db, finding, finding.status, text, actor)
    if ra.requested_by_id:
        notify(
            db,
            [ra.requested_by_id],
            NotificationKind.RISK_DECIDED,
            f"Risk acceptance {verb}: {_label(finding)}",
            body=ra.decision_note,
            link=finding_link(finding.id),
            actor=actor,
        )
    return ra


def _end(db: Session, ra: RiskAcceptance, new_state: str, note: str, actor: User | None) -> None:
    ra.status = new_state
    finding = db.get(Finding, ra.finding_id)
    if finding is None or finding.status != FindingStatus.RISK_ACCEPTED:
        return
    restore = ra.previous_status if ra.previous_status in ACTIVE_STATUSES else FindingStatus.OPEN
    _event(db, finding, restore, note, actor)
    finding.status = restore


def revoke(db: Session, ra: RiskAcceptance, note: str, actor: User) -> RiskAcceptance:
    if ra.status not in (AcceptanceStatus.APPROVED, AcceptanceStatus.PENDING):
        raise _error(status.HTTP_409_CONFLICT, "Only pending or approved acceptances can be revoked")
    if ra.status == AcceptanceStatus.PENDING:
        if actor.id != ra.requested_by_id and not has_perm(actor.role, Perm.RISK_APPROVE):
            raise _error(status.HTTP_403_FORBIDDEN, "You can only withdraw your own request")
        ra.status = AcceptanceStatus.REVOKED
        ra.decided_by_id = actor.id
        ra.decided_at = datetime.now(UTC)
        return ra
    if not has_perm(actor.role, Perm.RISK_APPROVE):
        raise _error(status.HTTP_403_FORBIDDEN, "Only approvers can revoke an accepted risk")
    ra.decided_by_id = actor.id
    ra.decided_at = datetime.now(UTC)
    ra.decision_note = note.strip() or ra.decision_note
    _end(
        db,
        ra,
        AcceptanceStatus.REVOKED,
        "Risk acceptance revoked" + (f": {note.strip()}" if note.strip() else ""),
        actor,
    )
    return ra


def end_for_manual_change(db: Session, finding: Finding, actor: User) -> None:
    """A user moved a risk-accepted finding to another status: close the acceptance."""
    for ra in db.scalars(
        select(RiskAcceptance).where(
            RiskAcceptance.finding_id == finding.id, RiskAcceptance.status == AcceptanceStatus.APPROVED
        )
    ):
        ra.status = AcceptanceStatus.REVOKED
        ra.decided_by_id = actor.id
        ra.decided_at = datetime.now(UTC)


def expire_due(db: Session, today: date | None = None) -> int:
    """Expire approved acceptances whose date has passed. Caller commits."""
    today = today or date.today()
    due = list(
        db.scalars(
            select(RiskAcceptance)
            .where(RiskAcceptance.status == AcceptanceStatus.APPROVED, RiskAcceptance.expires_at < today)
            .with_for_update(skip_locked=True, of=RiskAcceptance)
        ).unique()
    )
    for ra in due:
        _end(db, ra, AcceptanceStatus.EXPIRED, f"Risk acceptance expired on {ra.expires_at}", None)
        finding = db.get(Finding, ra.finding_id)
        if finding is not None and ra.requested_by_id:
            notify(
                db,
                [ra.requested_by_id],
                NotificationKind.RISK_EXPIRED,
                f"Risk acceptance expired: {_label(finding)}",
                link=finding_link(finding.id),
            )
    return len(due)
