"""Resume storage requires a bound job; candidate saves bind before returning."""
import io

import pytest

from common.db import col
from common.errors import BizError
from common.response import BizCode
from helpers import ensure_hr, make_candidate, make_job


def upload(client, candidate_id=None):
    data = {"file": (io.BytesIO(b"sample resume"), "resume.pdf")}
    if candidate_id is not None:
        data["candidate_id"] = str(candidate_id)
    return client.post("/api/resume/upload", data=data).get_json()


def test_resume_upload_requires_candidate_and_job_before_storing_any_file(client):
    ensure_hr(client)
    cid = make_candidate(client)
    assert upload(client)["code"] == 1001
    assert upload(client, cid)["code"] == 1001
    assert upload(client, "invalid")["code"] == 1001
    with client.application.app_context():
        assert col("attachments").count_documents({}) == 0
        assert col("files").count_documents({}) == 0


@pytest.mark.parametrize("job_id", [None, "", 0, -1, True, "invalid", 999999])
def test_explicit_missing_or_invalid_position_does_not_create_candidate(client, job_id):
    ensure_hr(client)
    result = client.post("/api/candidates", json={"name": "绑定校验", "job_id": job_id}).get_json()
    assert result["code"] == 1001, result
    with client.application.app_context():
        assert col("candidates").count_documents({}) == 0
        assert col("applications").count_documents({}) == 0


def test_create_candidate_binds_job_before_resume_can_be_saved(client):
    ensure_hr(client)
    job = make_job(client)
    result = client.post("/api/candidates", json={
        "name": "职位绑定候选人", "phone": "13966551111", "job_id": job["id"],
    }).get_json()
    assert result["code"] == 0, result
    data = result["data"]
    assert data["application"]["job_id"] == job["id"]
    assert data["application"]["candidate_id"] == data["candidate"]["id"]
    assert upload(client, data["candidate"]["id"])["code"] == 0
    with client.application.app_context():
        attachment = col("attachments").find_one({"candidate_id": data["candidate"]["id"]})
        assert attachment["job_id"] == job["id"]
        assert attachment["application_id"] == data["application"]["id"]


def test_failed_job_assignment_rolls_back_new_candidate(client, monkeypatch):
    ensure_hr(client)
    job = make_job(client)

    def reject_assignment(*args, **kwargs):
        raise BizError(BizCode.LOCKED, "测试岗位绑定失败")

    monkeypatch.setattr("modules.candidate_api.create_application", reject_assignment)
    result = client.post("/api/candidates", json={"name": "回滚测试", "job_id": job["id"]}).get_json()
    assert result["code"] == 1005, result
    with client.application.app_context():
        assert col("candidates").count_documents({}) == 0
        assert col("applications").count_documents({}) == 0


def test_resume_cannot_be_uploaded_to_an_unassigned_job(client):
    ensure_hr(client)
    job = make_job(client)
    other_job = make_job(client, name="尚未分配的岗位")
    created = client.post("/api/candidates", json={"name": "指定岗位校验", "job_id": job["id"]}).get_json()["data"]
    result = client.post("/api/resume/upload", data={
        "candidate_id": str(created["candidate"]["id"]), "job_id": str(other_job["id"]),
        "file": (io.BytesIO(b"sample resume"), "resume.pdf"),
    }).get_json()
    assert result["code"] == 1001, result
    with client.application.app_context():
        assert col("attachments").count_documents({}) == 0
        assert col("files").count_documents({}) == 0


def test_duplicate_merge_reuses_selected_job_application(client):
    ensure_hr(client)
    job = make_job(client)
    payload = {"name": "重复绑定", "phone": "13966552222", "email": "bind@example.com", "job_id": job["id"]}
    first = client.post("/api/candidates", json=payload).get_json()["data"]
    report = client.post("/api/candidates", json=payload).get_json()["data"]
    assert report["duplicated"] is True
    result = client.post("/api/candidates", json={**payload, "duplicate_review": {
        "token": report["review_token"],
        "decisions": {str(c["id"]): "same" for c in report["duplicates"]},
    }}).get_json()
    assert result["code"] == 0, result
    assert result["data"]["merged"] is True
    assert result["data"]["application"]["id"] == first["application"]["id"]
    with client.application.app_context():
        assert col("candidates").count_documents({}) == 1
        assert col("applications").count_documents({}) == 1


def test_batch_import_binds_each_new_candidate_to_selected_job(client):
    ensure_hr(client)
    job = make_job(client)
    csv = "姓名,性别,手机号,邮箱,城市,来源\n批量甲,男,13966553333,a@bind.test,广州,import\n批量乙,女,13966554444,b@bind.test,深圳,import\n"
    result = client.post("/api/candidates/import", data={
        "file": (io.BytesIO(csv.encode()), "candidates.csv"), "job_id": str(job["id"]),
    }).get_json()
    assert result["code"] == 0, result
    assert result["data"]["success_count"] == 2
    with client.application.app_context():
        for candidate in col("candidates").find({}):
            assert col("applications").find_one({"candidate_id": candidate["_id"], "job_id": job["id"]})
