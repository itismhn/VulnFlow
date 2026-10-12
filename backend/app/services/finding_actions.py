from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Finding, FindingEvent, User
from app.models.enums import FindingEventKind, FindingStatus, NotificationKind, Role
from app.schemas.finding import FindingUpdate
from app.services import risk
from app.services.notifications import finding_link, mentioned_users, notify


def update_finding(
    db: Session, finding: Finding, body: FindingUpdate, actor: User, *, notify_users: bool = True
) -> bool:
    """Apply a manual change and record it on the finding's timeline."""
    changed = False
    note = body.note.strip()
    mention_text = note if notify_users else ""

    if body.status and body.status != finding.status:
        if body.status == FindingStatus.RISK_ACCEPTED:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Risk acceptance needs a request and an approval; use the risk acceptance workflow",
            )
        if body.status == FindingStatus.FALSE_POSITIVE and not note:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "A reason is required to mark a false positive"
            )
        if finding.status == FindingStatus.RISK_ACCEPTED:
            risk.end_for_manual_change(db, finding, actor)
        db.add(
            FindingEvent(
                finding_id=finding.id,
                kind=FindingEventKind.STATUS,
                from_status=finding.status,
                to_status=body.status,
                note=note,
                actor_id=actor.id,
            )
        )
        finding.status = body.status
        finding.fixed_at = datetime.now(UTC) if body.status == FindingStatus.FIXED else None
        changed = True
        note = ""

    new_assignee = None if body.clear_assignee else body.assignee_id
    if (body.clear_assignee or body.assignee_id is not None) and new_assignee != finding.assignee_id:
        if new_assignee is not None:
            assignee = db.get(User, new_assignee)
            if assignee is None or not assignee.is_active or assignee.role == Role.VIEWER:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid assignee")
            label = f"Assigned to {assignee.username}"
        else:
            label = "Unassigned"
        db.add(
            FindingEvent(
                finding_id=finding.id,
                kind=FindingEventKind.ASSIGN,
                note=label + (f": {note}" if note else ""),
                actor_id=actor.id,
            )
        )
        finding.assignee_id = new_assignee
        if new_assignee is not None and notify_users:
            notify(
                db,
                [new_assignee],
                NotificationKind.ASSIGNED,
                f"Assigned to you: {finding.plugin.name} on {finding.asset.ip}",
                link=finding_link(finding.id),
                actor=actor,
            )
        changed = True
        note = ""

    if body.clear_due_date and finding.due_source == "manual":
        # Hand the date back to the SLA policy
        finding.due_source = None
        finding.due_date = None
        db.add(
            FindingEvent(
                finding_id=finding.id,
                kind=FindingEventKind.COMMENT,
                note="Due date reset to SLA policy",
                actor_id=actor.id,
            )
        )
        changed = True
    elif body.due_date is not None and body.due_date != finding.due_date:
        finding.due_date = body.due_date
        finding.due_source = "manual"
        db.add(
            FindingEvent(
                finding_id=finding.id,
                kind=FindingEventKind.COMMENT,
                note=f"Due date set to {body.due_date.isoformat()}",
                actor_id=actor.id,
            )
        )
        changed = True

    if note:
        db.add(
            FindingEvent(finding_id=finding.id, kind=FindingEventKind.COMMENT, note=note, actor_id=actor.id)
        )
        changed = True
    if mention_text:
        mentioned = mentioned_users(db, mention_text, finding.id)
        notify(
            db,
            [u.id for u in mentioned],
            NotificationKind.MENTION,
            f"{actor.username} mentioned you on {finding.plugin.name}",
            body=mention_text[:500],
            link=finding_link(finding.id),
            actor=actor,
        )
    return changed
