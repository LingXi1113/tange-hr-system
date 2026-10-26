"""Changing the applied job always creates a fresh, independent delivery."""
from datetime import datetime, timedelta

import pytest

from common.consistency import reconcile_application_status
from common.db import col, insert_doc
from conftest import login
from helpers import assign, make_candidate, make_job, make_template


def setup(client, stage="interview_1"):
    template = make_template(client)
    first = make_job(client, "原岗位", template_id=template)
    second = make_job(client, "新岗位", template_id=template)
    cid = make_candidate(client)
    application = assign(client, cid, first["id"])
    with client.application.app_context():
        col("applications").update_one({"_id": application["id"]}, {"$set": {
            "current_stage": stage, "status": "pending_onboard" if stage == "pending_onboard" else "in_progress",
            "screening_result_id": 123, "screening_score": 99, "screening_decision": "pass",
            "last_interview_conclusion": "pass", "interview_round": "三面",
        }})
    return cid, application, first, second


def change(client, cid, application, job, **fields):
    return client.post(f"/api/candidates/{cid}/change-job", json={
        "application_id": application["id"], "job_id": job["id"],
        "version": application["version"], "reason": "更适合另一个岗位", **fields,
    }).get_json()


@pytest.mark.parametrize("stage", ["new_resume", "business_screen", "interview_1", "interview_2", "interview_3", "hrbp_interview", "offer_approval", "offer_pending", "pending_onboard"])
def test_change_restarts_screening_and_keeps_history(client, stage):
    cid, old, first, second = setup(client, stage)
    body = change(client, cid, old, second)
    assert body["code"] == 0, body
    new = body["data"]
    assert new["id"] != old["id"]
    assert new["job_id"] == second["id"]
    assert new["current_stage"] == "new_resume"
    assert new["status"] == "in_progress"
    assert new["process_state_key"] == "awaiting_hr_screen"
    assert new["previous_application_id"] == old["id"]
    assert new["screening_result_id"] is None
    assert new["screening_decision"] == ""
    assert new["last_interview_conclusion"] == ""
    with client.application.app_context():
        archived = col("applications").find_one({"_id": old["id"]})
        assert archived["status"] == "closed"
        assert archived["current_stage"] == "job_changed"
        assert archived["archived_from_stage"] == stage
        assert archived["job_id"] == first["id"]
        assert archived["replacement_application_id"] == new["id"]
        assert archived["screening_result_id"] == 123
        assert reconcile_application_status(archived)["status"] == "closed"
        locks = list(col("lock_records").find({"candidate_id": cid, "released": False}))
        assert len(locks) == 1
        assert locks[0]["application_id"] == new["id"]
        assert locks[0]["owner_id"] == "hr-001"
    detail = client.get(f"/api/candidates/{cid}").get_json()["data"]
    assert len(detail["applications"]) == 2
    assert detail["applications"][0]["id"] == new["id"]
    board = client.get("/api/pipeline/board").get_json()["data"]
    assert [item["id"] for item in board["cards"]] == [new["id"]]
    summary = client.get("/api/candidates/classification-summary").get_json()["data"]
    assert summary["stage_counts"]["pending_screen"] == 1
    if stage == "interview_2":
        assert summary["stage_counts"]["interview_2"] == 0
    assert client.get("/api/interviews/pending-applications").get_json()["data"]["total"] == 0
    assert client.post("/api/interviews", json={
        "application_id": new["id"], "round": "一面", "type": "video",
        "start_at": "2026-12-01 10:00", "interviewer_id": "interviewer-001",
    }).get_json()["code"] != 0
    analysis = client.get(f"/api/candidates/{cid}/delivery-analysis").get_json()["data"]
    assert analysis["summary"]["total_deliveries"] == 2
    history = next(item for item in analysis["applications"] if item["id"] == old["id"])
    fresh = next(item for item in analysis["applications"] if item["id"] == new["id"])
    assert fresh["highest_stage_name"] not in ("一面", "二面", "三面")
    assert history["status"] == "closed"
    assert any("更换为" in event["detail"] for event in history["timeline"])


def tasks(client, old):
    with client.application.app_context():
        common = {"application_id": old["id"], "candidate_id": old["candidate_id"], "job_id": old["job_id"], "version": 1}
        completed = insert_doc("interviews", {**common, "round": "一面", "status": "completed"})
        feedback = insert_doc("interview_feedback", {"interview_id": completed["_id"], "conclusion": "pass", "comment": "原岗位评价"})
        pending = insert_doc("interviews", {**common, "round": "二面", "status": "confirmed",
                             "start_at": datetime.now() + timedelta(days=1), "end_at": datetime.now() + timedelta(days=1, hours=1)})
        offer = insert_doc("offers", {**common, "status": "pending_send"})
        approval = insert_doc("offer_approvals", {"offer_id": offer["_id"], "status": "pending", "version": 1,
                              "steps": [{"name": "原审批节点", "status": "approved"}]})
        # MongoDB persists millisecond precision; compare persisted snapshots.
        return tuple(col(collection).find_one({"_id": doc["_id"]}) for collection, doc in zip(
            ("interviews", "interview_feedback", "interviews", "offers", "offer_approvals"),
            (completed, feedback, pending, offer, approval),
        ))


def test_old_tasks_stop_but_completed_records_are_unchanged(client):
    cid, old, _, second = setup(client, "offer_approval")
    completed, feedback, pending, offer, approval = tasks(client, old)
    body = change(client, cid, old, second)
    assert body["code"] == 0, body
    with client.application.app_context():
        assert col("interviews").find_one({"_id": completed["_id"]}) == completed
        assert col("interview_feedback").find_one({"_id": feedback["_id"]}) == feedback
        assert col("interviews").find_one({"_id": pending["_id"]})["status"] == "cancelled"
        assert col("offers").find_one({"_id": offer["_id"]})["status"] == "withdrawn"
        closed_approval = col("offer_approvals").find_one({"_id": approval["_id"]})
        assert closed_approval["status"] == "cancelled"
        assert closed_approval["steps"] == approval["steps"]
    # Old application must not be revived by consistency repair or stale clients.
    assert client.post(f"/api/applications/{old['id']}/direct-interview", json={"version": old["version"] + 1}).get_json()["code"] != 0
    assert client.post(f"/api/approvals/{approval['_id']}/action", json={"version": 2, "action": "approve"}).get_json()["code"] != 0


@pytest.mark.parametrize("case", ["same_job", "stale", "missing_version", "invalid_job", "other_candidate", "terminal", "other_owner", "interviewer"])
def test_invalid_or_unauthorized_changes_do_not_create_deliveries(client, case):
    cid, old, first, second = setup(client)
    fields = {}
    if case == "same_job": fields["job_id"] = first["id"]
    if case == "stale": fields["version"] = 99
    if case == "missing_version": fields["version"] = None
    if case == "invalid_job": fields["job_id"] = 99999
    if case == "other_candidate": fields["application_id"] = 99999
    if case == "terminal":
        with client.application.app_context():
            col("applications").update_one({"_id": old["id"]}, {"$set": {"current_stage": "eliminated", "status": "eliminated"}})
    if case == "other_owner":
        with client.application.app_context():
            col("lock_records").update_many({"candidate_id": cid}, {"$set": {"owner_id": "another-hr"}})
    if case == "interviewer": login(client, "interviewer-001")
    assert change(client, cid, old, second, **fields)["code"] != 0
    with client.application.app_context():
        assert col("applications").count_documents({"candidate_id": cid}) == 1
        assert col("lock_records").count_documents({"candidate_id": cid, "released": False}) == 1


@pytest.mark.parametrize("failure", ["create", "after_tasks"])
def test_standalone_failure_restores_original_application_locks_and_tasks(client, monkeypatch, failure):
    import common.job_change as service

    cid, old, _, second = setup(client, "offer_approval")
    records = tasks(client, old)
    with client.application.app_context():
        before = col("applications").find_one({"_id": old["id"]})
        locks = list(col("lock_records").find({"candidate_id": cid}))
        transitions = list(col("stage_transitions").find({"application_id": old["id"]}))

    def fail(*args, **kwargs):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(service, "create_application" if failure == "create" else "write_log", fail)
    with pytest.raises(RuntimeError):
        change(client, cid, old, second)
    with client.application.app_context():
        assert col("applications").find_one({"_id": old["id"]}) == before
        assert col("applications").count_documents({"candidate_id": cid}) == 1
        assert list(col("lock_records").find({"candidate_id": cid})) == locks
        assert list(col("stage_transitions").find({"application_id": old["id"]})) == transitions
        assert col("notifications").count_documents({"dedupe_key": {"$regex": "^new_candidate:application:2::"}}) == 0
        for collection, doc in zip(("interviews", "interview_feedback", "interviews", "offers", "offer_approvals"), records):
            assert col(collection).find_one({"_id": doc["_id"]}) == doc


def test_can_change_back_to_previous_job_without_reusing_old_history(client):
    cid, old, first, second = setup(client)
    new = change(client, cid, old, second)["data"]
    third = change(client, cid, new, first)
    assert third["code"] == 0, third
    assert third["data"]["id"] not in (new["id"], old["id"])
    assert third["data"]["current_stage"] == "new_resume"
    assert len(client.get(f"/api/candidates/{cid}/applications").get_json()["data"]) == 3


def test_concurrent_job_changes_create_only_one_new_delivery(client):
    from concurrent.futures import ThreadPoolExecutor

    cid, old, _, second = setup(client)
    app = client.application

    def attempt():
        with app.test_client() as worker:
            login(worker, "hr-001")
            return change(worker, cid, old, second)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: attempt(), range(2)))
    assert sum(result["code"] == 0 for result in results) == 1
    with app.app_context():
        assert col("applications").count_documents({"candidate_id": cid}) == 2
        assert col("applications").count_documents({"candidate_id": cid, "status": "in_progress"}) == 1
        assert col("lock_records").count_documents({"candidate_id": cid, "released": False}) == 1


def test_archived_completed_interview_does_not_leave_feedback_todo(client):
    cid, old, _, second = setup(client)
    with client.application.app_context():
        interview = insert_doc("interviews", {
            "application_id": old["id"], "candidate_id": cid, "job_id": old["job_id"],
            "round": "一面", "status": "completed", "version": 1,
            "start_at": datetime.now() - timedelta(days=1, hours=1),
            "end_at": datetime.now() - timedelta(days=1),
        })
    before = client.get("/api/dashboard/summary").get_json()["data"]
    assert before["todos"]["feedback_pending"] == 1
    assert change(client, cid, old, second)["code"] == 0
    after = client.get("/api/dashboard/summary").get_json()["data"]
    assert after["todos"]["feedback_pending"] == 0
    historical = client.get(f"/api/interviews/{interview['_id']}").get_json()["data"]
    assert historical["status"] == "completed"
    assert historical["application_archived"] is True
    assert historical["process_state_key"] == "archived"
