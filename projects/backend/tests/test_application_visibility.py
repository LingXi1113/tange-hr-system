"""Cross-module visibility and application-granular delivery analysis."""
from datetime import datetime, timedelta

from conftest import login
from helpers import assign, make_candidate, make_job, make_template, publish_job
from common.db import col, insert_doc


def setup_application(client, suffix="1"):
    template = make_template(client)
    job = make_job(client, name=f"Visibility job {suffix}", template_id=template)
    publish_job(client, job["id"])
    candidate = make_candidate(client, name=f"Visibility person {suffix}",
                               phone=f"1397700000{suffix}", email=f"visibility{suffix}@example.com")
    application = assign(client, candidate, job["id"])
    return job, candidate, application


def enter_interview(client, application):
    body = client.post(f"/api/applications/{application['id']}/direct-interview",
                       json={"version": application["version"]}).get_json()
    assert body["code"] == 0, body
    return body["data"]


def schedule(client, application):
    start = datetime.now() + timedelta(days=2)
    body = client.post("/api/interviews", json={
        "application_id": application["id"], "round": "一面", "type": "video",
        "start_at": start.strftime("%Y-%m-%d %H:%M"),
        "interviewer_id": "interviewer-001",
    }).get_json()
    assert body["code"] == 0, body
    return body["data"]


def test_entering_first_interview_visible_before_scheduling(client):
    job, candidate, application = setup_application(client)
    application = enter_interview(client, application)
    board = client.get("/api/pipeline/board").get_json()
    assert board["code"] == 0
    assert application["id"] in [row["id"] for row in board["data"]["cards"]]
    pending = client.get("/api/interviews/pending-applications").get_json()["data"]
    assert pending["total"] == 1
    assert pending["list"][0]["candidate_id"] == candidate
    assert pending["list"][0]["job_id"] == job["id"]
    assert pending["list"][0]["interview_round"] == "一面"
    assert client.get("/api/interviews").get_json()["data"]["total"] == 0


def test_scheduling_moves_from_pending_to_actual_interviews(client):
    _, _, application = setup_application(client)
    application = enter_interview(client, application)
    interview = schedule(client, application)
    assert client.get("/api/interviews/pending-applications").get_json()["data"]["total"] == 0
    assert client.get("/api/interviews").get_json()["data"]["list"][0]["id"] == interview["id"]
    assert len(client.get("/api/pipeline/board").get_json()["data"]["cards"]) == 1


def test_cancelled_interview_returns_to_pending_list(client):
    _, _, application = setup_application(client)
    application = enter_interview(client, application)
    interview = schedule(client, application)
    response = client.post(f"/api/interviews/{interview['id']}/status", json={
        "action": "cancel", "version": interview["version"],
    }).get_json()
    assert response["code"] == 0, response
    assert client.get("/api/interviews/pending-applications").get_json()["data"]["total"] == 1


def test_all_jobs_board_and_pending_filters(client):
    job1, _, app1 = setup_application(client, "1")
    job2, _, app2 = setup_application(client, "2")
    enter_interview(client, app1)
    enter_interview(client, app2)
    board = client.get("/api/pipeline/board").get_json()["data"]
    assert {app1["id"], app2["id"]} == {row["id"] for row in board["cards"]}
    assert len({row["stage_key"] for row in board["columns"]}) == len(board["columns"])
    for job, application in ((job1, app1), (job2, app2)):
        pending = client.get("/api/interviews/pending-applications", query_string={"job_id": job["id"]}).get_json()["data"]
        assert [row["id"] for row in pending["list"]] == [application["id"]]
    assert client.get("/api/interviews/pending-applications", query_string={"round": "二面"}).get_json()["data"]["total"] == 0


def test_board_keeps_legacy_stage_without_matching_template_column(client):
    job, _, application = setup_application(client)
    with client.application.app_context():
        col("applications").update_one({"_id": application["id"]}, {"$set": {"current_stage": "interview_2"}})
    board = client.get("/api/pipeline/board", query_string={"job_id": job["id"]}).get_json()["data"]
    assert "interview_2" in [row["stage_key"] for row in board["columns"]]
    assert board["cards"][0]["current_stage"] == "interview_2"


def test_delivery_analysis_separates_applications_and_keeps_archived_history(client):
    job, candidate, application = setup_application(client)
    application = enter_interview(client, application)
    schedule(client, application)
    with client.application.app_context():
        col("applications").update_one({"_id": application["id"]}, {"$set": {
            "current_stage": "eliminated", "status": "eliminated",
        }})
        insert_doc("stage_transitions", {"application_id": application["id"],
                   "from_stage": "interview_1", "to_stage": "eliminated", "reason": "Test archive"})
        another = insert_doc("applications", {"candidate_id": candidate, "job_id": job["id"],
                             "current_stage": "new_resume", "status": "in_progress", "source": "manual"})
        # Collection counters overlap. A different interview with the same numeric ID
        # as this candidate/application must not leak its log into this person's history.
        insert_doc("operation_logs", {"biz_type": "interview", "biz_id": str(another["_id"]),
                                     "action": "unrelated_person", "detail": "Must not leak"})
    body = client.get(f"/api/candidates/{candidate}/delivery-analysis").get_json()
    assert body["code"] == 0, body
    data = body["data"]
    assert data["summary"]["total_deliveries"] == 2
    old = next(row for row in data["applications"] if row["id"] == application["id"])
    new = next(row for row in data["applications"] if row["id"] == another["_id"])
    assert old["highest_stage_name"] == "一面"
    assert old["status"] == "eliminated" and new["status"] == "in_progress"
    assert old["interviews"] and not new["interviews"]
    assert any(item["title"] == "进入淘汰" for item in old["timeline"])
    assert not any(item["title"] == "unrelated_person" for item in data["activities"])


def test_pending_list_not_available_to_non_hr(client):
    login(client, "interviewer-001")
    assert client.get("/api/interviews/pending-applications").get_json()["code"] == 1006


def test_missing_round_record_overrides_stale_feedback_action(client):
    _, _, application = setup_application(client)
    application = enter_interview(client, application)
    with client.application.app_context():
        col("applications").update_one({"_id": application["id"]}, {"$set": {
            "next_action": "submit_interview_feedback", "interview_round": "二面",
            "current_stage": "interview_2",
        }})
    pending = client.get("/api/interviews/pending-applications").get_json()["data"]
    assert pending["total"] == 1
    assert pending["list"][0]["interview_round"] == "二面"


def test_analysis_has_feedback_and_recommendation_outcomes(client):
    _, candidate, application = setup_application(client)
    application = client.post(f"/api/applications/{application['id']}/assign-business", json={
        "business_screener_id": "screen-001", "version": application["version"],
    }).get_json()["data"]
    application = enter_interview(client, application)
    interview = schedule(client, application)
    with client.application.app_context():
        col("interviews").update_one({"_id": interview["id"]}, {"$set": {"status": "completed"}})
        insert_doc("interview_feedback", {"interview_id": interview["id"], "conclusion": "pass",
                   "evaluator_name": "Test evaluator", "comment": "Test evidence"})
    data = client.get(f"/api/candidates/{candidate}/delivery-analysis").get_json()["data"]
    assert data["summary"]["recommendations"] == 1
    assert data["summary"]["passed_recommendations"] == 1
    assert data["summary"]["passed_interviews"] == 1
    assert data["summary"]["interview_pass_rate"] == 100
    assert any(item["title"] == "提交面试评价" for item in data["applications"][0]["timeline"])
