from datetime import datetime, timedelta

from common.db import col, dt, next_id

from tests.helpers import assign, ensure_hr, make_candidate, make_job, publish_job
from tests.conftest import login


def _offer(client):
    ensure_hr(client)
    job = make_job(client, name="Approval Job")
    publish_job(client, job["id"])
    candidate = make_candidate(client, name="Approval Candidate", phone="13700001001", email="approval@example.com")
    application = assign(client, candidate, job["id"])
    now = datetime.now()
    with client.application.app_context():
        col("applications").update_one({"_id": application["id"]}, {"$set": {"current_stage": "interview_passed"}})
        col("offer_approver_config").insert_one({
            "_id": 1,
            "org_approver_id": "org-001", "org_approver_name": "陈静",
            "gm_id": "gm-001", "gm_name": "赵敏",
            "chairman_id": "chairman-001", "chairman_name": "孙浩",
            "offer_sender_id": "offer-001", "offer_sender_name": "周婷",
        })
    response = client.post("/api/offers", json={
        "application_id": application["id"], "dept": "技术中心", "position": "工程师",
        "salary": "30k", "onboard_date": "2099-01-01", "valid_until": "2099-01-15",
    })
    assert response.get_json()["code"] == 0
    offer = response.get_json()["data"]
    submitted = client.post(f"/api/offers/{offer['id']}/status", json={"action": "submit", "version": offer["version"]})
    assert submitted.get_json()["code"] == 0
    return offer["id"]


def test_offer_approval_chain_can_be_created_and_acted(client):
    offer_id = _offer(client)

    approvals = client.get("/api/approvals").get_json()["data"]
    assert approvals["total"] == 1
    approval = approvals["list"][0]
    assert approval["offer_id"] == offer_id
    assert approval["steps"][0]["approver_id"] == "org-001"
    assert approval["deadline_at"] and approval["overdue"] is False

    login(client, "org-001")
    acted = client.post(f"/api/approvals/{approval['id']}/action", json={
        "action": "approve", "version": approval["version"],
    }).get_json()
    assert acted["code"] == 0
    assert acted["data"]["current_step"] == "gm"

    login(client, "gm-001")
    acted = client.post(f"/api/approvals/{approval['id']}/action", json={
        "action": "reject", "version": acted["data"]["version"], "reason": "薪资需要重新确认",
    }).get_json()
    assert acted["code"] == 0
    assert acted["data"]["status"] == "rejected"

    with client.application.app_context():
        assert col("operation_logs").count_documents({"biz_type": "offer_approval"}) == 2


def test_overdue_approval_is_exposed_and_notifies_hr(client):
    offer_id = _offer(client)
    with client.application.app_context():
        approval = col("offer_approvals").find_one({"offer_id": offer_id})
        col("offer_approvals").update_one(
            {"_id": approval["_id"]},
            {"$set": {"deadline_at": datetime.now() - timedelta(days=1)}},
        )
    approvals = client.get("/api/approvals").get_json()["data"]["list"]
    assert approvals[0]["overdue"] is True
    notes = client.get("/api/notifications").get_json()["data"]["list"]
    assert any(item["scene"] == "approval_due" for item in notes)


def test_onboarding_checklist_and_complete_moves_application(client):
    ensure_hr(client)
    job = make_job(client, name="Onboarding Job")
    publish_job(client, job["id"])
    candidate = make_candidate(client, name="Onboarding Candidate", phone="13700001002", email="onboard@example.com")
    application = assign(client, candidate, job["id"])
    with client.application.app_context():
        template_id = next_id("pipeline_templates")
        now = datetime.now()
        col("pipeline_templates").insert_one({
            "_id": template_id, "name": "Onboarding Test Template", "status": "active",
            "stages": [{"stage_key": key, "name": key, "category": "test", "sort_order": i,
                         "optional_flag": False, "lock_days": 0}
                        for i, key in enumerate(["new_resume", "pending_onboard", "onboarded"], 1)],
            "created_at": now, "updated_at": now,
        })
        col("jobs").update_one({"_id": job["id"]}, {"$set": {"template_id": template_id}})
        col("applications").update_one({"_id": application["id"]}, {"$set": {"current_stage": "pending_onboard"}})

    records = client.get("/api/onboarding").get_json()["data"]
    assert records["total"] == 1
    record = records["list"][0]
    assert record["candidate_name"] == "Onboarding Candidate"
    login(client, "ssc-001")
    detail = client.get(f"/api/onboarding/{record['id']}").get_json()["data"]
    for item in detail["checklist"]:
        result = client.post(f"/api/onboarding/{record['id']}/items/{item['key']}", json={"status": "verified"})
        assert result.get_json()["code"] == 0
    completed = client.post(f"/api/onboarding/{record['id']}/complete").get_json()
    assert completed["code"] == 0
    assert completed["data"]["status"] == "completed"
    with client.application.app_context():
        app = col("applications").find_one({"_id": application["id"]})
        assert app["current_stage"] == "onboarded"
