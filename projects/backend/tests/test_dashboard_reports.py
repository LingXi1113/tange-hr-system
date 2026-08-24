from datetime import datetime, timedelta

from common.db import col, dt

from tests.helpers import assign, ensure_hr, make_candidate, make_job, publish_job


def _seed_job_and_application(client, *, source="manual"):
    ensure_hr(client)
    job = make_job(client, name="Report Test Job")
    publish_job(client, job["id"])
    candidate = make_candidate(
        client,
        name=f"Report Candidate {source}",
        phone=f"1390000{job['id']:04d}",
        email=f"report-{source}-{job['id']}@example.com",
    )
    application = assign(client, candidate, job["id"], source=source)
    return job, candidate, application


def test_dashboard_summary_contains_workbench_counts_and_funnel(client):
    job, candidate, application = _seed_job_and_application(client)

    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 0

    data = payload["data"]
    assert data["overview"]["open_jobs"] >= 1
    assert data["overview"]["candidate_total"] >= 1
    assert data["todos"]["pending_screen"] >= 0
    assert any(item["stage_key"] == "new_resume" and item["count"] >= 1
               for item in data["funnel"])
    assert "recent_activities" in data


def test_reports_funnel_channels_and_csv_export(client):
    job_a, _, app_a = _seed_job_and_application(client, source="referral")
    job_b, _, app_b = _seed_job_and_application(client, source="manual")

    funnel = client.get("/api/reports/funnel")
    assert funnel.status_code == 200
    funnel_data = funnel.get_json()["data"]
    assert funnel_data["total"] >= 2
    assert any(row["stage_key"] == "new_resume" and row["count"] >= 2
               for row in funnel_data["stage_counts"])

    channels = client.get("/api/reports/channels")
    assert channels.status_code == 200
    channel_rows = channels.get_json()["data"]["rows"]
    sources = {row["source"] for row in channel_rows}
    assert {"referral", "manual"}.issubset(sources)

    export = client.get("/api/reports/export?type=channels")
    assert export.status_code == 200
    assert "text/csv" in export.content_type
    assert "attachment" in export.headers["Content-Disposition"]
    with client.application.app_context():
        assert col("export_logs").count_documents({"report_type": "channels"}) == 1


def test_reports_requirements_and_cycle_shape(client):
    job, candidate, application = _seed_job_and_application(client)
    now = datetime.now()
    with client.application.app_context():
        col("requirements").insert_one({
            "_id": 9991,
            "code": "REQ-REPORT-001",
            "name": "Report Requirement",
            "status": "recruiting",
            "headcount": 2,
            "due_date": (now + timedelta(days=10)).strftime("%Y-%m-%d"),
            "dept_name": "Engineering",
            "created_at": dt(now),
            "updated_at": dt(now),
        })
        col("stage_transitions").insert_one({
            "application_id": application["id"],
            "from_stage": "new_resume",
            "to_stage": "pending_screen",
            "created_at": dt(now - timedelta(days=3)),
        })
        col("stage_transitions").insert_one({
            "application_id": application["id"],
            "from_stage": "pending_screen",
            "to_stage": "hr_screen_passed",
            "created_at": dt(now - timedelta(days=1)),
        })

    requirements = client.get("/api/reports/requirements")
    assert requirements.status_code == 200
    requirements_data = requirements.get_json()["data"]
    assert requirements_data["summary"]["recruiting"] >= 1
    assert any(row["code"] == "REQ-REPORT-001" for row in requirements_data["rows"])

    cycle = client.get("/api/reports/cycle")
    assert cycle.status_code == 200
    cycle_data = cycle.get_json()["data"]
    assert cycle_data["sample_count"] >= 1
    assert "avg_recruitment_days" in cycle_data["metrics"]


def test_report_filters_and_audit_log_query(client):
    _seed_job_and_application(client, source="manual")
    filtered = client.get("/api/reports/funnel", query_string={
        "owner_id": "hr-001", "source": "manual",
    }).get_json()
    assert filtered["code"] == 0
    assert filtered["data"]["total"] >= 1
    audit = client.get("/api/audit-logs", query_string={"biz_type": "application"}).get_json()
    assert audit["code"] == 0
    assert audit["data"]["total"] >= 1
