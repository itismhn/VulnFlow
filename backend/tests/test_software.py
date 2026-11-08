"""Software inventory: extraction from plugin output, and the /software API."""

from pathlib import Path

import pytest

from app.services.software_extract import (
    clean_plugin_name,
    clean_software_name,
    extract,
    identify,
    parse_cpe,
    split_os,
    version_key,
)
from tests.conftest import ApiClient
from tests.test_api_flow import loaded  # noqa: F401  (fixture)

CPE_OUTPUT = """The remote operating system matched the following CPE :

  cpe:/o:canonical:ubuntu_linux:20.04 -> Canonical Ubuntu Linux 20.04

Following application CPE's matched on the remote system :

  cpe:/a:apache:http_server:2.4.41 -> Apache Software Foundation Apache HTTP Server 2.4.41
  cpe:/a:openbsd:openssh:8.2:p1 -> OpenBSD OpenSSH 8.2
  x-cpe:/a:oracle:database_server:19.3.0.0.0
"""


def test_cpe_list() -> None:
    found = extract(45590, "Common Platform Enumeration (CPE)", "General", "", CPE_OUTPUT)
    by_product = {s.product: s for s in found}
    assert by_product["ubuntu_linux"].category == "os"
    assert by_product["http_server"].version == "2.4.41"
    assert by_product["http_server"].vendor == "apache"
    assert by_product["openssh"].version == "8.2p1"
    assert by_product["openssh"].name == "OpenBSD OpenSSH"
    assert by_product["database_server"].version == "19.3.0.0.0"
    assert parse_cpe("cpe:2.3:a:apache:log4j:2.14.1:*:*:*:*:*:*:*").version == "2.14.1"  # type: ignore[union-attr]


def test_package_enumerations() -> None:
    dpkg = "packages :\n\n  ii  openssl   1.1.1f-1ubuntu2.16   amd64   toolkit\n  ii  libc6:amd64  2.31-0ubuntu9.9  amd64  C"
    rpm = "packages :\n\n  bash-4.2.46-34.el7|(none)\n  openssl-libs-1.0.2k-19.el7.x86_64|(none)"
    assert {(s.name, s.version) for s in extract(22869, "", "General", "", dpkg)} == {
        ("openssl", "1.1.1f-1ubuntu2.16"),
        ("libc6", "2.31-0ubuntu9.9"),
    }
    assert {(s.name, s.version) for s in extract(22869, "", "General", "", rpm)} == {
        ("bash", "4.2.46-34.el7"),
        ("openssl-libs", "1.0.2k-19.el7"),
    }
    win = "  Microsoft Visual C++ 2015 x64 Runtime - 14.0.23026  [version 14.0.23026]  [installed on 2020/01/01]"
    [sw] = extract(20811, "", "Windows", "", win)
    assert (sw.name, sw.version, sw.category, sw.vendor) == (
        "Microsoft Visual C++ Runtime",
        "14.0.23026",
        "application",
        "microsoft",
    )


def test_every_version_of_a_product_shares_one_identity() -> None:
    win = (
        "  7-Zip 16.04 (x64)  [version 16.04]\n"
        "  7-Zip 23.01 (x64)  [version 23.01]\n"
        "  Java 8 Update 361 (64-bit)  [version 8.0.3610.9]\n"
        "  Oracle Database 19c  [version 19.3.0.0.0]\n"
        "  Microsoft SQL Server 2019 (64-bit)  [version 15.0.2000.5]\n"
        "  Microsoft 365 Apps for enterprise  [version 16.0.17029.20108]\n"
        "  Some Inhouse Tool 2.1  [version 2.1]"
    )
    found = {(s.name, s.version): (s.vendor, s.product) for s in extract(20811, "", "Windows", "", win)}
    assert found[("7-Zip", "16.04")] == found[("7-Zip", "23.01")] == ("7-zip", "7-zip")
    assert found[("Java", "8.0.3610.9")] == ("oracle", "jre")
    # Same identity as the CPE plugin's cpe:/a:oracle:database_server
    assert found[("Oracle Database", "19.3.0.0.0")] == ("oracle", "database_server")
    assert found[("Microsoft SQL Server", "15.0.2000.5")] == ("microsoft", "sql_server")
    assert found[("Microsoft 365 Apps for enterprise", "16.0.17029.20108")][0] == "microsoft"
    # Unknown vendor: still grouped by its cleaned name across versions
    assert found[("Some Inhouse Tool", "2.1")] == ("", "")

    rpm = "packages :\n\n  java-1.8.0-openjdk-1.8.0.392-1.el8.x86_64|(none)"
    [pkg] = extract(22869, "", "General", "", rpm)
    assert (pkg.name, pkg.vendor, pkg.product) == ("java-1.8.0-openjdk", "oracle", "openjdk")
    assert clean_software_name("Microsoft Visual C++ 2015-2022 Redistributable (x64)") == (
        "Microsoft Visual C++ Redistributable"
    )
    assert identify("Oracle Linux") == ("oracle", "linux")
    assert identify("Red Hat Enterprise Linux") == ("redhat", "enterprise_linux")


def test_banners_and_detection_blocks() -> None:
    [apache] = extract(
        10107, "", "Web Servers", "", "The remote web server type is :\n\nApache/2.4.41 (Ubuntu)", 80
    )
    assert (apache.vendor, apache.product, apache.version) == ("apache", "http_server", "2.4.41")
    [ssh] = extract(10267, "", "Misc.", "", "SSH version : SSH-2.0-OpenSSH_8.2p1 Ubuntu-4ubuntu0.5", 22)
    assert (ssh.product, ssh.version) == ("openssh", "8.2p1")
    [tns] = extract(10658, "", "Databases", "", "TNSLSNR for Linux: Version 19.0.0.0.0 - Production", 1521)
    assert (tns.name, tns.version) == ("Oracle Database", "19.0.0.0.0")

    output = "  Path    : /opt/a/log4j-core-2.14.1.jar\n  Version : 2.14.1\n\n  Path    : /opt/b/x.jar\n  Version : 2.17.1"
    found = extract(156000, "Apache Log4j Installed (Linux / Unix)", "Misc.", "cpe:/a:apache:log4j", output)
    assert [(s.product, s.version, s.path) for s in found] == [
        ("log4j", "2.14.1", "/opt/a/log4j-core-2.14.1.jar"),
        ("log4j", "2.17.1", "/opt/b/x.jar"),
    ]
    # Fixed-version advice and certificate "Version: 3" are not installed software
    assert extract(10863, "SSL Certificate Information", "General", "", "Version : 3") == []
    assert extract(1, "Scan Information", "Settings", "", "Version : 10.6.1") == []
    assert clean_plugin_name("Apache Tomcat Detection (Remote)") == "Apache Tomcat"


def test_version_ordering_and_os_split() -> None:
    ordered = ["2.4.9", "2.4.41", "2.14.1", "2.17.1"]
    assert sorted(ordered, key=version_key) == ordered
    assert version_key("8.2") < version_key("8.2p1") < version_key("8.3")
    assert split_os("Microsoft Windows Server 2012 R2") == ("Microsoft Windows Server", "2012 R2")
    assert split_os("Ubuntu 22.04 LTS") == ("Ubuntu", "22.04 LTS")


@pytest.mark.usefixtures("loaded")
def test_software_inventory_api(loaded: ApiClient, tmp_path: Path) -> None:  # noqa: F811
    stats = loaded.get("/api/v1/software/stats").json()
    assert stats["hosts"] == 20 and stats["products"] > 5
    assert {"os", "package", "service", "application"} <= set(stats["by_category"])

    groups = loaded.get("/api/v1/software", params={"q": "openssl"}).json()
    assert groups["total"] >= 1
    assert all(v["hosts"] > 0 for g in groups["items"] for v in g["versions"])

    oses = loaded.get("/api/v1/software", params={"category": "os"}).json()["items"]
    assert sum(g["hosts"] for g in oses) == 20

    # Version range search: which hosts run log4j older than 2.17.1?
    old = loaded.get(
        "/api/v1/software/instances", params={"product": "log4j", "version": "<2.17.1", "page_size": 500}
    ).json()
    versions = {i["version"] for i in old["items"]}
    assert versions and all(version_key(v) < version_key("2.17.1") for v in versions)
    assert all(i["ip"] and i["finding_id"] for i in old["items"])

    prefix = loaded.get("/api/v1/software/instances", params={"version": "19", "q": "oracle"}).json()
    assert all(i["version"].startswith("19") for i in prefix["items"])

    asset_id = old["items"][0]["asset_id"] if old["items"] else prefix["items"][0]["asset_id"]
    own = loaded.get("/api/v1/software/instances", params={"asset_id": asset_id, "page_size": 500}).json()
    assert own["total"] > 0 and {i["asset_id"] for i in own["items"]} == {asset_id}

    csv_body = loaded.get("/api/v1/software/export", params={"q": "openssh"}).text
    assert csv_body.startswith("IP,Hostname,Network") and "openssh" in csv_body.lower()
    assert loaded.get("/api/v1/software/instances", params={"ip": "nope"}).status_code == 422

    # Vendor view: Oracle collects its database, Java and OS under one entry
    vendors = loaded.get("/api/v1/software/vendors", params={"page_size": 500}).json()["items"]
    by_vendor = {v["vendor"]: v for v in vendors}
    oracle = by_vendor["oracle"]
    assert oracle["label"] == "Oracle" and oracle["product_count"] >= 2
    assert "database_server" in {p["product"] for p in oracle["products"]}
    assert vendors[-1]["vendor"] == "" or "" not in by_vendor  # unknown vendor sorts last
    db_group = loaded.get(
        "/api/v1/software", params={"vendor": "oracle", "product": "database_server"}
    ).json()
    [group] = db_group["items"]
    assert group["name"] == "Oracle Database" and group["version_count"] >= 2
    # "Oracle Database 19c" from the Windows list no longer forms its own product
    assert not loaded.get("/api/v1/software", params={"q": "19c"}).json()["items"]

    # Rebuilding from stored findings gives the same inventory
    before = loaded.get("/api/v1/software/stats").json()
    assert loaded.post("/api/v1/software/rebuild").status_code == 202
    assert loaded.get("/api/v1/software/stats").json() == before


def test_inventory_follows_scan_delete(loaded: ApiClient) -> None:  # noqa: F811
    scans = loaded.get("/api/v1/scans").json()["items"]
    for scan in scans:
        assert loaded.delete(f"/api/v1/scans/{scan['id']}").status_code == 204
    assert loaded.get("/api/v1/software/stats").json()["instances"] == 0
