from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.demo import build_hosts, software_items, write_nessus
from app.services.parsers import ParseError, get_parser
from app.services.parsers.nessus import NessusParser

MINIMAL = """<?xml version="1.0" ?>
<NessusClientData_v2>
<Policy><policyName>Bank Policy</policyName>
  <Preferences/>
  <FamilySelection>
    <FamilyItem><FamilyName>Windows</FamilyName><Status>disabled</Status></FamilyItem>
    <FamilyItem><FamilyName>General</FamilyName><Status>enabled</Status></FamilyItem>
  </FamilySelection>
</Policy>
<Report name="Weekly DMZ">
 <ReportHost name="web01.bank.example">
  <HostProperties>
   <tag name="HOST_START">Mon Oct  5 10:00:00 2026</tag>
   <tag name="host-ip">10.20.0.5</tag>
   <tag name="hostname">web01</tag>
   <tag name="operating-system">Ubuntu 22.04
Linux Kernel 5.15</tag>
   <tag name="Credentialed_Scan">true</tag>
  </HostProperties>
  <ReportItem port="443" svc_name="www" protocol="tcp" severity="3" pluginID="42873" pluginName="SSL Medium Strength Cipher Suites" pluginFamily="General">
   <description>Desc with unicode: café ✓</description>
   <solution>Reconfigure.</solution>
   <cvss3_base_score>7.5</cvss3_base_score>
   <cve>CVE-2016-2183</cve>
   <cve>CVE-2016-6329</cve>
   <see_also>https://a.example
https://b.example</see_also>
   <exploit_available>true</exploit_available>
   <exploit_framework_metasploit>true</exploit_framework_metasploit>
   <plugin_publication_date>2009/11/23</plugin_publication_date>
   <plugin_output>TLS 1.2 DES-CBC3-SHA</plugin_output>
  </ReportItem>
  <ReportItem port="0" svc_name="general" protocol="tcp" severity="0" pluginID="19506" pluginName="Nessus Scan Information" pluginFamily="Settings"/>
  <ReportItem port="1" severity="2" pluginID="not-a-number" pluginName="Broken"/>
 </ReportHost>
 <ReportHost name="no-ip-host"><HostProperties/></ReportHost>
</Report>
</NessusClientData_v2>
"""


def test_parses_hosts_items_and_policy(tmp_path: Path) -> None:
    path = tmp_path / "scan.nessus"
    path.write_text(MINIMAL, encoding="utf-8")
    parser = get_parser(path)
    hosts = list(parser.iter_hosts(path))

    assert parser.meta.policy_name == "Bank Policy"
    assert parser.meta.report_name == "Weekly DMZ"
    assert parser.meta.disabled_families == ["Windows"]
    assert parser.meta.skipped_hosts == 1
    assert len(hosts) == 1

    host = hosts[0]
    assert host.ip == "10.20.0.5"
    assert host.os == "Ubuntu 22.04"
    assert host.credentialed is True
    assert host.started_at == datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
    assert len(host.items) == 2  # the item with a bad plugin id is dropped

    item = host.items[0]
    assert item.port == 443 and item.severity == 3
    assert item.plugin.cvss3_base == 7.5
    assert item.plugin.cves == ["CVE-2016-2183", "CVE-2016-6329"]
    assert item.plugin.see_also == ["https://a.example", "https://b.example"]
    assert item.plugin.exploit_available and item.plugin.exploit_frameworks == ["Metasploit"]
    assert "café" in item.plugin.description
    assert item.output == "TLS 1.2 DES-CBC3-SHA"


def test_rejects_non_nessus(tmp_path: Path) -> None:
    path = tmp_path / "x.nessus"
    path.write_text("<html><body>nope</body></html>")
    with pytest.raises(ParseError):
        get_parser(path)


def test_xxe_is_not_resolved(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET")
    payload = f"""<?xml version="1.0"?>
<!DOCTYPE NessusClientData_v2 [<!ENTITY xxe SYSTEM "file://{secret}">]>
<NessusClientData_v2><Report name="r"><ReportHost name="10.0.0.1">
<HostProperties><tag name="host-ip">10.0.0.1</tag><tag name="hostname">&xxe;</tag></HostProperties>
</ReportHost></Report></NessusClientData_v2>"""
    path = tmp_path / "xxe.nessus"
    path.write_text(payload)
    hosts = list(NessusParser().iter_hosts(path))
    assert all("TOP-SECRET" not in h.hostname for h in hosts)


def test_truncated_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "cut.nessus"
    path.write_text(MINIMAL[: len(MINIMAL) // 2])
    with pytest.raises(ParseError):
        list(NessusParser().iter_hosts(path))


def test_demo_generator_roundtrip(tmp_path: Path) -> None:
    hosts = build_hosts(per_network=2)
    path = write_nessus(tmp_path / "demo.nessus", hosts, datetime(2026, 1, 1, tzinfo=UTC))
    parsed = list(NessusParser().iter_hosts(path))
    assert len(parsed) == len(hosts)
    assert sum(len(h.items) for h in parsed) == sum(len(h.vulns) + len(software_items(h)) for h in hosts)
