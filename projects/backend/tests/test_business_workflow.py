"""HR 流程安排、业务人员指派与面试评价门禁。"""
from datetime import datetime, timedelta

from conftest import login
from helpers import make_candidate, make_job, publish_job


def _template(client):
    login(client, "super-admin-001")
    response = client.post("/api/pipeline-templates", json={
        "name": "业务协作用例流程",
        "stages": [
            {"stage_key": "new_resume", "name": "新简历", "sort_order": 1},
            {"stage_key": "hr_screen_passed", "name": "HR筛选", "sort_order": 2},
            {"stage_key": "business_screen", "name": "业务复筛", "sort_order": 3},
            {"stage_key": "interview_1", "name": "一面", "sort_order": 4},
            {"stage_key": "interview_2", "name": "二面", "sort_order": 5},
            {"stage_key": "interview_passed", "name": "面试阶段", "sort_order": 6},
        ],
    })
    assert response.get_json()["code"] == 0
    return response.get_json()["data"]["id"]


def _setup(client):
    template_id = _template(client)
    login(client, "hr-001")
    job = make_job(client, name="业务协作职位", template_id=template_id)
    publish_job(client, job["id"])
    candidate_id = make_candidate(client, phone="13700009999", email="workflow-assignment@example.com")
    application = client.post(
        f"/api/candidates/{candidate_id}/applications", json={"job_id": job["id"]},
    ).get_json()["data"]
    return job, application


def _future_slot():
    start = datetime.now() + timedelta(days=1)
    end = start + timedelta(hours=1)
    return start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M")


def test_hr_assigns_business_and_direct_interview(client):
    job, application = _setup(client)
    assigned = client.post(
        f"/api/applications/{application['id']}/assign-business",
        json={"business_screener_id": "screen-001", "version": application["version"]},
    ).get_json()
    assert assigned["code"] == 0
    assert assigned["data"]["current_stage"] == "business_screen"
    assert assigned["data"]["business_screener_id"] == "screen-001"
    assert assigned["data"]["business_screener_name"] == "王强"

    direct = client.post(
        f"/api/applications/{application['id']}/direct-interview",
        json={"version": assigned["data"]["version"]},
    ).get_json()
    assert direct["code"] == 0
    assert direct["data"]["current_stage"] == "interview_1"


def test_only_assigned_business_interviewer_can_feedback_before_next_round(client):
    _job, application = _setup(client)
    direct = client.post(
        f"/api/applications/{application['id']}/direct-interview",
        json={"version": application["version"]},
    ).get_json()["data"]
    start, end = _future_slot()
    interview = client.post("/api/interviews", json={
        "application_id": direct["id"], "round": "一面", "type": "video",
        "start_at": start, "end_at": end, "interviewer_id": "interviewer-001",
    }).get_json()
    assert interview["code"] == 0, interview
    interview_id = interview["data"]["id"]

    client.post(f"/api/interviews/{interview_id}/status", json={"action": "invite"})
    client.post(f"/api/interviews/{interview_id}/status", json={"action": "confirm"})

    login(client, "screen-001")
    forbidden = client.post(f"/api/interviews/{interview_id}/feedback", json={
        "conclusion": "pass", "comment": "非本场面试人员",
    }).get_json()
    assert forbidden["code"] == 1006

    login(client, "interviewer-001")
    feedback = client.post(f"/api/interviews/{interview_id}/feedback", json={
        "conclusion": "pass", "comment": "专业能力和沟通均通过",
    }).get_json()
    assert feedback["code"] == 0
    completed = client.post(f"/api/interviews/{interview_id}/complete", json={}).get_json()
    assert completed["code"] == 0

    login(client, "hr-001")
    applied = client.post(f"/api/interviews/{interview_id}/apply-conclusion", json={
        "version": direct["version"],
    }).get_json()
    assert applied["code"] == 0
    assert applied["data"]["application"]["current_stage"] == "interviewing"
    assert applied["data"]["application"]["interview_round"] == "二面"
