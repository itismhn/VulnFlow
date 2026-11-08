"""Pull software names and versions out of Nessus plugin output.

Nessus has no single "inventory" section. Versions are spread across the CPE
plugin, package and installed-software enumerations, service banners, and the
"Version : x" blocks that detection plugins print. Each extractor here handles
one of those shapes. Results are best-effort: credentialed scans report exact
versions, uncredentialed scans only what a service discloses.
"""

import re
from dataclasses import dataclass, replace
from urllib.parse import unquote

OS = "os"
APPLICATION = "application"
PACKAGE = "package"
SERVICE = "service"
HARDWARE = "hardware"
CATEGORIES = (OS, APPLICATION, PACKAGE, SERVICE, HARDWARE)

PLUGIN_CPE = 45590
PLUGIN_PACKAGES_SSH = 22869
PLUGIN_WINDOWS_SOFTWARE = 20811
PLUGIN_HTTP_SERVER = 10107
PLUGIN_SSH_SERVER = 10267
PLUGIN_ORACLE_TNS = 10658

# Info plugins whose "Version" lines are not about installed software
_IGNORED_PLUGINS = {
    19506,  # Nessus Scan Information
    10863,  # SSL Certificate Information
    11936,  # OS Identification (the host's OS comes from its properties)
    10287,  # Traceroute
    56984,  # SSL / TLS Versions Supported
    66334,  # Patch Report
}
_IGNORED_FAMILIES = {"Settings", "Port scanners"}

MAX_ITEMS_PER_OUTPUT = 5000


@dataclass(frozen=True, slots=True)
class Software:
    category: str
    name: str
    version: str = ""
    vendor: str = ""
    product: str = ""
    cpe: str = ""
    path: str = ""

    @property
    def key(self) -> str:
        """Grouping key: CPE product when known, otherwise the lowercased name."""
        return (self.product or self.name).lower()


def version_key(version: str) -> str:
    """A string that sorts like the version under byte (C) collation.

    Numeric parts are zero-padded so 2.4.9 < 2.4.41, letters sort before
    numbers, and a shorter version sorts before its extensions (8.2 < 8.2p1).
    """
    parts = re.findall(r"\d+|[a-z]+", version.lower())
    out = []
    for part in parts[:24]:
        if part.isdigit():
            out.append("#" + part[-12:].zfill(12))
        else:
            out.append("!" + part[:16])
    return "".join(out)


# --- Product identity --------------------------------------------------------
# Plugins without a CPE report software by display name only, often with the
# version and architecture baked in ("7-Zip 19.00 (x64)", "Java 8 Update 361").
# Cleaning those names and mapping them to a CPE-style vendor and product makes
# every version of one product land in one group, under its vendor.

# Leading name words -> CPE vendor id. Longest match wins.
_VENDOR_PREFIXES = {
    "7-zip": "7-zip",
    "adobe": "adobe",
    "amazon": "amazon",
    "anydesk": "anydesk",
    "apache": "apache",
    "atlassian": "atlassian",
    "broadcom": "broadcom",
    "centos": "centos",
    "check point": "checkpoint",
    "cisco": "cisco",
    "citrix": "citrix",
    "debian": "debian",
    "dell": "dell",
    "elastic": "elastic",
    "eset": "eset",
    "f5": "f5",
    "fortinet": "fortinet",
    "git": "git-scm",
    "google": "google",
    "hp": "hp",
    "hewlett packard enterprise": "hpe",
    "ibm": "ibm",
    "intel": "intel",
    "jetbrains": "jetbrains",
    "kaspersky": "kaspersky",
    "mariadb": "mariadb",
    "mcafee": "mcafee",
    "microsoft": "microsoft",
    "mongodb": "mongodb",
    "mozilla": "mozilla",
    "mysql": "oracle",
    "notepad++": "notepad-plus-plus",
    "nvidia": "nvidia",
    "openvpn": "openvpn",
    "oracle": "oracle",
    "palo alto networks": "paloaltonetworks",
    "postgresql": "postgresql",
    "putty": "putty",
    "python": "python",
    "red hat": "redhat",
    "sap": "sap",
    "suse": "suse",
    "symantec": "symantec",
    "teamviewer": "teamviewer",
    "trend micro": "trendmicro",
    "veeam": "veeam",
    "veritas": "veritas",
    "vmware": "vmware",
    "winrar": "rarlab",
    "wireshark": "wireshark",
    "zoom": "zoom",
}
_VENDOR_PREFIX_ORDER = sorted(_VENDOR_PREFIXES, key=len, reverse=True)

# Cleaned, lowercased names whose CPE product differs from the name
_NAME_ALIASES: dict[str, tuple[str, str]] = {
    "oracle database": ("oracle", "database_server"),
    "oracle database server": ("oracle", "database_server"),
    "java": ("oracle", "jre"),
    "oracle java": ("oracle", "jre"),
    "java se runtime environment": ("oracle", "jre"),
    "java se development kit": ("oracle", "jdk"),
    "mysql": ("oracle", "mysql"),
    "mysql server": ("oracle", "mysql"),
    "ubuntu": ("canonical", "ubuntu_linux"),
    "microsoft iis": ("microsoft", "internet_information_services"),
    "openssl": ("openssl", "openssl"),
    "openssh": ("openbsd", "openssh"),
}

# Linux package names that are the same product as a CPE detection. The package
# keeps its own name; only its vendor and product join it to that group.
_PACKAGE_ALIASES: list[tuple[re.Pattern[str], tuple[str, str]]] = [
    (re.compile(r"openssl"), ("openssl", "openssl")),
    (re.compile(r"openssh(?:-server|-client|-clients)?"), ("openbsd", "openssh")),
    (
        re.compile(r"(?:java-[\d.]+-|java-)?openjdk(?:-\d+)?(?:-jre|-jdk)?(?:-headless)?"),
        ("oracle", "openjdk"),
    ),
    (re.compile(r"mysql-server(?:-[\d.]+)?"), ("oracle", "mysql")),
]

VENDOR_LABELS = {
    "7-zip": "7-Zip",
    "apache": "Apache",
    "canonical": "Canonical",
    "checkpoint": "Check Point",
    "f5": "F5",
    "git-scm": "Git",
    "hp": "HP",
    "hpe": "HPE",
    "ibm": "IBM",
    "mariadb": "MariaDB",
    "mongodb": "MongoDB",
    "notepad-plus-plus": "Notepad++",
    "nvidia": "NVIDIA",
    "openbsd": "OpenBSD",
    "openssl": "OpenSSL",
    "openvpn": "OpenVPN",
    "paloaltonetworks": "Palo Alto Networks",
    "postgresql": "PostgreSQL",
    "putty": "PuTTY",
    "rarlab": "RARLAB",
    "redhat": "Red Hat",
    "sap": "SAP",
    "suse": "SUSE",
    "teamviewer": "TeamViewer",
    "trendmicro": "Trend Micro",
    "vmware": "VMware",
}

_ARCH_PAREN = re.compile(r"\s*\([^)]*\b(?:x64|x86|64-bit|32-bit|amd64|x86_64|arm64)\b[^)]*\)", re.I)
_ARCH_WORDS = {"x64", "x86", "64-bit", "32-bit", "amd64", "x86_64", "arm64"}
_COUNTER_WORDS = {"update", "build", "sp", "version", "release", "rev"}


def vendor_label(vendor: str) -> str:
    return VENDOR_LABELS.get(vendor) or (_humanize(vendor) if vendor else "")


def clean_software_name(name: str, version: str = "") -> str:
    """'Java 8 Update 361 (64-bit)' -> 'Java'; '7-Zip 19.00 (x64)' -> '7-Zip'.

    Drops dotted versions, years, the version's own major number, "Update N" style
    counters, and architecture tags, so every version shares one name.
    """
    major = m.group(0) if (m := re.match(r"\d+", version)) else ""
    tokens = _ARCH_PAREN.sub("", name).split()
    kept: list[str] = []
    skip = False
    for i, tok in enumerate(tokens):
        low = tok.lower().strip(",;")
        if skip:
            skip = False
            if re.fullmatch(r"\d[\w.]*", low):
                continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if low in _COUNTER_WORDS and re.fullmatch(r"\d[\w.]*", nxt):
            skip = True
            continue
        if (
            low in _ARCH_WORDS
            or re.fullmatch(r"v?\d+(?:[._-]\d+)+[a-z0-9]*", low)  # 19.00, 2015-2022, 1.8.0_351
            or re.fullmatch(r"(?:19|20)\d\d", low)  # 2015, 2019
            or re.fullmatch(r"sp\d+|r\d", low)
            or (major and re.fullmatch(rf"v?{major}[a-z]{{0,2}}\d*", low))  # 8, 19c
        ):
            continue
        kept.append(tok)
    cleaned = re.sub(r"[\s\-\u2013,:]+$", "", " ".join(kept)).strip()
    return cleaned or name.strip()


def _snake(text: str) -> str:
    return re.sub(r"[^\w.+\-]+", "_", text.lower()).strip("_")


def identify(name: str) -> tuple[str, str]:
    """(vendor, product) for a cleaned display name; ('', '') when the vendor is unknown."""
    low = name.lower().strip()
    if low in _NAME_ALIASES:
        return _NAME_ALIASES[low]
    for prefix in _VENDOR_PREFIX_ORDER:
        if low == prefix or (low.startswith(prefix) and low[len(prefix)] in " -_/"):
            rest = low[len(prefix) :].strip(" -_/")
            vendor = _VENDOR_PREFIXES[prefix]
            alias = _NAME_ALIASES.get(f"{prefix} {rest}")
            if alias:
                return alias
            return vendor, _snake(rest or prefix)
    return "", ""


def normalize(sw: Software) -> Software:
    """Fill in vendor and product for software a plugin named without a CPE."""
    if sw.vendor and sw.product:
        return sw
    if sw.category == PACKAGE:
        for pattern, (vendor, product) in _PACKAGE_ALIASES:
            if pattern.fullmatch(sw.name.lower()):
                return replace(sw, vendor=vendor, product=product)
        return sw
    name = clean_software_name(sw.name, sw.version) if not sw.product else sw.name
    vendor, product = identify(name)
    if sw.vendor and vendor and vendor != sw.vendor:
        product = ""  # the name names another vendor's product; trust the CPE vendor
    return replace(sw, name=name[:255], vendor=sw.vendor or vendor, product=sw.product or product[:255])


# --- CPE -------------------------------------------------------------------

_CPE_RE = re.compile(r"(?:x-)?cpe:(?:/|2\.3:)([aoh]):([^\s]+?)(?:\s+->\s+(.+))?\s*$")
_CPE_CATEGORY = {"a": APPLICATION, "o": OS, "h": HARDWARE}
_EMPTY = {"", "*", "-"}


def _humanize(product: str) -> str:
    words = unquote(product).replace("_", " ").split()
    return " ".join(w if any(c.isupper() for c in w) else w.capitalize() for w in words)


def parse_cpe(text: str) -> Software | None:
    match = _CPE_RE.search(text.strip())
    if not match:
        return None
    part, rest, title = match.groups()
    fields = [unquote(f).replace("\\", "") for f in rest.split(":")]
    vendor = fields[0] if fields and fields[0] not in _EMPTY else ""
    product = fields[1] if len(fields) > 1 and fields[1] not in _EMPTY else ""
    if not product:
        return None
    version = fields[2] if len(fields) > 2 and fields[2] not in _EMPTY else ""
    update = fields[3] if len(fields) > 3 and fields[3] not in _EMPTY else ""
    if version and update:
        # OpenSSH-style patch levels read as one version: 8.2 + p1 -> 8.2p1
        version = f"{version}{update}" if re.fullmatch(r"p\d+", update) else f"{version} {update}"
    name = (title or "").strip()
    if name and (lead := re.match(r"\d[\d.]*\d|\d", version)):
        # "Apache HTTP Server 2.4.41" -> "Apache HTTP Server"
        name = re.sub(rf"\s+v?{re.escape(lead.group(0))}.*$", "", name).strip() or name
    if not name:
        same = vendor in ("", product)
        name = _humanize(product) if same else f"{_humanize(vendor)} {_humanize(product)}"
    cpe = match.group(0).split(" -> ")[0].strip()
    return Software(
        category=_CPE_CATEGORY[part],
        name=name[:255],
        version=version[:128],
        vendor=vendor.lower()[:128],
        product=product.lower()[:255],
        cpe=cpe[:512],
    )


def _from_cpe_list(output: str) -> list[Software]:
    found = []
    for line in output.splitlines():
        if "cpe:" in line:
            sw = parse_cpe(line)
            if sw:
                found.append(sw)
    return found


# --- Package and installed-software enumerations ---------------------------

_DPKG_RE = re.compile(r"^\s*[a-z]i\s+(\S+)\s+(\S+)")
_RPM_RE = re.compile(r"^\s*([A-Za-z0-9][\w.+\-]*?)-(\d[^-\s|]*)-([^\s|]+?)(?:\|.*)?$")
_WIN_RE = re.compile(r"^\s*(.+?)\s+\[version ([^\]]+)\]")


def _from_packages(output: str) -> list[Software]:
    found = []
    for line in output.splitlines():
        if m := _DPKG_RE.match(line):
            name, version = m.group(1).split(":")[0], m.group(2)
        elif _RPM_RE.match(line):
            # name-version-release: the name may itself contain digits and dashes
            name, ver, rel = line.strip().split("|")[0].rsplit("-", 2)
            version = f"{ver}-{rel}"
            # Drop a trailing architecture: 34.el7.x86_64 -> 34.el7
            version = re.sub(r"\.(x86_64|i[3-6]86|noarch|aarch64|ppc64le|s390x)$", "", version)
        else:
            continue
        found.append(Software(PACKAGE, name[:255], version[:128], product=name.lower()[:255]))
    return found


def _from_windows_software(output: str) -> list[Software]:
    found = []
    for line in output.splitlines():
        if m := _WIN_RE.match(line):
            name, version = m.group(1).strip(), m.group(2).strip()
            # "Visual C++ Runtime - 14.0.23026  [version 14.0.23026]" -> "Visual C++ Runtime"
            name = re.sub(rf"\s*(?:-\s*)?v?{re.escape(version)}$", "", name) or name
            found.append(Software(APPLICATION, name[:255], version[:128]))
    return found


# --- Service banners -------------------------------------------------------

_BANNER_RE = re.compile(r"([A-Za-z][\w\-. ]*?)/v?(\d[\w.\-]*)")
_SSH_RE = re.compile(r"SSH-[\d.]+-([A-Za-z][A-Za-z.\-]*?)[_\-]v?(\d[\w.]*)")
_TNS_RE = re.compile(r"TNSLSNR for [^:]+:\s*Version\s+([\d.]+)", re.IGNORECASE)


# Banner names -> CPE vendor/product, so banners group with credentialed detections
_BANNER_ALIASES = {
    "apache": ("Apache HTTP Server", "apache", "http_server"),
    "microsoft-iis": ("Microsoft IIS", "microsoft", "internet_information_services"),
    "nginx": ("nginx", "f5", "nginx"),
    "openssh": ("OpenSSH", "openbsd", "openssh"),
    "lighttpd": ("lighttpd", "lighttpd", "lighttpd"),
    "apache-coyote": ("Apache Tomcat", "apache", "tomcat"),
}


def _service(name: str, version: str = "") -> Software:
    alias = _BANNER_ALIASES.get(name.lower())
    if alias:
        return Software(SERVICE, alias[0], version[:128], vendor=alias[1], product=alias[2])
    return Software(SERVICE, name[:255], version[:128])


def _from_http_banner(output: str) -> list[Software]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return []
    banner = lines[-1]
    found = [_service(m.group(1).strip(), m.group(2)) for m in _BANNER_RE.finditer(banner)]
    if not found and ":" not in banner:
        found.append(_service(banner.split()[0]))
    return found[:5]


def _from_ssh_banner(output: str) -> list[Software]:
    m = _SSH_RE.search(output)
    return [_service(m.group(1), m.group(2))] if m else []


def _from_oracle_tns(output: str) -> list[Software]:
    m = _TNS_RE.search(output)
    if not m:
        return []
    return [Software(SERVICE, "Oracle Database", m.group(1), vendor="oracle", product="database_server")]


# --- Generic "Version : x" detection blocks --------------------------------

_VERSION_LINE = re.compile(
    r"^\s*(?:installed |remote |product |detected |file |reported |)version\s*:\s*(\S.*?)\s*$", re.I
)
_PATH_LINE = re.compile(r"^\s*(?:path|location|install(?:ation)? path|file)\s*:\s*(\S.*?)\s*$", re.I)
_PRODUCT_LINE = re.compile(r"^\s*(?:product|product name|application|name|edition)\s*:\s*(\S.*?)\s*$", re.I)
_NAME_NOISE = [
    re.compile(
        r"\s*\((?:remote|local|credentialed check|uncredentialed check|windows|linux|unix|"
        r"mac ?os ?x?|macos|nix|network|version check)\)",
        re.I,
    ),
    re.compile(
        r"\s+(?:remote\s+)?(?:version\s+)?(?:detection|disclosure|installed|installation detection|"
        r"install detection|identification|enumeration|version|type and version|"
        r"server detection|service detection|discovery)$",
        re.I,
    ),
]


def clean_plugin_name(name: str) -> str:
    """'Apache Tomcat Detection (Remote)' -> 'Apache Tomcat'."""
    previous = None
    while previous != name:
        previous = name
        for pattern in _NAME_NOISE:
            name = pattern.sub("", name).strip()
    return name


def _from_version_blocks(output: str, plugin_name: str, plugin_cpe: str, category: str) -> list[Software]:
    base = parse_cpe(plugin_cpe) if plugin_cpe else None
    default_name = clean_plugin_name(plugin_name) or plugin_name
    found = []
    for block in re.split(r"\n\s*\n", output):
        version = path = product = ""
        for line in block.splitlines():
            if not version and (m := _VERSION_LINE.match(line)):
                version = m.group(1)
            elif not path and (m := _PATH_LINE.match(line)):
                path = m.group(1)
            elif not product and (m := _PRODUCT_LINE.match(line)):
                product = m.group(1)
        if not version or len(version) > 64:
            continue
        name = product if product and len(product) <= 128 else (base.name if base else default_name)
        found.append(
            Software(
                category,
                name[:255],
                version[:128],
                vendor=base.vendor if base else "",
                product=base.product if base and not product else "",
                cpe=base.cpe if base else "",
                path=path[:512],
            )
        )
    return found


def extract(
    plugin_id: int,
    plugin_name: str,
    plugin_family: str,
    plugin_cpe: str,
    output: str,
    port: int = 0,
) -> list[Software]:
    """Software reported by one informational plugin result."""
    if not output or plugin_id in _IGNORED_PLUGINS or plugin_family in _IGNORED_FAMILIES:
        return []
    if plugin_id == PLUGIN_CPE:
        found = _from_cpe_list(output)
    elif plugin_id == PLUGIN_PACKAGES_SSH:
        found = _from_packages(output)
    elif plugin_id == PLUGIN_WINDOWS_SOFTWARE:
        found = _from_windows_software(output)
    elif plugin_id == PLUGIN_HTTP_SERVER:
        found = _from_http_banner(output)
    elif plugin_id == PLUGIN_SSH_SERVER:
        found = _from_ssh_banner(output)
    elif plugin_id == PLUGIN_ORACLE_TNS:
        found = _from_oracle_tns(output)
    else:
        found = _from_version_blocks(output, plugin_name, plugin_cpe, SERVICE if port else APPLICATION)
    return [normalize(sw) for sw in found[:MAX_ITEMS_PER_OUTPUT]]


def split_os(os_name: str) -> tuple[str, str]:
    """'Microsoft Windows Server 2012 R2' -> ('Microsoft Windows Server', '2012 R2')."""
    m = re.match(r"^(.*?)\s+((?:v?\d[\w.\-]*|XP|Vista)(?:\s.*)?)$", os_name.strip())
    if not m or not m.group(1):
        return os_name.strip(), ""
    return m.group(1), m.group(2)
