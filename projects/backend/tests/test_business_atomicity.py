import pytest

from common.db import col
from tests.helpers import assign, ensure_hr, make_candidate, make_job, make_template, publish_job


def _offer_setup(client):
    ensure_hr(client)
    template_id = make_template(client)
    job = make_job(client, name="一致性 Offer 岗位", template_id=template_id)
    publish_job(client, job["id"])
    candidate_id = make_candidate(
        client, name="一致性候选人", phone="13988880001", email="atomic@example.com",
    )
    application = assign(client, candidate_id, job["id"])
    with client.application.app_context():
        col("applications").update_one(
            {"_id": application["id"]},
            {"$set": {"current_stage": "interview_passed"}},
        )
    offer = client.post("/api/offers", json={
        "application_id": application["id"],
        "dept": "技术中心", "position": "一致性测试工程师", "salary": "30k",
        "onboard_date": "2099-01-01", "valid_until": "2099-01-15",
    }).get_json()["data"]
    submitted = client.post(
        f"/api/offers/{offer['id']}/status",
        json={"action": "submit", "version": offer["version"]},
    ).get_json()["data"]
    return application["id"], submitted["id"]


def test_stage_transition_rolls_back_when_lock_write_fails(client, monkeypatch):
    ensure_hr(client)
    template_id = make_template(client)
    job = make_job(client, name="阶段回滚岗位", template_id=template_id)
    publish_job(client, job["id"])
    candidate_id = make_candidate(
        client, name="阶段回滚候选人", phone="13988880002", email="stage-atomic@example.com",
    )
    application = assign(client, candidate_id, job["id"])

    def fail_lock(*args, **kwargs):
        raise RuntimeError("simulated lock write failure")

    monkeypatch.setattr("common.flow.start_stage_lock", fail_lock)
    with pytest.raises(RuntimeError, match="simulated lock write failure"):
        client.post(f"/api/applications/{application['id']}/move", json={
            "to_stage": "business_screen", "reason": "模拟锁写入失败",
            "version": application["version"],
        })

    with client.application.app_context():
        current = col("applications").find_one({"_id": application["id"]})
        assert current["current_stage"] == "new_resume"
        assert current["version"] == application["version"]
        assert col("stage_transitions").count_documents({
            "application_id": application["id"], "to_stage": "business_screen",
        }) == 0


def test_offer_and_application_roll_back_together_when_linked_stage_fails(client, monkeypatch):
    application_id, offer_id = _offer_setup(client)

    def fail_stage(*args, **kwargs):
        raise RuntimeError("simulated linked stage failure")

    monkeypatch.setattr("modules.offer_api._move_application_stage", fail_stage)
    with client.application.app_context():
        offer = col("offers").find_one({"_id": offer_id})
        application = col("applications").find_one({"_id": application_id})

    with pytest.raises(RuntimeError, match="simulated linked stage failure"):
        client.post(f"/api/offers/{offer_id}/status", json={
            "action": "send", "version": offer["version"],
        })

    with client.application.app_context():
        current_offer = col("offers").find_one({"_id": offer_id})
        current_application = col("applications").find_one({"_id": application_id})
        assert current_offer["status"] == "pending_send"
        assert current_offer["version"] == offer["version"]
        assert current_application["current_stage"] == application["current_stage"]
        assert current_application["version"] == application["version"]
