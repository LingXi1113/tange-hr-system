from datetime import datetime, timedelta

from helpers import assign, ensure_hr, make_candidate, make_job, publish_job


def _template(client, stages):
    return client.post("/api/pipeline-templates", json={
        "name": "一致性测试流程",
        "stages": [
            {"stage_key": key, "name": key, "sort_order": index + 1}
            for index, key in enumerate(stages)
        ],
    }).get_json()["data"]["id"]


def _setup(client, stages):
    ensure_hr(client)
    template_id = _template(client, stages)
    job = make_job(client, name="一致性测试职位", template_id=template_id)
    publish_job(client, job["id"])
    candidate_id = make_candidate(
        client, phone="13700009991", email="consistency@example.com",
    )
    return job, candidate_id, assign(client, candidate_id, job["id"])


def test_stage_cannot_move_backwards_and_pending_onboard_requires_accepted_offer(client):
    job, candidate_id, app = _setup(
        client, ["new_resume", "interview_passed", "offer_pending", "pending_onboard", "onboarded"],
    )
    moved = client.post(f"/api/applications/{app['id']}/move", json={
        "to_stage": "interview_passed", "reason": "面试通过", "version": app["version"],
    }).get_json()
    assert moved["code"] == 0
    blocked = client.post(f"/api/applications/{app['id']}/move", json={
        "to_stage": "new_resume", "reason": "回退测试", "version": moved["data"]["version"],
    }).get_json()
    assert blocked["code"] == 1003

    blocked = client.post(f"/api/applications/{app['id']}/move", json={
        "to_stage": "pending_onboard", "reason": "无 Offer 入职测试",
        "version": moved["data"]["version"],
    }).get_json()
    assert blocked["code"] == 1003

    with client.application.app_context():
        from common.db import col

        col("offers").insert_one({
            "_id": 90001, "application_id": app["id"], "candidate_id": candidate_id,
            "job_id": job["id"], "status": "accepted", "created_at": datetime.now(),
        })
    accepted = client.post(f"/api/applications/{app['id']}/move", json={
        "to_stage": "pending_onboard", "reason": "Offer 已接受",
        "version": moved["data"]["version"],
    }).get_json()
    assert accepted["code"] == 0
    assert accepted["data"]["status"] == "pending_onboard"


def test_interview_cannot_be_created_after_offer_stage(client):
    job, candidate_id, app = _setup(client, ["new_resume", "offer_pending"])
    moved = client.post(f"/api/applications/{app['id']}/move", json={
        "to_stage": "offer_pending", "reason": "进入 Offer 阶段", "version": app["version"],
    }).get_json()["data"]
    start = datetime.now() + timedelta(days=1)
    end = start + timedelta(hours=1)
    result = client.post("/api/interviews", json={
        "application_id": app["id"], "candidate_id": candidate_id, "job_id": job["id"],
        "round": "一面", "type": "video",
        "start_at": start.strftime("%Y-%m-%d %H:%M"),
        "end_at": end.strftime("%Y-%m-%d %H:%M"),
    }).get_json()
    assert result["code"] == 1003


def test_elimination_uses_application_version(client):
    job, candidate_id, app = _setup(client, ["new_resume", "interview_passed"])
    first = client.post(f"/api/applications/{app['id']}/eliminate", json={
        "reason": "不符合岗位要求", "version": app["version"],
    }).get_json()
    assert first["code"] == 0
    second = client.post(f"/api/applications/{app['id']}/eliminate", json={
        "reason": "重复操作", "version": app["version"],
    }).get_json()
    assert second["code"] in (1003, 1007)
