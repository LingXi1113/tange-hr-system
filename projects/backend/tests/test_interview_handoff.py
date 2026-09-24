from datetime import datetime, timedelta

from conftest import login
from helpers import assign, make_candidate, make_job, publish_job


def test_interviewer_or_hr_feedback_keeps_stage_and_pass_allows_manual_advance(client):
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
        "conclusion": "hold",
        "comment": "先由面试官评价为待定",
        "dimension_scores": [{"name": "专业能力", "score": 4}],
    }).get_json()
    assert feedback["code"] == 0
    completed = client.post(f"/api/interviews/{interview['id']}/complete", json={
        "version": interview["version"],
    }).get_json()
    assert completed["code"] == 0
    assert completed["data"]["handed_to_hr"] is False

    login(client, "hr-001")
    detail = client.get(f"/api/candidates/{candidate_id}").get_json()["data"]
    current_application = detail["applications"][0]
    assert current_application["current_stage"] == "pending_interview"
    assert current_application["awaiting_hr_action"] is False
    assert current_application["owner_id"] == "hr-001"
    assert current_application["process_state_key"] == "interview_evaluated"
    assert current_application["process_state_label"] == "面试已评价"

    # 待定/不通过评价不能推进后续阶段。
    blocked = client.post(f"/api/applications/{application['id']}/move", json={
        "to_stage": "interview_passed",
        "reason": "尝试推进",
        "version": current_application["version"],
    }).get_json()
    assert blocked["code"] == 1003
    assert "通过评价" in blocked["msg"]

    # 招聘 HR 可以直接代评/修改评价；通过后仍保留原招聘阶段。
    hr_feedback = client.post(f"/api/interviews/{interview['id']}/feedback", json={
        "version": feedback["data"]["version"],
        "conclusion": "pass",
        "comment": "HR复核通过",
        "dimension_scores": [{"name": "综合能力", "score": 5}],
    }).get_json()
    assert hr_feedback["code"] == 0
    assert hr_feedback["data"]["evaluator_id"] == "hr-001"
    assert hr_feedback["data"]["conclusion"] == "pass"
    completed_again = client.post(f"/api/interviews/{interview['id']}/complete", json={
        "version": completed["data"]["version"],
    }).get_json()
    assert completed_again["code"] == 0

    detail = client.get(f"/api/candidates/{candidate_id}").get_json()["data"]
    current_application = detail["applications"][0]
    assert current_application["current_stage"] == "pending_interview"
    assert current_application["last_interview_conclusion"] == "pass"
    assert current_application["process_state_key"] == "interview_evaluated"

    dashboard = client.get("/api/dashboard/summary").get_json()["data"]
    interview_metrics = next(item for item in dashboard["workbench_metrics"] if item["key"] == "interview")
    assert all(item["key"] != "hr_review" for item in interview_metrics["items"])

    # 通过评价不会自动流转，HR 手动选择后续阶段才真正推进。
    advanced = client.post(f"/api/applications/{application['id']}/move", json={
        "to_stage": "interview_passed",
        "reason": "HR确认评价通过后手动推进",
        "version": current_application["version"],
    }).get_json()
    assert advanced["code"] == 0
    assert advanced["data"]["current_stage"] == "interview_passed"
    assert advanced["data"]["awaiting_hr_action"] is False


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
