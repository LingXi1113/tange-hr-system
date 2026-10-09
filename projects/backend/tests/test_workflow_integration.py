from datetime import datetime, timedelta

from conftest import login
from helpers import assign, make_candidate, make_job, publish_job


def _future_date(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


def test_candidate_to_onboarding_workflow_and_dashboard_links(client):
    login(client, "super-admin-001")
    template_id = client.post("/api/pipeline-templates", json={
        "name": "全链路串联测试流程",
        "stages": [
            {"stage_key": "new_resume", "name": "简历初筛", "sort_order": 1},
            {"stage_key": "pending_interview", "name": "一面", "sort_order": 2},
            {"stage_key": "offer_pending", "name": "录用审批", "sort_order": 3},
            {"stage_key": "pending_onboard", "name": "待入职", "sort_order": 4},
            {"stage_key": "onboarded", "name": "已入职", "sort_order": 5},
        ],
    }).get_json()["data"]["id"]
    assert client.put("/api/system/offer-approvers", json={
        "org_approver_id": "org-001",
        "gm_id": "gm-001",
        "chairman_id": "chairman-001",
        "offer_sender_id": "offer-001",
    }).get_json()["code"] == 0

    login(client, "hr-001")
    job = make_job(client, name="全链路串联职位", template_id=template_id)
    publish_job(client, job["id"])
    candidate_id = make_candidate(
        client, name="全链路候选人", phone="13977001122", email="workflow@example.com",
    )
    assert client.put(f"/api/candidates/{candidate_id}", json={
        "source": "referral", "city": "杭州",
    }).get_json()["code"] == 0
    application = assign(client, candidate_id, job["id"], source="referral")

    dashboard = client.get("/api/dashboard/summary").get_json()["data"]
    screening = next(group for group in dashboard["workbench_metrics"] if group["key"] == "screening")
    assert next(item for item in screening["items"] if item["key"] == "unprocessed")["count"] == 1
    assert next(item for item in screening["items"] if item["key"] == "referral")["count"] == 1

    application = client.post(f"/api/applications/{application['id']}/direct-interview", json={
        "version": application["version"],
    }).get_json()["data"]
    waiting = client.get("/api/candidates", query_string={
        "action_state": "awaiting_interview_schedule",
    }).get_json()["data"]
    dashboard = client.get("/api/dashboard/summary").get_json()["data"]
    waiting_metric = next(
        item for group in dashboard["workbench_metrics"]
        for item in group["items"] if item["key"] == "waiting_schedule"
    )
    assert waiting_metric["count"] == waiting["total"] == 1

    start = datetime.now() + timedelta(days=1)
    interview = client.post("/api/interviews", json={
        "application_id": application["id"],
        "round": "一面", "type": "video",
        "start_at": start.strftime("%Y-%m-%d %H:%M"),
        "end_at": (start + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"),
        "interviewer_id": "interviewer-001",
    }).get_json()["data"]
    for action in ("invite", "confirm"):
        interview = client.post(f"/api/interviews/{interview['id']}/status", json={
            "action": action, "version": interview["version"],
        }).get_json()["data"]

    login(client, "interviewer-001")
    assert client.post(f"/api/interviews/{interview['id']}/feedback", json={
        "conclusion": "pass", "comment": "通过",
        "dimension_scores": [{"name": "专业能力", "score": 5}],
    }).get_json()["code"] == 0
    assert client.post(f"/api/interviews/{interview['id']}/complete", json={
        "version": interview["version"],
    }).get_json()["code"] == 0

    login(client, "hr-002")
    detail = client.get(f"/api/candidates/{candidate_id}").get_json()["data"]
    application = detail["applications"][0]
    assert application["process_state_key"] == "interview_evaluated"
    moved = client.post(f"/api/applications/{application['id']}/move", json={
        "to_stage": "offer_pending", "reason": "评价通过，进入录用审批",
        "version": application["version"],
    }).get_json()
    assert moved["code"] == 0

    login(client, "hr-001")
    offer = client.post("/api/offers", json={
        "application_id": application["id"], "dept": "研发部", "position": "测试工程师",
        "salary": "20k", "onboard_date": _future_date(30), "valid_until": _future_date(10),
    }).get_json()["data"]
    offer = client.post(f"/api/offers/{offer['id']}/status", json={
        "action": "submit", "version": offer["version"],
    }).get_json()["data"]
    assert offer["approval_status"] == "pending"
    blocked_send = client.post(f"/api/offers/{offer['id']}/status", json={
        "action": "send", "version": offer["version"],
    }).get_json()
    assert blocked_send["code"] == 1003

    approval = client.get("/api/approvals", query_string={"status": "pending"}).get_json()["data"]["list"][0]
    for user_id in ("org-001", "gm-001", "chairman-001"):
        login(client, user_id)
        approval = client.post(f"/api/approvals/{approval['id']}/action", json={
            "action": "approve", "version": approval["version"],
        }).get_json()["data"]
    assert approval["status"] == "approved"

    login(client, "hr-001")
    offer = client.get(f"/api/offers/{offer['id']}").get_json()["data"]
    assert offer["approval_status"] == "approved"
    offer = client.post(f"/api/offers/{offer['id']}/status", json={
        "action": "send", "version": offer["version"],
    }).get_json()["data"]
    offer = client.post(f"/api/offers/{offer['id']}/status", json={
        "action": "accept", "version": offer["version"],
    }).get_json()["data"]
    assert offer["status"] == "accepted"

    onboarding = client.get("/api/onboarding", query_string={
        "application_stage": "pending_onboard",
    }).get_json()["data"]
    assert onboarding["total"] == 1
    record = onboarding["list"][0]
    record = client.post(f"/api/onboarding/{record['id']}/start", json={
        "version": record["version"],
    }).get_json()["data"]
    for item in record["checklist"]:
        record = client.post(f"/api/onboarding/{record['id']}/items/{item['key']}", json={
            "status": "verified", "version": record["version"],
        }).get_json()["data"]
    completed = client.post(f"/api/onboarding/{record['id']}/complete", json={
        "version": record["version"],
    }).get_json()["data"]
    assert completed["application_stage"] == "onboarded"

    final_detail = client.get(f"/api/candidates/{candidate_id}").get_json()["data"]
    assert final_detail["applications"][0]["current_stage"] == "onboarded"
    dashboard = client.get("/api/dashboard/summary").get_json()["data"]
    onboarding_metric = next(
        item for group in dashboard["workbench_metrics"]
        for item in group["items"] if item["key"] == "pending_onboard"
    )
    assert onboarding_metric["count"] == 0


def test_rejected_offer_approval_returns_to_editable_draft(client):
    login(client, "super-admin-001")
    template_id = client.post("/api/pipeline-templates", json={
        "name": "Offer驳回重提流程",
        "stages": [
            {"stage_key": "new_resume", "name": "初筛", "sort_order": 1},
            {"stage_key": "offer_pending", "name": "录用审批", "sort_order": 2},
        ],
    }).get_json()["data"]["id"]
    assert client.put("/api/system/offer-approvers", json={
        "org_approver_id": "org-001", "gm_id": "gm-001",
        "chairman_id": "chairman-001", "offer_sender_id": "offer-001",
    }).get_json()["code"] == 0
    login(client, "hr-001")
    job = make_job(client, name="Offer驳回重提职位", template_id=template_id)
    publish_job(client, job["id"])
    candidate_id = make_candidate(client, phone="13977003344", email="offer-retry@example.com")
    application = assign(client, candidate_id, job["id"])
    application = client.post(f"/api/applications/{application['id']}/move", json={
        "to_stage": "offer_pending", "reason": "进入录用审批", "version": application["version"],
    }).get_json()["data"]
    offer = client.post("/api/offers", json={
        "application_id": application["id"], "dept": "研发部", "position": "开发工程师",
        "salary": "20k", "onboard_date": _future_date(30), "valid_until": _future_date(10),
    }).get_json()["data"]
    offer = client.post(f"/api/offers/{offer['id']}/status", json={
        "action": "submit", "version": offer["version"],
    }).get_json()["data"]
    approval = client.get("/api/approvals", query_string={"status": "pending"}).get_json()["data"]["list"][0]

    login(client, "org-001")
    rejected = client.post(f"/api/approvals/{approval['id']}/action", json={
        "action": "reject", "reason": "薪资需调整", "version": approval["version"],
    }).get_json()["data"]
    assert rejected["status"] == "rejected"

    login(client, "hr-001")
    offer = client.get(f"/api/offers/{offer['id']}").get_json()["data"]
    assert offer["status"] == "draft"
    offer = client.put(f"/api/offers/{offer['id']}", json={
        "salary": "22k", "version": offer["version"],
    }).get_json()["data"]
    offer = client.post(f"/api/offers/{offer['id']}/status", json={
        "action": "submit", "version": offer["version"],
    }).get_json()["data"]
    assert offer["approval_status"] == "pending"
