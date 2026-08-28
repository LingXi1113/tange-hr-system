from datetime import datetime, timedelta

import common.stage_rules as stage_rules
from common.background_failures import record_background_failure, resolve_background_failure
from common.resume_parser import parse_resume_file
from conftest import login
from helpers import assign, ensure_hr, make_candidate, make_job, publish_job


def test_background_failure_can_be_recorded_and_resolved(client):
    with client.application.app_context():
        assert record_background_failure("test_operation", 1001, RuntimeError("temporary"))
        from common.db import col

        pending = col("background_failures").find_one({
            "failure_key": "test_operation:1001", "status": "pending",
        })
        assert pending is not None
        assert pending["retry_count"] == 1

        resolve_background_failure("test_operation", 1001)
        resolved = col("background_failures").find_one({"_id": pending["_id"]})
        assert resolved["status"] == "resolved"


def test_stage_rule_failure_is_recorded_and_resolved_after_retry(client, monkeypatch):
    ensure_hr(client)
    login(client, "super-admin-001")
    tpl = client.post("/api/pipeline-templates", json={
        "name": "异常留痕模板", "stage_rules_enabled": True,
        "stages": [{
            "stage_key": "new_resume", "name": "未处理", "sort_order": 1,
            "unprocessed_days": 1, "expiry_action": "talent_pool", "auto_reminder": False,
        }],
    }).get_json()["data"]["id"]
    login(client, "hr-001")
    job = make_job(client, name="异常留痕职位", template_id=tpl)
    publish_job(client, job["id"])
    cid = make_candidate(client, phone="13600001999", email="failure-record@example.com")
    application = assign(client, cid, job["id"])

    with client.application.app_context():
        from common.db import col

        col("applications").update_one(
            {"_id": application["id"]},
            {"$set": {"stage_entered_at": datetime.now() - timedelta(days=2)}},
        )
        original_move = stage_rules.move_application

        def fail_once(*args, **kwargs):
            raise RuntimeError("simulated stage action failure")

        monkeypatch.setattr(stage_rules, "move_application", fail_once)
        assert stage_rules.process_expired_stage_rules() == 0
        failure = col("background_failures").find_one({
            "failure_key": f"stage_rule_expire:{application['id']}",
            "status": "pending",
        })
        assert failure is not None

        monkeypatch.setattr(stage_rules, "move_application", original_move)
        assert stage_rules.process_expired_stage_rules() == 1
        failure = col("background_failures").find_one({"_id": failure["_id"]})
        assert failure["status"] == "resolved"


def test_resume_parser_logs_exception_and_returns_manual_status(monkeypatch, caplog):
    def fail_extract(_file_path):
        raise RuntimeError("invalid resume document")

    monkeypatch.setattr("common.resume_parser._extract_docx", fail_extract)
    with caplog.at_level("ERROR", logger="common.resume_parser"):
        fields, status = parse_resume_file("broken.docx")

    assert status == "failed"
    assert fields == {
        "name": "", "phone": "", "email": "", "city": "",
        "gender": "", "education": [], "work_experience": [],
    }
    assert "简历文本提取失败" in caplog.text
