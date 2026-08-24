"""个人信息访问、文件授权与候选人彻底删除。"""
import io

from conftest import login
from helpers import assign, ensure_hr, make_candidate, make_job, publish_job

from common.db import col


def test_non_hr_cannot_disable_candidate_mask_or_export(client):
    ensure_hr(client)
    cid = make_candidate(client, phone="13988889999", email="privacy@example.com")

    login(client, "screen-001")
    row = client.get("/api/candidates", query_string={
        "keyword": "13988889999", "mask": "0",
    }).get_json()["data"]["list"][0]
    assert row["phone"] == "139****9999"
    assert row["email"] == "pr***@example.com"

    detail = client.get(f"/api/candidates/{cid}", query_string={"mask": "0"}).get_json()["data"]
    assert detail["phone"] == "139****9999"
    assert detail["email"] == "pr***@example.com"
    assert client.get("/api/candidates/export").get_json()["code"] == 1006
    assert client.get("/api/reports/funnel").get_json()["code"] == 1006
    assert client.get("/api/talent-pool/export").get_json()["code"] == 1006


def test_resume_access_is_role_scoped_and_logged(client):
    ensure_hr(client)
    cid = make_candidate(client, phone="13988880001", email="resume-security@example.com")
    uploaded = client.post("/api/resume/upload", data={
        "candidate_id": str(cid),
        "file": (io.BytesIO(b"resume-data"), "resume.pdf"),
    }, content_type="multipart/form-data").get_json()["data"]

    login(client, "screen-001")
    assert client.get(f"/api/attachments/{uploaded['attachment_id']}").status_code == 200
    assert client.get(f"/api/files/{uploaded['file_id']}").get_json()["code"] == 1006

    login(client, "ssc-001")
    assert client.get(f"/api/attachments/{uploaded['attachment_id']}").get_json()["code"] == 1006

    with client.application.app_context():
        log = col("operation_logs").find_one({
            "biz_type": "attachment", "action": "download",
            "biz_id": str(uploaded["attachment_id"]),
        })
        assert log is not None


def test_delete_candidate_cascades_all_personal_data(client):
    ensure_hr(client)
    job = make_job(client, name="隐私删除测试职位")
    publish_job(client, job["id"])
    cid = make_candidate(client, phone="13988880002", email="cascade@example.com")
    app = assign(client, cid, job["id"])

    with client.application.app_context():
        interview = {"_id": 8101, "candidate_id": cid, "application_id": app["id"]}
        offer = {"_id": 8102, "candidate_id": cid, "application_id": app["id"]}
        onboarding = {"_id": 8103, "candidate_id": cid, "application_id": app["id"]}
        col("interviews").insert_one(interview)
        col("interview_feedback").insert_one({"_id": 8104, "interview_id": 8101})
        col("offers").insert_one(offer)
        col("offer_approvals").insert_one({"_id": 8105, "offer_id": 8102})
        col("onboarding_records").insert_one(onboarding)
        col("talent_pool").insert_one({"_id": 8106, "candidate_id": cid})
        col("notifications").insert_one({"_id": 8107, "receiver_id": "hr-001",
                                           "biz_type": "candidate", "biz_id": str(cid)})
        col("operation_logs").insert_one({"_id": 8108, "biz_type": "candidate",
                                           "biz_id": str(cid), "detail": "候选人姓名"})

    result = client.delete(f"/api/candidates/{cid}?confirm=1").get_json()
    assert result["code"] == 0
    assert result["data"]["applications"] == 1
    assert result["data"]["interviews"] == 1

    with client.application.app_context():
        assert col("candidates").find_one({"_id": cid}) is None
        assert col("applications").find_one({"_id": app["id"]}) is None
        assert col("interviews").find_one({"_id": 8101}) is None
        assert col("interview_feedback").find_one({"_id": 8104}) is None
        assert col("offers").find_one({"_id": 8102}) is None
        assert col("offer_approvals").find_one({"_id": 8105}) is None
        assert col("onboarding_records").find_one({"_id": 8103}) is None
        assert col("talent_pool").find_one({"_id": 8106}) is None
        assert col("notifications").find_one({"_id": 8107}) is None
        assert col("operation_logs").find_one({"_id": 8108}) is None
        deletion_log = col("operation_logs").find_one({
            "biz_type": "candidate", "action": "delete", "biz_id": str(cid),
        })
        assert deletion_log is not None
        assert "cascade=" not in deletion_log.get("detail", "")


def test_non_hr_cannot_use_generic_file_upload(client):
    login(client, "screen-001")
    response = client.post("/api/files/upload", data={
        "file": (io.BytesIO(b"private"), "private.txt"),
        "biz_type": "general",
    }, content_type="multipart/form-data")
    assert response.get_json()["code"] == 1006
