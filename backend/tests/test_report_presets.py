from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Finding, ReportJob, ReportTemplate
from app.models.enums import ACTIVE_STATUSES, FindingStatus
from app.services.reporting.builtin import BUILTIN_TEMPLATES, ensure_builtin_templates
from app.services.reporting.engine import build_context
from tests import test_api_flow
from tests.conftest import ApiClient

loaded = test_api_flow.loaded


def test_presets_seed_without_overwriting_existing_templates(db) -> None:
    custom = ReportTemplate(
        name="Accepted Risk Review Register",
        kind="technical",
        description="User-authored register",
        builtin=False,
        config={"sections": ["details"]},
    )
    db.add(custom)
    db.commit()
    ensure_builtin_templates(db)
    ensure_builtin_templates(db)
    templates = list(db.scalars(select(ReportTemplate)))
    assert len(templates) == len(BUILTIN_TEMPLATES)
    db.refresh(custom)
    assert not custom.builtin
    assert custom.description == "User-authored register"
    assert custom.config == {"sections": ["details"]}


def test_scenario_reports_use_default_filters_and_render(loaded: ApiClient) -> None:
    now = datetime.now(UTC)
    # Give the scenario filters both matching and non-matching records.
    with SessionLocal() as db:
        findings = list(db.scalars(select(Finding).order_by(Finding.id)))
        for i, finding in enumerate(findings):
            finding.status = (
                FindingStatus.OPEN,
                FindingStatus.REOPENED,
                FindingStatus.RISK_ACCEPTED,
                FindingStatus.FIXED,
            )[i % 4]
            finding.first_seen = now - timedelta(days=120 if i % 3 else 10)
            finding.due_date = date.today() + timedelta(days=-5 if i % 2 else 5)
        db.commit()
        expected = {
            "Critical & High Remediation Plan": {
                f.id for f in findings if f.status in ACTIVE_STATUSES and f.severity in (3, 4)
            },
            "Public Exploit Exposure Brief": {
                f.id
                for f in findings
                if f.status in ACTIVE_STATUSES and f.severity > 0 and f.plugin.exploit_available
            },
            "Overdue Remediation Escalation": {
                f.id
                for f in findings
                if f.status in ACTIVE_STATUSES and f.severity > 0 and f.due_date < date.today()
            },
            "Aging Vulnerability Backlog": {
                f.id
                for f in findings
                if f.status in ACTIVE_STATUSES and f.severity > 0 and f.first_seen < now - timedelta(days=90)
            },
            "Asset Owner Remediation Handoff": {
                f.id for f in findings if f.status in ACTIVE_STATUSES and f.severity > 0
            },
            "Reopened Findings Review": {
                f.id for f in findings if f.status == FindingStatus.REOPENED and f.severity > 0
            },
            "Accepted Risk Review Register": {
                f.id for f in findings if f.status == FindingStatus.RISK_ACCEPTED and f.severity > 0
            },
        }

    templates = loaded.get("/api/v1/report-templates").json()
    assert {t["name"] for t in templates} == {t["name"] for t in BUILTIN_TEMPLATES}
    for template in templates:
        if template["name"] not in expected and template["name"] != "Security Team Operations Review":
            continue
        response = loaded.post("/api/v1/reports", json={"template_id": template["id"], "format": "html"})
        assert response.status_code == 201, response.text
        job_id = response.json()["id"]
        job = loaded.get(f"/api/v1/reports/{job_id}").json()
        assert job["status"] == "done", job
        html = loaded.get(f"/api/v1/reports/{job_id}/download").text
        assert template["name"].replace("&", "&amp;") in html
        assert "{{ report." not in html
        for section in template["config"]["custom_sections"]:
            assert section["title"] in html
        if template["name"] in expected:
            assert expected[template["name"]], template["name"]
            with SessionLocal() as db:
                saved = db.get(ReportJob, job_id)
                ctx = build_context(db, saved, saved.created_by)
                ids = {f.id for group in ctx["groups"] for f in group["instances"]}
                assert ids == expected[template["name"]], template["name"]
        if template["name"] in ("Accepted Risk Review Register", "Reopened Findings Review"):
            assert "This report covers" not in html
            assert '<div class="kpis">' not in html


def test_new_presets_render_empty_scopes(admin_client: ApiClient) -> None:
    for template in admin_client.get("/api/v1/report-templates").json():
        response = admin_client.post(
            "/api/v1/report-preview",
            json={"name": template["name"], "kind": template["kind"], "config": template["config"]},
        )
        assert response.status_code == 200, response.text
        assert "{{ report." not in response.text
        if "details" in template["config"]["sections"]:
            assert "No findings match this report's scope." in response.text
