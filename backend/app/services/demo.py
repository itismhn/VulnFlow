"""Synthetic, fully fictional `.nessus` generator for tests, demos, and screenshots.

Never commit real scan exports: they reveal internal IPs, hostnames, and weaknesses.
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from lxml import etree


@dataclass(frozen=True)
class DemoVuln:
    plugin_id: int
    name: str
    family: str
    severity: int
    port: int
    svc: str
    cvss3: float | None = None
    cves: tuple[str, ...] = ()
    exploit: bool = False
    os: str = "any"  # "windows" | "linux" | "any"
    vpr: float | None = None


CATALOG: list[DemoVuln] = [
    DemoVuln(
        97833,
        "MS17-010: Security Update for Microsoft Windows SMB Server",
        "Windows",
        4,
        445,
        "cifs",
        8.1,
        ("CVE-2017-0144", "CVE-2017-0145"),
        True,
        "windows",
        9.7,
    ),
    DemoVuln(
        125313,
        "Microsoft RDP RCE (CVE-2019-0708) (BlueKeep)",
        "Windows",
        4,
        3389,
        "msrdp",
        9.8,
        ("CVE-2019-0708",),
        True,
        "windows",
        9.6,
    ),
    DemoVuln(
        155999,
        "Apache Log4j < 2.15.0 Remote Code Execution",
        "Misc.",
        4,
        8080,
        "www",
        10.0,
        ("CVE-2021-44228",),
        True,
        "linux",
        10.0,
    ),
    DemoVuln(
        108797,
        "Unsupported Windows OS (remote)",
        "Windows",
        4,
        0,
        "general",
        10.0,
        (),
        False,
        "windows",
        None,
    ),
    DemoVuln(
        201198,
        "OpenSSH < 9.8 Race Condition RCE (regreSSHion)",
        "Misc.",
        3,
        22,
        "ssh",
        8.1,
        ("CVE-2024-6387",),
        True,
        "linux",
        8.4,
    ),
    DemoVuln(
        100464,
        "Microsoft Windows SMBv1 Multiple Vulnerabilities",
        "Windows",
        3,
        445,
        "cifs",
        8.1,
        ("CVE-2017-0279",),
        True,
        "windows",
        7.4,
    ),
    DemoVuln(
        34460, "Unsupported Web Server Detection", "Web Servers", 3, 80, "www", 10.0, (), False, "any", None
    ),
    DemoVuln(
        42873,
        "SSL Medium Strength Cipher Suites Supported (SWEET32)",
        "General",
        3,
        443,
        "www",
        7.5,
        ("CVE-2016-2183",),
        False,
        "any",
        6.1,
    ),
    DemoVuln(
        171356,
        "Apache 2.4.x < 2.4.56 Multiple Vulnerabilities",
        "Web Servers",
        3,
        443,
        "www",
        9.8,
        ("CVE-2023-25690",),
        False,
        "linux",
        6.7,
    ),
    DemoVuln(
        51192, "SSL Certificate Cannot Be Trusted", "General", 2, 443, "www", 6.5, (), False, "any", None
    ),
    DemoVuln(57582, "SSL Self-Signed Certificate", "General", 2, 443, "www", 6.5, (), False, "any", None),
    DemoVuln(
        104743,
        "TLS Version 1.0 Protocol Detection",
        "Service detection",
        2,
        443,
        "www",
        6.5,
        (),
        False,
        "any",
        None,
    ),
    DemoVuln(
        157288,
        "TLS Version 1.1 Deprecated Protocol",
        "Service detection",
        2,
        443,
        "www",
        6.5,
        (),
        False,
        "any",
        None,
    ),
    DemoVuln(57608, "SMB Signing not required", "Misc.", 2, 445, "cifs", 5.3, (), False, "windows", None),
    DemoVuln(
        58453,
        "Terminal Services Doesn't Use Network Level Authentication (NLA) Only",
        "Misc.",
        2,
        3389,
        "msrdp",
        4.0,
        (),
        False,
        "windows",
        None,
    ),
    DemoVuln(
        18405,
        "Remote Desktop Protocol Server Man-in-the-Middle Weakness",
        "Windows",
        2,
        3389,
        "msrdp",
        6.5,
        ("CVE-2005-1794",),
        False,
        "windows",
        4.9,
    ),
    DemoVuln(42263, "Unencrypted Telnet Server", "Misc.", 2, 23, "telnet", 6.5, (), False, "linux", None),
    DemoVuln(
        11213,
        "HTTP TRACE / TRACK Methods Allowed",
        "Web Servers",
        2,
        80,
        "www",
        5.3,
        ("CVE-2003-1567",),
        False,
        "any",
        4.0,
    ),
    DemoVuln(90317, "SSH Weak Algorithms Supported", "Misc.", 2, 22, "ssh", 4.3, (), False, "linux", None),
    DemoVuln(
        35291,
        "SSL Certificate Signed Using Weak Hashing Algorithm",
        "General",
        2,
        443,
        "www",
        7.5,
        ("CVE-2004-2761",),
        False,
        "any",
        4.5,
    ),
    DemoVuln(15901, "SSL Certificate Expiry", "General", 2, 443, "www", 5.3, (), False, "any", None),
    DemoVuln(
        70658,
        "SSH Server CBC Mode Ciphers Enabled",
        "Misc.",
        1,
        22,
        "ssh",
        3.7,
        ("CVE-2008-5161",),
        False,
        "linux",
        2.5,
    ),
    DemoVuln(71049, "SSH Weak MAC Algorithms Enabled", "Misc.", 1, 22, "ssh", None, (), False, "linux", None),
    DemoVuln(
        10114,
        "ICMP Timestamp Request Remote Date Disclosure",
        "General",
        1,
        0,
        "general",
        None,
        ("CVE-1999-0524",),
        False,
        "any",
        4.2,
    ),
    DemoVuln(
        83875,
        "SSL/TLS Diffie-Hellman Modulus <= 1024 Bits (Logjam)",
        "Misc.",
        1,
        443,
        "www",
        3.7,
        ("CVE-2015-4000",),
        False,
        "any",
        4.5,
    ),
    DemoVuln(19506, "Nessus Scan Information", "Settings", 0, 0, "general"),
    DemoVuln(10863, "SSL Certificate Information", "General", 0, 443, "www"),
    DemoVuln(22964, "Service Detection", "Service detection", 0, 443, "www"),
    DemoVuln(11219, "Nessus SYN scanner", "Port scanners", 0, 443, "www"),
    DemoVuln(45590, "Common Platform Enumeration (CPE)", "General", 0, 0, "general"),
]

NETWORKS = [
    ("Core Banking", "10.10.0.0/24", "Core Banking", 5),
    ("Card Processing", "10.11.0.0/24", "Cards / PCI", 5),
    ("Internet DMZ", "10.20.0.0/24", "DMZ", 4),
    ("Corporate Servers", "10.30.0.0/24", "Corporate", 3),
    ("Branch Network", "10.40.0.0/22", "Branch", 2),
]

_OS = {
    "windows": [
        "Microsoft Windows Server 2019 Standard",
        "Microsoft Windows Server 2016",
        "Microsoft Windows Server 2012 R2",
        "Microsoft Windows 10 Enterprise",
    ],
    "linux": [
        "Red Hat Enterprise Linux 8",
        "Ubuntu 22.04 LTS",
        "Oracle Linux 7",
        "SUSE Linux Enterprise Server 15",
    ],
}


@dataclass
class DemoHost:
    ip: str
    hostname: str
    os_kind: str
    os: str
    vulns: list[DemoVuln]


def build_hosts(seed: int = 7, per_network: int = 12) -> list[DemoHost]:
    rng = random.Random(seed)
    hosts: list[DemoHost] = []
    for _name, cidr, zone, _crit in NETWORKS:
        base = cidr.split("/")[0].rsplit(".", 1)[0]
        prefix = zone.split()[0].lower().replace("/", "")
        for i in range(per_network):
            kind = rng.choice(["windows", "linux"])
            pool = [v for v in CATALOG if v.os in (kind, "any")]
            infos = [v for v in pool if v.severity == 0]
            risky = [v for v in pool if v.severity > 0]
            # Higher-criticality zones are, unhelpfully, a bit worse in the demo
            k = rng.randint(2, min(len(risky), 9))
            hosts.append(
                DemoHost(
                    ip=f"{base}.{10 + i * 3}",
                    hostname=f"{prefix}-{kind[:3]}-{i + 1:02d}",
                    os_kind=kind,
                    os=rng.choice(_OS[kind]),
                    vulns=infos + rng.sample(risky, k),
                )
            )
    return hosts


def evolve(
    hosts: list[DemoHost], seed: int, fix_ratio: float = 0.3, new_ratio: float = 0.15
) -> list[DemoHost]:
    """Next month's state: some vulns get patched, some new ones appear."""
    rng = random.Random(seed)
    out = []
    for h in hosts:
        kept = [v for v in h.vulns if v.severity == 0 or rng.random() > fix_ratio]
        pool = [v for v in CATALOG if v.os in (h.os_kind, "any") and v not in kept and v.severity > 0]
        if pool and rng.random() < new_ratio * 3:
            kept.append(rng.choice(pool))
        out.append(DemoHost(h.ip, h.hostname, h.os_kind, h.os, kept))
    return out


def write_nessus(
    path: Path,
    hosts: list[DemoHost],
    scan_time: datetime,
    report_name: str = "Monthly Internal Scan",
    policy_name: str = "Advanced Network Scan",
    credentialed: bool = True,
) -> Path:
    root = etree.Element("NessusClientData_v2")
    policy = etree.SubElement(root, "Policy")
    etree.SubElement(policy, "policyName").text = policy_name
    report = etree.SubElement(root, "Report", name=report_name)

    for idx, h in enumerate(hosts):
        start = scan_time + timedelta(seconds=idx * 20)
        end = start + timedelta(minutes=4)
        rh = etree.SubElement(report, "ReportHost", name=h.ip)
        props = etree.SubElement(rh, "HostProperties")
        for name, value in (
            ("HOST_START_TIMESTAMP", str(int(start.timestamp()))),
            ("HOST_END_TIMESTAMP", str(int(end.timestamp()))),
            ("host-ip", h.ip),
            ("hostname", h.hostname),
            ("host-fqdn", f"{h.hostname}.bank.example"),
            ("netbios-name", h.hostname.upper()[:15] if h.os_kind == "windows" else ""),
            ("operating-system", h.os),
            ("Credentialed_Scan", "true" if credentialed else "false"),
        ):
            if value:
                etree.SubElement(props, "tag", name=name).text = value
        for v in h.vulns:
            item = etree.SubElement(
                rh,
                "ReportItem",
                port=str(v.port),
                svc_name=v.svc,
                protocol="tcp" if v.port else "icmp" if v.plugin_id == 10114 else "tcp",
                severity=str(v.severity),
                pluginID=str(v.plugin_id),
                pluginName=v.name,
                pluginFamily=v.family,
            )
            risk = ["None", "Low", "Medium", "High", "Critical"][v.severity]
            fields: list[tuple[str, str]] = [
                ("risk_factor", risk),
                ("synopsis", f"Synthetic demo finding: {v.name}."),
                ("description", f"This is fictional demo data describing '{v.name}'."),
                ("solution", "Apply the vendor-recommended update or configuration change."),
                ("plugin_output", f"Demo output for {h.ip}:{v.port}\nDetected by synthetic generator."),
                ("plugin_publication_date", "2020/01/15"),
            ]
            if v.cvss3 is not None:
                fields.append(("cvss3_base_score", str(v.cvss3)))
                fields.append(("cvss3_vector", "CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"))
            if v.vpr is not None:
                fields.append(("vpr_score", str(v.vpr)))
            fields.extend(("cve", c) for c in v.cves)
            if v.exploit:
                fields.append(("exploit_available", "true"))
                fields.append(("exploit_framework_metasploit", "true"))
            for tag, text in fields:
                etree.SubElement(item, tag).text = text

    path.parent.mkdir(parents=True, exist_ok=True)
    etree.ElementTree(root).write(str(path), xml_declaration=True, encoding="UTF-8", pretty_print=True)
    return path


def generate_series(out_dir: Path, months: int = 4, seed: int = 7, per_network: int = 12) -> list[Path]:
    """A sequence of monthly scans showing remediation progress over time."""
    now = datetime.now(UTC).replace(hour=2, minute=0, second=0, microsecond=0)
    hosts = build_hosts(seed, per_network)
    paths = []
    for m in range(months):
        when = now - timedelta(days=30 * (months - 1 - m))
        paths.append(
            write_nessus(
                out_dir / f"demo-scan-{when:%Y-%m}.nessus",
                hosts,
                when,
                report_name=f"Monthly Internal Scan {when:%b %Y}",
            )
        )
        hosts = evolve(hosts, seed + m + 1)
    return paths
