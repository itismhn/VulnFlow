from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Protocol


class ParseError(Exception):
    pass


@dataclass(slots=True)
class ParsedPlugin:
    id: int
    name: str
    family: str = ""
    severity: int = 0
    risk_factor: str = ""
    synopsis: str = ""
    description: str = ""
    solution: str = ""
    see_also: list[str] = field(default_factory=list)
    cvss2_base: float | None = None
    cvss2_vector: str = ""
    cvss3_base: float | None = None
    cvss3_vector: str = ""
    cvss4_base: float | None = None
    cvss4_vector: str = ""
    vpr_score: float | None = None
    epss_score: float | None = None
    cves: list[str] = field(default_factory=list)
    cwes: list[str] = field(default_factory=list)
    exploit_available: bool = False
    exploit_frameworks: list[str] = field(default_factory=list)
    exploitability_ease: str = ""
    publication_date: date | None = None
    patch_publication_date: date | None = None
    vuln_publication_date: date | None = None


@dataclass(slots=True)
class ParsedItem:
    plugin: ParsedPlugin
    port: int
    protocol: str
    service: str
    severity: int
    output: str


@dataclass(slots=True)
class ParsedHost:
    ip: str
    hostname: str = ""
    fqdn: str = ""
    netbios: str = ""
    mac: str = ""
    os: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    credentialed: bool = False
    items: list[ParsedItem] = field(default_factory=list)


@dataclass(slots=True)
class ScanMeta:
    report_name: str = ""
    policy_name: str = ""
    disabled_families: list[str] = field(default_factory=list)
    skipped_hosts: int = 0


class ScanParser(Protocol):
    """Interface for scanner formats. Implement this to add OpenVAS, Qualys, etc."""

    name: str
    meta: ScanMeta
    position: int

    @staticmethod
    def detect(path: Path) -> bool: ...

    def iter_hosts(self, path: Path) -> Iterator[ParsedHost]: ...
