"""Candidate identity decisions must precede master-profile creation/merging."""
import io

from common.db import col
from conftest import login
from helpers import ensure_hr
import pytest
from pymongo.errors import DuplicateKeyError


BASE = {"name": "王晓明", "phone": "13955551111", "email": "wang@example.com"}


def submit(client, payload):
    body = client.post("/api/candidates", json=payload).get_json()
    assert body["code"] == 0, body
    return body["data"]


def confirm(client, payload, report, decision):
    return submit(client, {**payload, "duplicate_review": {
        "token": report["review_token"],
        "decisions": {str(c["id"]): decision for c in report["duplicates"]},
    }})


def test_exact_identity_merges_into_master_and_records_decision(client):
    ensure_hr(client)
    original = submit(client, BASE)["candidate"]
    payload = {**BASE, "email": " WANG@example.com ", "city": "广州",
               "education": [{"school": "测试大学", "degree": "本科"}]}
    report = submit(client, payload)
    assert report["duplicate_kind"] == "exact"
    assert report["duplicates"][0]["matched_fields"] == ["name", "phone", "email"]
    with client.application.app_context():
        assert col("candidates").count_documents({}) == 1
    result = confirm(client, payload, report, "same")
    assert result["merged"] is True
    assert result["candidate"]["id"] == original["id"]
    assert result["candidate"]["city"] == "广州"
    with client.application.app_context():
        assert col("candidates").count_documents({}) == 1
        assert col("operation_logs").count_documents({"action": "duplicate_confirm_same"}) == 1
        assert col("operation_logs").count_documents({"action": "merge"}) == 1


def test_partial_identity_blocks_force_and_can_be_confirmed_different(client):
    ensure_hr(client)
    submit(client, BASE)
    payload = {**BASE, "name": "另一位王先生", "email": "other@example.com"}
    report = submit(client, {**payload, "force": 1})
    assert report["duplicate_kind"] == "suspected"
    with client.application.app_context():
        assert col("candidates").count_documents({}) == 1
    # The legacy force flag has no special meaning and cannot bypass review.
    result = confirm(client, payload, report, "different")
    assert result["duplicated"] is False
    with client.application.app_context():
        assert col("candidates").count_documents({}) == 2
        assert col("operation_logs").count_documents({"action": "duplicate_confirm_different"}) == 1
    # Even the exempt profile must not be duplicated on a later submission.
    assert submit(client, payload)["duplicate_kind"] == "exact"


def test_same_name_requires_review_and_empty_values_do_not_match(client):
    ensure_hr(client)
    submit(client, {"name": "同名人员"})
    report = submit(client, {"name": "同名人员", "phone": "13955552222"})
    assert report["duplicate_kind"] == "suspected"
    assert report["duplicates"][0]["matched_fields"] == ["name"]
    assert submit(client, {"name": "无关联人员"})["duplicated"] is False


def test_suspected_same_person_adds_histories_without_overwriting_master(client):
    ensure_hr(client)
    original = submit(client, {**BASE, "city": "深圳"})["candidate"]
    payload = {**BASE, "email": "new@example.com", "city": "广州",
               "work_experience": [{"company": "示例科技", "start": "2020", "end": "2024"}]}
    report = submit(client, payload)
    result = confirm(client, payload, report, "same")
    assert result["candidate"]["id"] == original["id"]
    assert result["candidate"]["email"] == BASE["email"]
    assert result["candidate"]["city"] == "深圳"
    with client.application.app_context():
        master = col("candidates").find_one({"_id": original["id"]})
        assert master["work_experience"][0]["company"] == "示例科技"


def test_review_cannot_be_forged_reused_for_changed_payload_or_other_hr(client):
    ensure_hr(client)
    submit(client, BASE)
    payload = {**BASE, "email": "second@example.com"}
    report = submit(client, payload)
    forged = {**payload, "duplicate_review": {"token": "forged", "decisions": {"1": "different"}}}
    assert submit(client, forged)["duplicated"] is True
    assert confirm(client, {**payload, "phone": "13955553333"}, report, "different")["duplicated"] is True
    login(client, "hr-002")
    assert confirm(client, payload, report, "different")["duplicated"] is True
    with client.application.app_context():
        assert col("candidates").count_documents({}) == 1


def test_all_matches_must_be_reviewed_and_exact_identity_cannot_be_overridden(client):
    ensure_hr(client)
    submit(client, BASE)
    submit(client, {"name": "李晓华", "phone": "13955554444", "email": "li@example.com"})
    payload = {**BASE, "phone": "13955554444", "email": "third@example.com"}
    report = submit(client, payload)
    assert len(report["duplicates"]) == 2
    partial = {**payload, "duplicate_review": {
        "token": report["review_token"], "decisions": {str(report["duplicates"][0]["id"]): "different"},
    }}
    assert submit(client, partial)["duplicated"] is True
    exact = submit(client, BASE)
    response = client.post("/api/candidates", json={**BASE, "duplicate_review": {
        "token": exact["review_token"], "decisions": {str(exact["duplicates"][0]["id"]): "different"},
    }}).get_json()
    assert response["code"] == 1001


def test_import_suspected_row_waits_for_hr_without_creating_profile(client):
    ensure_hr(client)
    submit(client, BASE)
    csv = "姓名,性别,手机号,邮箱,城市,来源\n王晓明,男,13955556666,new@example.com,广州,import\n"
    result = client.post("/api/candidates/import", data={
        "file": (io.BytesIO(csv.encode()), "candidates.csv"),
    }).get_json()["data"]
    assert result["success_count"] == 0
    row = result["duplicates"][0]
    assert row["review"]["duplicate_kind"] == "suspected"
    saved = confirm(client, row["payload"], row["review"], "different")
    assert saved["duplicated"] is False


def test_candidate_edit_requires_confirmation_when_identity_changes(client):
    ensure_hr(client)
    submit(client, BASE)
    candidate = submit(client, {"name": "李四", "phone": "13955557777", "email": "li4@example.com"})["candidate"]
    payload = {"phone": BASE["phone"], "version": candidate["version"]}
    url = f"/api/candidates/{candidate['id']}"
    report = client.put(url, json={**payload, "force": 1}).get_json()["data"]
    assert report["duplicate_kind"] == "suspected"
    result = client.put(url, json={**payload, "duplicate_review": {
        "token": report["review_token"],
        "decisions": {str(c["id"]): "different" for c in report["duplicates"]},
    }}).get_json()
    assert result["code"] == 0, result
    assert result["data"]["candidate"]["phone"] == BASE["phone"]


def test_full_identity_unique_index_still_protects_confirmed_different_profiles(client):
    ensure_hr(client)
    submit(client, BASE)
    payload = {**BASE, "name": "另一个王先生"}
    result = confirm(client, payload, submit(client, payload), "different")
    with client.application.app_context():
        original = col("candidates").find_one({"_id": result["candidate"]["id"]})
        duplicate = {**original, "_id": 99999}
        with pytest.raises(DuplicateKeyError):
            col("candidates").insert_one(duplicate)


def test_changed_historical_profile_invalidates_previous_confirmation(client):
    ensure_hr(client)
    original = submit(client, BASE)["candidate"]
    payload = {**BASE, "email": "changed@example.com"}
    report = submit(client, payload)
    with client.application.app_context():
        col("candidates").update_one({"_id": original["id"]}, {"$inc": {"version": 1}})
    refreshed = confirm(client, payload, report, "different")
    assert refreshed["duplicated"] is True
    assert refreshed["review_token"] != report["review_token"]
    with client.application.app_context():
        assert col("candidates").count_documents({}) == 1
