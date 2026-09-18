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
    assert [group["title"] for group in data["workbench_metrics"]] == [
        "简历初筛", "简历推荐", "面试", "录用",
    ]
    screening = data["workbench_metrics"][0]
    assert {item["key"] for item in screening["items"]} == {
        "unprocessed", "referral", "recommended", "unassigned",
    }
    routes = {
        item["key"]: item["route"]
        for group in data["workbench_metrics"]
        for item in group["items"]
    }
    assert routes == {
        "unprocessed": "/candidates?unprocessed=1",
        "referral": "/candidates?source=referral",
        "recommended": "/candidates?source_group=talent_recommendation",
        "unassigned": "/candidates?unassigned=1",
        "pending_feedback": "/candidates?recommendation_status=pending",
        "passed": "/candidates?recommendation_status=passed",
        "failed": "/candidates?recommendation_status=failed",
        "waiting_schedule": "/candidates?action_state=awaiting_interview_schedule",
        "feedback": "/interviews?action_state=awaiting_interviewer_feedback",
        "hr_review": "/interviews?action_state=awaiting_hr_review",
        "pending_onboard": "/onboarding?application_stage=pending_onboard",
        "pending_approval": "/approvals?status=pending",
        "pending_send": "/offers?status=pending_send&ready_to_send=1",
    }
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


def test_job_progress_report_groups_jobs_and_stage_metrics(client):
    job, _, application = _seed_job_and_application(client, source="manual")
    now = datetime.now()
    with client.application.app_context():
        col("stage_transitions").insert_one({
            "application_id": application["id"],
            "from_stage": "pending_screen",
            "to_stage": "hr_screen_passed",
            "created_at": dt(now),
        })

    response = client.get("/api/reports/job-progress", query_string={"job_id": job["id"]})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 0
    data = payload["data"]
    assert data["summary"]["received"] == 1
    assert data["summary"]["recommended"] == 1
    assert len(data["rows"]) == 1
    assert data["rows"][0]["job_id"] == job["id"]
    assert {
        "job_resumes", "department_onboarded", "hr_recommended",
        "hr_offers", "job_completion", "job_onboarded",
        "job_onboarding_cycle", "delivery_onboarded", "resume_sources",
    }.issubset(data["rankings"])


def test_channel_effect_report_groups_sources(client):
    _seed_job_and_application(client, source="referral")
    _seed_job_and_application(client, source="manual")

    response = client.get("/api/reports/channel-effect")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 0
    data = payload["data"]
    assert data["summary"]["active_channels"] >= 2
    assert data["summary"]["applications"] >= 2
    assert {"referral", "manual"}.issubset({row["source"] for row in data["rows"]})
    assert "attrition" in data


def test_stage_funnel_report_returns_three_chart_groups(client):
    job, _, application = _seed_job_and_application(client, source="manual")
    now = datetime.now()
    with client.application.app_context():
        col("stage_transitions").insert_one({
            "application_id": application["id"],
            "from_stage": "new_resume",
            "to_stage": "pending_screen",
            "created_at": dt(now),
        })

    response = client.get("/api/reports/stage-funnel", query_string={"job_id": job["id"]})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 0
    data = payload["data"]
    assert data["total"] == 1
    assert data["stage_funnel"][0]["stage_key"] == "new_resume"
    assert data["stage_funnel"][0]["count"] == 1
    assert data["stage_funnel"][1]["count"] == 1
    assert isinstance(data["interview_funnel"], list)
    assert isinstance(data["current_stages"], list)


def test_interviewer_efficiency_report_aggregates_feedback(client):
    job, candidate, application = _seed_job_and_application(client, source="manual")
    now = datetime.now()
    with client.application.app_context():
        col("interviews").insert_one({
            "_id": 92001,
            "candidate_id": candidate,
            "job_id": job["id"],
            "application_id": application["id"],
            "round": "一面",
            "interviewer_name": "效率测试面试官",
            "status": "completed",
            "created_at": dt(now - timedelta(hours=4)),
            "updated_at": dt(now - timedelta(hours=1)),
        })
        col("interview_feedback").insert_one({
            "_id": 92001,
            "interview_id": 92001,
            "conclusion": "pass",
            "evaluator_name": "效率测试面试官",
            "skip_eval": False,
            "created_at": dt(now - timedelta(hours=1)),
            "updated_at": dt(now - timedelta(hours=1)),
        })

    response = client.get("/api/reports/interviewer-efficiency", query_string={
        "job_id": job["id"], "interviewer_name": "效率测试面试官",
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 0
    data = payload["data"]
    assert data["summary"]["recommended"] == 1
    assert data["summary"]["feedback"] == 1
    assert data["summary"]["attended"] == 1
    assert data["rows"][0]["pass_rate"] == 100
    assert data["rows"][0]["feedback_hours"] == 3


def test_talent_profile_report_aggregates_candidate_attributes(client):
    job, candidate, _ = _seed_job_and_application(client, source="referral")
    with client.application.app_context():
        col("candidates").update_one({"_id": candidate}, {"$set": {
            "gender": "女",
            "age": 29,
            "education": [
                {"school": "画像测试学院", "degree": "本科", "major": "工商管理"},
                {"school": "画像测试大学", "degree": "硕士研究生", "major": "软件工程"},
            ],
            # Deliberately newest-first: the report must use dates, not list position.
            "work_experience": [
                {"company": "最新受聘公司", "start": "2024-02", "end": "至今"},
                {"company": "上一家公司", "start": "2022-01", "end": "2024-01"},
            ],
        }})

    response = client.get("/api/reports/talent-profile", query_string={"job_id": job["id"]})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 0
    data = payload["data"]
    assert data["total"] == 1
    assert {item["name"] for item in data["gender"] if item["value"]} == {"女"}
    assert {item["name"] for item in data["highest_education"] if item["value"]} == {"硕士"}
    assert data["graduation_school"][0] == {"name": "画像测试大学", "value": 1}
    assert data["latest_employer"][0] == {"name": "最新受聘公司", "value": 1}
    assert data["profession"][0]["name"] == "软件工程"


def test_talent_profile_includes_unassigned_candidates_without_job_filter(client):
    ensure_hr(client)
    candidate = make_candidate(
        client,
        name="待分配画像候选人",
        phone="13987654321",
        email="unassigned-profile@example.com",
    )
    with client.application.app_context():
        col("candidates").update_one({"_id": candidate}, {"$set": {
            "age": 23,
            "highest_education": "大专",
            "major": "工程造价",
            "education": [{
                "school": "海南职业技术学院",
                "degree": "大专",
                "major": "工程造价",
                "graduate_at": "2024",
            }],
        }})

    data = client.get("/api/reports/talent-profile").get_json()["data"]
    assert any(item == {"name": "大专", "value": 1} for item in data["highest_education"])
    assert any(item == {"name": "工程造价", "value": 1} for item in data["profession"])

    job = make_job(client, name="画像职位过滤测试")
    publish_job(client, job["id"])
    filtered = client.get(
        "/api/reports/talent-profile", query_string={"job_id": job["id"]},
    ).get_json()["data"]
    assert not any(item.get("name") == "工程造价" for item in filtered["profession"])
