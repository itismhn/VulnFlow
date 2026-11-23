import io

import pytest
from PIL import Image

from app.core.db import SessionLocal
from app.models import Network, ReportJob, User
from app.models.enums import Role
from app.services.reporting.engine import render_report
from tests import test_api_flow
from tests.conftest import ApiClient, login, make_user

loaded = test_api_flow.loaded


def image_upload(client: ApiClient) -> str:
    data = io.BytesIO()
    Image.new("RGB", (200, 300), "#123456").save(data, "PNG")
    r = client.post("/api/v1/report-assets", files={"file": ("cover.png", data.getvalue(), "image/png")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def create_template(client: ApiClient, config: dict) -> int:
    r = client.post(
        "/api/v1/report-templates", json={"name": "Custom assessment", "kind": "technical", "config": config}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_designed_pages_order_text_and_portable_images(admin_client: ApiClient) -> None:
    asset = image_upload(admin_client)
    config = {
        "branding": {"company_name": 'Bank <&> "Company"', "logo_asset": asset},
        "opening_pages": [
            {
                "id": "cover",
                "background_asset": asset,
                "blocks": [
                    {"id": "title", "text": "{{ report.title }}\n{{ company.name }}", "x": 10, "y": 20},
                ],
            },
            {"id": "second", "blocks": [{"id": "note", "text": "Scope and methodology"}]},
        ],
        "sections": ["custom_note", "summary", "kpis"],
        "custom_sections": [
            {
                "id": "custom_note",
                "title": "Our approach",
                "text": "Prepared for {{ company.name }}",
                "page_break": True,
            }
        ],
        "summary_text": "An independently written summary.",
        "section_titles": {"summary": "Assessment overview"},
    }
    tid = create_template(admin_client, config)
    r = admin_client.post(
        "/api/v1/reports", json={"template_id": tid, "name": "Monthly review", "format": "html"}
    )
    assert r.status_code == 201, r.text
    job = admin_client.get(f"/api/v1/reports/{r.json()['id']}").json()
    assert job["status"] == "done", job
    html = admin_client.get(f"/api/v1/reports/{job['id']}/download").text
    assert "data:image/png;base64," in html
    assert (
        html.index("Scope and methodology") < html.index("Our approach") < html.index("Assessment overview")
    )
    assert "An independently written summary." in html
    assert "This report covers" not in html
    assert "Bank &lt;&amp;&gt;" in html
    preview = admin_client.post(
        "/api/v1/report-preview", json={"name": "Preview", "kind": "technical", "config": config}
    )
    assert preview.status_code == 200 and "Scope and methodology" in preview.text


def test_queued_report_keeps_settings_after_template_deleted(admin_client: ApiClient, monkeypatch) -> None:
    from app.api.v1 import reports

    monkeypatch.setattr(reports.generate_report_task, "delay", lambda *_: None)
    tid = create_template(admin_client, {"sections": ["summary"], "summary_text": "Original wording"})
    job_id = admin_client.post("/api/v1/reports", json={"template_id": tid, "format": "html"}).json()["id"]
    admin_client.patch(
        f"/api/v1/report-templates/{tid}",
        json={"config": {"sections": ["summary"], "summary_text": "Changed wording"}},
    )
    admin_client.delete(f"/api/v1/report-templates/{tid}")
    with SessionLocal() as db:
        result = render_report(db, db.get(ReportJob, job_id)).read_text()
    assert "Original wording" in result and "Changed wording" not in result


def test_missing_assets_and_bad_sections_rejected(admin_client: ApiClient) -> None:
    for config in (
        {"branding": {"logo_asset": "a" * 64 + ".png"}},
        {"sections": ["unknown"]},
        {"opening_pages": [{"id": "p", "background_asset": "../../etc/passwd"}]},
    ):
        r = admin_client.post(
            "/api/v1/report-templates", json={"name": "Invalid", "kind": "technical", "config": config}
        )
        assert r.status_code == 422, r.text
    assert (
        admin_client.post("/api/v1/report-assets", files={"file": ("bad.png", b"not an image")}).status_code
        == 422
    )


def test_report_overrides_do_not_change_saved_template(admin_client: ApiClient) -> None:
    tid = create_template(admin_client, {"sections": ["summary"], "summary_text": "Template summary"})
    job = admin_client.post(
        "/api/v1/reports",
        json={
            "template_id": tid,
            "format": "html",
            "config": {"sections": ["summary"], "summary_text": "Only this report"},
        },
    ).json()
    html = admin_client.get(f"/api/v1/reports/{job['id']}/download").text
    assert "Only this report" in html
    assert (
        next(t for t in admin_client.get("/api/v1/report-templates").json() if t["id"] == tid)["config"][
            "summary_text"
        ]
        == "Template summary"
    )


def test_explicit_empty_scope_clears_template_defaults(loaded: ApiClient) -> None:
    tid = create_template(loaded, {"sections": ["summary"], "filters": {"ip": "10.10.0.0/24"}})
    requested = loaded.post(
        "/api/v1/reports", json={"template_id": tid, "format": "html", "filters": {}}
    ).json()
    html = loaded.get(f"/api/v1/reports/{requested['id']}/download").text
    assert "IP / range: 10.10.0.0/24" not in html
    assert "All active findings" in html
    assert requested["filters"].get("ip") is None


def test_opening_pages_only_and_landscape_pdf(admin_client: ApiClient) -> None:
    try:
        from weasyprint import HTML  # noqa: F401
    except OSError:
        pytest.skip("Pango unavailable")
    response = admin_client.post(
        "/api/v1/report-preview?format=pdf",
        json={
            "name": "Opening pages",
            "kind": "technical",
            "config": {
                "sections": [],
                "opening_pages": [{"id": "one", "blocks": [{"id": "title", "text": "Only an opening page"}]}],
                "layout": {"orientation": "landscape"},
            },
        },
    )
    assert response.status_code == 200 and response.content.startswith(b"%PDF"), response.text[:200]


def test_report_top_list_size_can_exceed_dashboard_default(loaded: ApiClient) -> None:
    from lxml import html

    response = loaded.post(
        "/api/v1/report-preview",
        json={
            "name": "Asset ranking",
            "kind": "technical",
            "config": {"sections": ["top_hosts"], "top_n": 12},
        },
    )
    assert response.status_code == 200, response.text
    tree = html.fromstring(response.text)
    assert len(tree.xpath("//table/tbody/tr")) == 12


def test_report_designer_has_no_document_import_or_export(admin_client: ApiClient) -> None:
    assert admin_client.get("/api/v1/report-word-example").status_code == 404
    assert admin_client.get("/api/v1/report-capabilities").status_code == 404
    assert (
        admin_client.post(
            "/api/v1/report-assets", files={"file": ("template.docx", b"PK-not-an-image")}
        ).status_code
        == 422
    )
    tid = create_template(admin_client, {"sections": ["summary"]})
    assert (
        admin_client.post("/api/v1/reports", json={"template_id": tid, "format": "docx"}).status_code == 422
    )
    assert (
        admin_client.post(
            "/api/v1/report-preview?format=docx",
            json={"name": "Preview", "kind": "technical", "config": {"sections": ["summary"]}},
        ).status_code
        == 422
    )


def test_scoped_designer_preview_includes_logo_and_only_visible_hosts(loaded: ApiClient) -> None:
    logo = image_upload(loaded)
    network = next(n for n in loaded.get("/api/v1/networks").json() if n["name"] == "Branch Network")
    scoped = make_user("branch_reporter", Role.VIEWER, scope_restricted=True)
    with SessionLocal() as db:
        db.get(User, scoped.id).networks = [db.get(Network, network["id"])]
        db.commit()
    loaded.cookies.clear()
    login(loaded, "branch_reporter")
    response = loaded.post(
        "/api/v1/report-preview",
        json={
            "name": "Branch assessment",
            "kind": "technical",
            "config": {"sections": ["details"], "group_by": "host", "branding": {"logo_asset": logo}},
        },
    )
    assert response.status_code == 200, response.text
    assert "data:image/png;base64," in response.text
    assert "10.40." in response.text and "10.10." not in response.text and "10.30." not in response.text


def test_existing_exports_remain_downloadable(admin_client: ApiClient, tmp_path) -> None:
    # Keep history usable for files generated before a format was retired.
    path = tmp_path / "previous-report.docx"
    path.write_bytes(b"previously generated export")
    with SessionLocal() as db:
        owner = db.query(User).filter_by(username="admin").one()
        job = ReportJob(
            name="Previous export", format="docx", status="done", file_path=str(path), created_by_id=owner.id
        )
        db.add(job)
        db.commit()
        job_id = job.id
    response = admin_client.get("/api/v1/reports")
    assert response.status_code == 200 and response.json()["items"][0]["format"] == "docx"
    download = admin_client.get(f"/api/v1/reports/{job_id}/download")
    assert download.status_code == 200 and download.content == path.read_bytes()


@pytest.mark.parametrize("group_by", ["host", "plugin"])
def test_empty_details_explain_no_matches(admin_client: ApiClient, group_by: str) -> None:
    response = admin_client.post(
        "/api/v1/report-preview",
        json={
            "name": "Empty",
            "kind": "technical",
            "config": {"sections": ["details"], "group_by": group_by},
        },
    )
    assert response.status_code == 200
    assert "No findings match this report's scope." in response.text


def test_full_length_report_title_and_detailed_scope(admin_client: ApiClient) -> None:
    title = "Assessment " + "a" * 200
    response = admin_client.post(
        "/api/v1/report-preview",
        json={
            "name": title,
            "kind": "technical",
            "config": {
                "sections": ["summary"],
                "filters": {"port": 443, "exploitable": False, "min_cvss": 7, "plugin_id": [123]},
            },
        },
    )
    assert response.status_code == 200, response.text
    for text in (title, "Port: 443", "No known public exploit", "Minimum CVSS: 7", "Plugin IDs: 123"):
        assert text in response.text
    assert "All active findings" not in response.text


@pytest.mark.parametrize(
    "config",
    [
        {"filters": {"severity": [5]}},
        {"filters": {"severity": [-1]}},
        {"opening_pages": [{"id": "same"}, {"id": "same"}]},
        {"opening_pages": [{"id": "page", "blocks": [{"id": "same"}, {"id": "same"}]}]},
        {"page_breaks": ["unknown"]},
    ],
)
def test_invalid_designer_settings_return_validation_errors(admin_client: ApiClient, config: dict) -> None:
    r = admin_client.post(
        "/api/v1/report-preview", json={"name": "Invalid", "kind": "technical", "config": config}
    )
    assert r.status_code == 422, r.text


def test_chart_layout_fits_narrow_page_and_section_breaks(admin_client: ApiClient) -> None:
    from weasyprint import HTML

    r = admin_client.post(
        "/api/v1/report-preview",
        json={
            "name": "Narrow page",
            "kind": "executive",
            "config": {
                "sections": ["charts", "recommendations"],
                "page_breaks": ["recommendations"],
                "layout": {"show_cover": False, "margin_mm": 35},
            },
        },
    )
    assert r.status_code == 200, r.text
    doc = HTML(string=r.text).render()
    assert len(doc.pages) >= 2
    charts = []
    for page in doc.pages:
        for box in page._page_box.descendants():
            if str(box.element_tag).endswith("svg"):
                charts.append(box)
                assert box.position_x >= 35 * 96 / 25.4 - 1
                assert box.position_x + box.width <= page.width - 35 * 96 / 25.4 + 1
    assert len(charts) >= 3
    headings = [
        " ".join(box.text for box in page._page_box.descendants() if hasattr(box, "text"))
        for page in doc.pages
    ]
    assert "Recommendations" not in headings[0]
    assert "Recommendations" in headings[1]


def test_host_details_disclose_instance_limit(loaded: ApiClient, monkeypatch) -> None:
    from app.services.reporting import engine

    monkeypatch.setattr(engine, "MAX_INSTANCES_PER_GROUP", 1)
    r = loaded.post(
        "/api/v1/report-preview",
        json={
            "name": "Limited details",
            "kind": "technical",
            "config": {"sections": ["details"], "group_by": "host"},
        },
    )
    assert r.status_code == 200
    assert "more. Use XLSX/CSV for the full data set." in r.text


def test_scoped_exports_and_history_are_isolated(loaded: ApiClient) -> None:
    import csv

    from openpyxl import load_workbook

    tid = create_template(loaded, {"sections": ["details"], "group_by": "host"})
    private = loaded.post("/api/v1/reports", json={"template_id": tid, "format": "html"}).json()
    network = next(n for n in loaded.get("/api/v1/networks").json() if n["name"] == "Branch Network")
    user = make_user("isolated_reporter", Role.VIEWER, scope_restricted=True)
    with SessionLocal() as db:
        db.get(User, user.id).networks = [db.get(Network, network["id"])]
        db.commit()
    loaded.cookies.clear()
    login(loaded, "isolated_reporter")
    assert loaded.get(f"/api/v1/reports/{private['id']}/download").status_code == 404
    assert loaded.delete(f"/api/v1/reports/{private['id']}").status_code == 404
    assert (
        loaded.post("/api/v1/report-templates", json={"name": "Forbidden", "kind": "technical"}).status_code
        == 403
    )
    assert loaded.post("/api/v1/report-assets", files={"file": ("bad.png", b"x")}).status_code == 403
    for fmt in ("html", "pdf", "csv", "xlsx"):
        r = loaded.post("/api/v1/reports", json={"template_id": tid, "format": fmt})
        assert r.status_code == 201, r.text
        job = loaded.get(f"/api/v1/reports/{r.json()['id']}").json()
        assert job["status"] == "done", job
        download = loaded.get(f"/api/v1/reports/{job['id']}/download")
        assert download.status_code == 200
        if fmt == "html":
            assert "10.40." in download.text and "10.10." not in download.text
        elif fmt == "pdf":
            assert download.content.startswith(b"%PDF")
        else:
            rows = (
                list(csv.reader(io.StringIO(download.content.decode("utf-8-sig"))))
                if fmt == "csv"
                else list(load_workbook(io.BytesIO(download.content))["Findings"].values)
            )
            assert len(rows) > 1
            assert all(str(row[0]).startswith("10.40.") for row in rows[1:])
    assert loaded.get("/api/v1/reports").json()["total"] == 4


@pytest.mark.parametrize(
    "size,orientation,width_mm,height_mm",
    [
        ("A4", "portrait", 210, 297),
        ("A4", "landscape", 297, 210),
        ("Letter", "portrait", 215.9, 279.4),
        ("Letter", "landscape", 279.4, 215.9),
    ],
)
def test_pdf_paper_dimensions_and_cover_visibility(
    admin_client: ApiClient, size, orientation, width_mm, height_mm
) -> None:
    from weasyprint import HTML

    r = admin_client.post(
        "/api/v1/report-preview",
        json={
            "name": "Paper test",
            "kind": "technical",
            "config": {
                "sections": ["summary"],
                "summary_text": "Body proof",
                "opening_pages": [{"id": "cover", "blocks": [{"id": "text", "text": "Hidden cover"}]}],
                "layout": {
                    "show_cover": False,
                    "page_size": size,
                    "orientation": orientation,
                    "page_numbers": False,
                },
            },
        },
    )
    assert r.status_code == 200
    assert "Hidden cover" not in r.text
    doc = HTML(string=r.text).render()
    assert len(doc.pages) == 1
    assert doc.pages[0].width == pytest.approx(width_mm * 96 / 25.4)
    assert doc.pages[0].height == pytest.approx(height_mm * 96 / 25.4)


def test_template_lifecycle_and_image_roundtrip(admin_client: ApiClient) -> None:
    image = image_upload(admin_client)
    assert admin_client.get(f"/api/v1/report-assets/{image}").content.startswith(b"\x89PNG")
    config = {"sections": ["summary"], "branding": {"logo_asset": image}}
    tid = create_template(admin_client, config)
    assert (
        admin_client.post(
            "/api/v1/report-templates", json={"name": "Custom assessment", "kind": "technical"}
        ).status_code
        == 409
    )
    config.update({"summary_text": "Updated content", "page_breaks": ["summary"]})
    update = admin_client.patch(
        f"/api/v1/report-templates/{tid}", json={"name": "Updated assessment", "config": config}
    )
    assert update.status_code == 200
    assert update.json()["config"]["page_breaks"] == ["summary"]
    job = admin_client.post("/api/v1/reports", json={"template_id": tid, "format": "html"}).json()
    assert job["status"] == "done"
    assert "Updated content" in admin_client.get(f"/api/v1/reports/{job['id']}/download").text
    assert admin_client.delete(f"/api/v1/report-templates/{tid}").status_code == 204
    assert admin_client.get(f"/api/v1/reports/{job['id']}/download").status_code == 200
    assert admin_client.delete(f"/api/v1/reports/{job['id']}").status_code == 204
    assert admin_client.get(f"/api/v1/reports/{job['id']}/download").status_code == 404
