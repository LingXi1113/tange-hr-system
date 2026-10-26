"""Candidate facets, list rows and workbench cards must use the same predicates."""
import pytest

from common.db import col, insert_doc
from helpers import assign, make_candidate, make_job, make_template, publish_job


def setup_people(client):
    template = make_template(client)
    job1 = make_job(client, name="Count job A", template_id=template)
    job2 = make_job(client, name="Count job B", template_id=template)
    for job in (job1, job2):
        publish_job(client, job["id"])
    candidates = []
    applications = []
    for index, source in enumerate(("headhunt", "manual", "referral"), 1):
        candidate = make_candidate(client, name=f"Count person {index}",
                                   phone=f"1398800100{index}", email=f"count-{index}@example.com")
        candidates.append(candidate)
        applications.append(assign(client, candidate, job1["id"] if index != 2 else job2["id"], source=source))
    unassigned = make_candidate(client, name="Unassigned count person", phone="13988001004", email="count-4@example.com")
    with client.application.app_context():
        col("jobs").update_one({"_id": job1["id"]}, {"$set": {"dept_id": "count-dept-A"}})
        col("jobs").update_one({"_id": job2["id"]}, {"$set": {"dept_id": "count-dept-B"}})
        col("candidates").update_one({"_id": candidates[0]}, {"$set": {"tags": "待定", "highest_education": "本科"}})
        col("candidates").update_one({"_id": candidates[2]}, {"$set": {"highest_education": "大专"}})
        col("candidates").update_one({"_id": unassigned}, {"$set": {"tags": "待定"}})
        col("applications").update_one({"_id": applications[1]["id"]}, {"$set": {
            "current_stage": "interview_1", "status": "in_progress", "next_action": "schedule_interview",
        }})
    return job1, job2, candidates, applications, unassigned


@pytest.mark.parametrize("scope", [
    {}, {"stage": "pending_screen"}, {"stage": "interview_1"}, {"highest_education": "本科"},
    {"job_dept_id": "count-dept-A"}, {"keyword": "Count person 1"}, {"source": "referral"}, {"locked": "1"},
])
def test_each_facet_count_equals_its_filtered_list(client, scope):
    setup_people(client)
    summary = client.get("/api/candidates/classification-summary", query_string=scope).get_json()["data"]
    for filters, count in (({"unprocessed": "1"}, summary["categories"]["unprocessed"]),
                           ({"category": "pending"}, summary["categories"]["pending"]),
                           ({"category": "recommended"}, summary["categories"]["recommended"]),
                           ({"unassigned": "1"}, summary["unassigned"])):
        body = client.get("/api/candidates", query_string={**scope, **filters, "include_summary": "1"}).get_json()
        assert body["code"] == 0, body
        assert body["data"]["total"] == count
        assert body["data"]["classification"] == summary


def test_job_scope_applies_to_all_facets(client):
    job1, job2, _, _, _ = setup_people(client)
    for job in (job1, job2):
        summary = client.get("/api/candidates/classification-summary", query_string={"job_id": job["id"]}).get_json()["data"]
        for category in ("pending", "recommended"):
            result = client.get("/api/candidates", query_string={"job_id": job["id"], "category": category}).get_json()["data"]
            assert summary["categories"][category] == result["total"]
        assert summary["unassigned"] == 0


def test_stage_change_updates_embedded_counts_and_workbench(client):
    _, _, _, applications, _ = setup_people(client)
    before = client.get("/api/candidates", query_string={"stage": "pending_screen", "include_summary": "1"}).get_json()["data"]
    application = applications[0]
    moved = client.post(f"/api/applications/{application['id']}/direct-interview", json={"version": application["version"]}).get_json()
    assert moved["code"] == 0, moved
    after = client.get("/api/candidates", query_string={"stage": "pending_screen", "include_summary": "1"}).get_json()["data"]
    assert after["total"] == before["total"] - 1
    assert after["classification"]["categories"]["unprocessed"] == before["classification"]["categories"]["unprocessed"] - 1
    dashboard = client.get("/api/dashboard/summary").get_json()["data"]
    metric = next(item for group in dashboard["workbench_metrics"] for item in group["items"] if item["key"] == "unprocessed")
    assert metric["count"] == after["classification"]["categories"]["unprocessed"]


def test_workbench_recommendation_and_both_routes_include_referrals(client):
    setup_people(client)
    dashboard = client.get("/api/dashboard/summary").get_json()["data"]
    count = next(item["count"] for group in dashboard["workbench_metrics"] for item in group["items"] if item["key"] == "recommended")
    summary = client.get("/api/candidates/classification-summary").get_json()["data"]
    assert count == summary["categories"]["recommended"] == 2
    for params in ({"category": "recommended"}, {"source_group": "talent_recommendation"}):
        assert client.get("/api/candidates", query_string=params).get_json()["data"]["total"] == count


def test_multiple_applications_count_once_and_show_matching_stage(client):
    job1, job2, candidates, applications, _ = setup_people(client)
    job3 = make_job(client, name="Count job C")
    publish_job(client, job3["id"])
    with client.application.app_context():
        insert_doc("applications", {"candidate_id": candidates[0], "job_id": job2["id"],
            "current_stage": "interview_1", "status": "in_progress", "source": "manual"})
        insert_doc("applications", {"candidate_id": candidates[0], "job_id": job3["id"],
            "current_stage": "interview_1", "status": "in_progress", "source": "manual"})
    data = client.get("/api/candidates", query_string={"stage": "pending_screen", "include_summary": "1"}).get_json()["data"]
    row = next(candidate for candidate in data["list"] if candidate["id"] == candidates[0])
    assert row["application_id"] == applications[0]["id"]
    assert row["current_stage"] == "new_resume"
    assert data["classification"]["stage_counts"]["pending_screen"] == data["total"]
    interviews = client.get("/api/candidates", query_string={"stage": "interview_1", "job_id": job2["id"], "include_summary": "1"}).get_json()["data"]
    assert interviews["total"] == 2
    assert interviews["classification"]["stage_counts"]["interview_1"] == 2
    assert all(candidate["current_stage"] == "interview_1" for candidate in interviews["list"])
    assert client.get("/api/candidates", query_string={"stage": "interview_1", "job_id": job1["id"]}).get_json()["data"]["total"] == 0


def test_selected_subcategory_does_not_zero_other_facets_or_depend_on_pagination(client):
    setup_people(client)
    common = {"stage": "pending_screen", "include_summary": "1", "category": "recommended"}
    page1 = client.get("/api/candidates", query_string={**common, "page": 1, "page_size": 1}).get_json()["data"]
    page2 = client.get("/api/candidates", query_string={**common, "page": 2, "page_size": 1}).get_json()["data"]
    assert page1["classification"] == page2["classification"]
    assert page1["classification"]["categories"]["pending"] == 2
    assert page1["classification"]["categories"]["recommended"] == page1["total"] == 2
