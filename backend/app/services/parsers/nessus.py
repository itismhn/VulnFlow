"""Streaming parser for Nessus `.nessus` (NessusClientData_v2) exports.

Uses lxml iterparse and clears each ReportHost once handled, so memory stays
flat for multi-hundred-megabyte files. External entities and network access
are disabled to prevent XXE.
"""

import ipaddress
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import BinaryIO

from lxml import etree

from app.services.parsers.base import (
    ParsedHost,
    ParsedItem,
    ParsedPlugin,
    ParseError,
    ScanMeta,
)

_EXPLOIT_FRAMEWORKS = {
    "exploit_framework_metasploit": "Metasploit",
    "exploit_framework_canvas": "CANVAS",
    "exploit_framework_core": "Core Impact",
    "exploit_framework_d2_elliot": "D2 Elliot",
    "exploit_framework_exploithub": "ExploitHub",
}


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _host_time(tags: dict[str, str], key: str) -> datetime | None:
    ts = tags.get(f"{key}_TIMESTAMP")
    if ts and ts.isdigit():
        return datetime.fromtimestamp(int(ts), tz=UTC)
    raw = tags.get(key)
    if raw:
        try:
            return datetime.strptime(" ".join(raw.split()), "%a %b %d %H:%M:%S %Y").replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


class NessusParser:
    name = "nessus"

    def __init__(self) -> None:
        self.meta = ScanMeta()
        # Bytes consumed so far, for progress reporting
        self.position = 0

    @staticmethod
    def detect(path: Path) -> bool:
        with path.open("rb") as fh:
            head = fh.read(4096)
        return b"NessusClientData_v2" in head

    def iter_hosts(self, path: Path) -> Iterator[ParsedHost]:
        with path.open("rb") as fh:
            yield from self._iter(fh)

    def _iter(self, fh: BinaryIO) -> Iterator[ParsedHost]:
        context = etree.iterparse(
            fh,
            events=("start", "end"),
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            huge_tree=True,
            remove_comments=True,
        )
        saw_root = False
        try:
            for event, elem in context:
                tag = elem.tag
                if event == "start":
                    if not saw_root:
                        if tag != "NessusClientData_v2":
                            raise ParseError("Not a Nessus v2 file (missing NessusClientData_v2)")
                        saw_root = True
                    elif tag == "Report":
                        self.meta.report_name = elem.get("name", "")
                    continue

                if tag == "Policy":
                    self._read_policy(elem)
                    elem.clear()
                elif tag == "ReportHost":
                    host = self._read_host(elem)
                    elem.clear()
                    # Drop already-processed siblings to keep memory flat
                    while elem.getprevious() is not None:
                        del elem.getparent()[0]
                    self.position = fh.tell()
                    if host is None:
                        self.meta.skipped_hosts += 1
                    else:
                        yield host
        except etree.XMLSyntaxError as exc:
            raise ParseError(f"Invalid XML: {exc}") from exc
        if not saw_root:
            raise ParseError("Empty file")

    def _read_policy(self, policy: etree._Element) -> None:
        self.meta.policy_name = (policy.findtext("policyName") or "").strip()
        for item in policy.iterfind("FamilySelection/FamilyItem"):
            if (item.findtext("Status") or "").strip().lower() == "disabled":
                self.meta.disabled_families.append((item.findtext("FamilyName") or "").strip())

    def _read_host(self, node: etree._Element) -> ParsedHost | None:
        tags = {t.get("name", ""): (t.text or "").strip() for t in node.iterfind("HostProperties/tag")}
        ip = _valid_ip(tags.get("host-ip", "")) or _valid_ip(node.get("name", ""))
        if ip is None:
            return None

        host = ParsedHost(
            ip=ip,
            hostname=tags.get("hostname", ""),
            fqdn=tags.get("host-fqdn", "") or tags.get("host-rdns", ""),
            netbios=tags.get("netbios-name", ""),
            mac=tags.get("mac-address", "").replace("\n", ", "),
            os=tags.get("operating-system", "").split("\n")[0],
            started_at=_host_time(tags, "HOST_START"),
            ended_at=_host_time(tags, "HOST_END"),
            credentialed=tags.get("Credentialed_Scan", "").lower() == "true",
        )
        for item in node.iterfind("ReportItem"):
            parsed = self._read_item(item)
            if parsed is not None:
                host.items.append(parsed)
        return host

    def _read_item(self, item: etree._Element) -> ParsedItem | None:
        try:
            plugin_id = int(item.get("pluginID", ""))
        except ValueError:
            return None

        fields: dict[str, list[str]] = {}
        for child in item:
            if isinstance(child.tag, str):
                fields.setdefault(child.tag, []).append((child.text or "").strip())

        def one(name: str) -> str:
            values = fields.get(name)
            return values[0] if values else ""

        severity = max(0, min(4, int(item.get("severity", "0") or 0)))
        see_also = [
            line.strip() for v in fields.get("see_also", []) for line in v.splitlines() if line.strip()
        ]
        cwes = [c for v in fields.get("cwe", []) for c in re.split(r"[,\s]+", v) if c]

        plugin = ParsedPlugin(
            id=plugin_id,
            name=item.get("pluginName", "") or one("plugin_name"),
            family=item.get("pluginFamily", ""),
            severity=severity,
            risk_factor=one("risk_factor"),
            synopsis=one("synopsis"),
            description=one("description"),
            solution=one("solution"),
            see_also=see_also,
            cvss2_base=_float(one("cvss_base_score")),
            cvss2_vector=one("cvss_vector"),
            cvss3_base=_float(one("cvss3_base_score")),
            cvss3_vector=one("cvss3_vector"),
            cvss4_base=_float(one("cvss4_base_score")),
            cvss4_vector=one("cvss4_vector"),
            vpr_score=_float(one("vpr_score")),
            epss_score=_float(one("epss_score")),
            cves=sorted(set(fields.get("cve", []))),
            cwes=sorted(set(cwes)),
            exploit_available=one("exploit_available").lower() == "true",
            exploit_frameworks=[
                label for key, label in _EXPLOIT_FRAMEWORKS.items() if one(key).lower() == "true"
            ],
            exploitability_ease=one("exploitability_ease"),
            publication_date=_date(one("plugin_publication_date")),
            patch_publication_date=_date(one("patch_publication_date")),
            vuln_publication_date=_date(one("vuln_publication_date")),
            cpe=one("cpe").split()[0][:512] if one("cpe") else "",
        )
        try:
            port = int(item.get("port", "0") or 0)
        except ValueError:
            port = 0
        return ParsedItem(
            plugin=plugin,
            port=port,
            protocol=(item.get("protocol", "tcp") or "tcp").lower()[:8],
            service=item.get("svc_name", "")[:64],
            severity=severity,
            output=one("plugin_output"),
        )
