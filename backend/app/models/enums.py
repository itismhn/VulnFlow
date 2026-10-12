from enum import IntEnum, StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Severity(IntEnum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name.lower()


class FindingStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    FIXED = "fixed"
    REOPENED = "reopened"
    RISK_ACCEPTED = "risk_accepted"
    FALSE_POSITIVE = "false_positive"


# Statuses that count as "still a problem"
ACTIVE_STATUSES = (FindingStatus.OPEN, FindingStatus.IN_PROGRESS, FindingStatus.REOPENED)
# Statuses that the import lifecycle must never touch
MANUAL_STATUSES = (FindingStatus.RISK_ACCEPTED, FindingStatus.FALSE_POSITIVE)


class ScanStatus(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    DONE = "done"
    FAILED = "failed"


class ReportFormat(StrEnum):
    PDF = "pdf"
    XLSX = "xlsx"
    CSV = "csv"
    HTML = "html"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class FindingEventKind(StrEnum):
    DETECTED = "detected"
    STATUS = "status"
    ASSIGN = "assign"
    COMMENT = "comment"
    RISK = "risk"


class AcceptanceStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"


class NotificationKind(StrEnum):
    MENTION = "mention"
    ASSIGNED = "assigned"
    RISK_REQUESTED = "risk_requested"
    RISK_DECIDED = "risk_decided"
    RISK_EXPIRED = "risk_expired"
