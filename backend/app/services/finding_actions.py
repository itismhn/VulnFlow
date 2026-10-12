from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Finding, FindingEvent, User
from app.models.enums import FindingEventKind, FindingStatus, Role
from app.schemas.finding import FindingUpdate


def update_finding(db: Session, finding: Finding, body: FindingUpdate, actor: User) -> bool:
    """Apply a manual change and record it on the finding's timeline."""
    changed = False
    note = body.note.strip()

    if body.status and body.status != finding.status:
        if body.status in (FindingStatus.RISK_ACCEPTED, FindingStatus.FALSE_POSITIVE) and not note:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A justification note is required for risk acceptance or false positive",
            )
        if body.status == FindingStatus.RISK_ACCEPTED and actor.role != Role.ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can accept risk")
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
        changed = True
        note = ""

    if body.due_date is not None and body.due_date != finding.due_date:
        finding.due_date = body.due_date
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
    return changed
