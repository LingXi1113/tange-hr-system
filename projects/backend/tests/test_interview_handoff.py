from datetime import datetime, timedelta

from conftest import login
from helpers import assign, make_candidate, make_job, publish_job


def test_interviewer_feedback_hands_back_to_hr_before_stage_advances(client):
    login(client, "super-admin-001")
    template_id = client.post("/api/pipeline-templates", json={
        "name": "面试交接测试流程",
        "stages": [
            {"stage_key": "new_resume", "name": "新简历", "sort_order": 1},
            {"stage_key": "pending_interview", "name": "待面试", "sort_order": 2},
            {"stage_key": "interviewing", "name": "面试中", "sort_order": 3},
            {"stage_key": "interview_passed", "name": "面试通过", "sort_order": 4},
        ],
    }).get_json()["data"]["id"]

    login(client, "hr-001")
    job = make_job(client, name="面试交接测试职位", template_id=template_id)
    publish_job(client, job["id"])
    candidate_id = make_candidate(client, phone="13988001122", email="handoff@example.com")
    application = assign(client, candidate_id, job["id"])
    application = client.post(f"/api/applications/{application['id']}/move", json={
        "to_stage": "pending_interview",
        "reason": "进入一面",
        "version": application["version"],
    }).get_json()["data"]

    start = datetime.now() + timedelta(days=1)
    end = start + timedelta(hours=1)
    interview = client.post("/api/interviews", json={
        "application_id": application["id"],
        "round": "一面",
        "type": "video",
        "start_at": start.strftime("%Y-%m-%d %H:%M"),
        "end_at": end.strftime("%Y-%m-%d %H:%M"),
        "interviewer_id": "interviewer-001",
    }).get_json()["data"]
    interview = client.post(f"/api/interviews/{interview['id']}/status", json={
        "action": "invite", "version": interview["version"],
    }).get_json()["data"]
    interview = client.post(f"/api/interviews/{interview['id']}/status", json={
        "action": "confirm", "version": interview["version"],
    }).get_json()["data"]

    login(client, "interviewer-001")
    no_feedback = client.post(f"/api/interviews/{interview['id']}/complete", json={
        "version": interview["version"],
    }).get_json()
    assert no_feedback["code"] == 1001

    feedback = client.post(f"/api/interviews/{interview['id']}/feedback", json={
        "conclusion": "pass",
        "comment": "建议进入下一阶段",
        "dimension_scores": [{"name": "专业能力", "score": 4}],
    }).get_json()
    assert feedback["code"] == 0
    completed = client.post(f"/api/interviews/{interview['id']}/complete", json={
        "version": interview["version"],
    }).get_json()
    assert completed["code"] == 0
    assert completed["data"]["handed_to_hr"] is True

    interviewer_cannot_advance = client.post(
        f"/api/interviews/{interview['id']}/apply-conclusion",
        json={"version": application["version"]},
    ).get_json()
    assert interviewer_cannot_advance["code"] == 1006

    login(client, "hr-001")
    detail = client.get(f"/api/candidates/{candidate_id}").get_json()["data"]
    current_application = detail["applications"][0]
    assert current_application["current_stage"] == "pending_interview"
    assert current_application["awaiting_hr_action"] is True
    assert current_application["owner_id"] == "hr-001"
    assert current_application["process_state_key"] == "awaiting_hr_review"
    assert current_application["process_state_label"] == "待 HR 确认"

    # 交回 HR 只是阶段内状态，候选人仍留在真实面试阶段中。
    interview_stage = client.get("/api/candidates", query_string={
        "stage": "interview_1",
    }).get_json()["data"]
    candidate_row = next(item for item in interview_stage["list"] if item["id"] == candidate_id)
    assert candidate_row["latest_application"]["process_state_key"] == "awaiting_hr_review"

    board = client.get("/api/pipeline/board", query_string={"job_id": job["id"]}).get_json()["data"]
    board_card = next(item for item in board["cards"] if item["id"] == application["id"])
    assert board_card["current_stage"] == "pending_interview"
    assert board_card["process_state_label"] == "待 HR 确认"

    hr_interviews = client.get("/api/interviews", query_string={
        "action_state": "awaiting_hr_review",
    }).get_json()["data"]
    assert any(item["id"] == interview["id"] for item in hr_interviews["list"])

    dashboard = client.get("/api/dashboard/summary").get_json()["data"]
    assert dashboard["todos"]["hr_review_pending"] == 1
    interview_metrics = next(item for item in dashboard["workbench_metrics"] if item["key"] == "interview")
    assert next(item for item in interview_metrics["items"] if item["key"] == "hr_review")["count"] == 1

    advanced = client.post(f"/api/interviews/{interview['id']}/apply-conclusion", json={
        "version": current_application["version"],
    }).get_json()
    assert advanced["code"] == 0
    assert advanced["data"]["application"]["current_stage"] == "interview_passed"
    assert advanced["data"]["application"]["awaiting_hr_action"] is False


def test_stage_alias_and_keyword_search_find_candidate(client):
    login(client, "hr-001")
    job = make_job(client, name="阶段分类测试职位")
    publish_job(client, job["id"])
    candidate_id = make_candidate(
        client, name="阶段检索候选人", phone="13988003344", email="stage-search@example.com",
    )
    application = assign(client, candidate_id, job["id"])

    from common.db import col
    with client.application.app_context():
        col("applications").update_one({"_id": application["id"]}, {"$set": {
            "current_stage": "interviewing",
            "interview_round": "一面",
        }})

    first_round = client.get("/api/candidates", query_string={"stage": "interview_1"}).get_json()["data"]
    assert any(item["id"] == candidate_id for item in first_round["list"])
    global_search = client.get("/api/candidates", query_string={
        "keyword": "阶段检索候选人",
    }).get_json()["data"]
    assert global_search["total"] == 1
