from datetime import datetime, timedelta

from common.stage_rules import process_expired_stage_rules
from conftest import login
from helpers import assign, ensure_hr, make_candidate, make_job, publish_job


def test_stage_rule_configuration_round_trip(client):
    ensure_hr(client)
    login(client, "super-admin-001")
    response = client.post("/api/pipeline-templates", json={
        "name": "客保规则模板",
        "stage_rules_enabled": True,
        "stages": [{
            "stage_key": "pending_onboard", "name": "待入职", "sort_order": 1,
            "lock_days": 45, "unprocessed_days": 90,
            "expiry_action": "abandoned", "deadline_basis": "planned_onboard_date",
            "reminder_days_before": 3, "skippable": False, "requires_interview": False, "requires_feedback": False,
            "auto_reminder": True, "enter_talent_pool": True,
        }],
    })
    body = response.get_json()
    assert body["code"] == 0
    stage = body["data"]["stages"][0]
    assert stage["lock_days"] == 45
    assert stage["unprocessed_days"] == 90
    assert stage["expiry_action"] == "abandoned"
    assert stage["deadline_basis"] == "planned_onboard_date"
    assert stage["reminder_days_before"] == 3
    assert stage["enter_talent_pool"] is True


def test_stage_rule_blocks_skipping_non_skippable_stage(client):
    ensure_hr(client)
    login(client, "super-admin-001")
    tpl = client.post("/api/pipeline-templates", json={
        "name": "顺序规则模板", "stage_rules_enabled": True,
        "stages": [
            {"stage_key": "new_resume", "name": "未处理", "sort_order": 1},
            {"stage_key": "interview_1", "name": "一面", "sort_order": 2, "skippable": False},
            {"stage_key": "interview_2", "name": "二面", "sort_order": 3},
        ],
    }).get_json()["data"]["id"]
    login(client, "hr-001")
    job = make_job(client, name="顺序校验职位", template_id=tpl)
    publish_job(client, job["id"])
    app = assign(client, make_candidate(client, phone="13600001001", email="rule-order@example.com"), job["id"])
    response = client.post(f"/api/applications/{app['id']}/move", json={
        "to_stage": "interview_2", "reason": "测试跳过", "version": app["version"],
    })
    assert response.get_json()["code"] == 1003


def test_expired_stage_rule_moves_to_talent_pool(client):
    ensure_hr(client)
    login(client, "super-admin-001")
    tpl = client.post("/api/pipeline-templates", json={
        "name": "到期规则模板", "stage_rules_enabled": True,
        "stages": [{
            "stage_key": "new_resume", "name": "未处理", "sort_order": 1,
            "unprocessed_days": 1, "expiry_action": "talent_pool", "auto_reminder": False,
        }],
    }).get_json()["data"]["id"]
    login(client, "hr-001")
    job = make_job(client, name="到期规则职位", template_id=tpl)
    publish_job(client, job["id"])
    cid = make_candidate(client, phone="13600001002", email="rule-expire@example.com")
    app = assign(client, cid, job["id"])
    with client.application.app_context():
        from common.db import col

        col("applications").update_one(
            {"_id": app["id"]},
            {"$set": {"stage_entered_at": datetime.now() - timedelta(days=2)}},
        )
        assert process_expired_stage_rules() == 1
        updated = col("applications").find_one({"_id": app["id"]})
        assert updated["current_stage"] == "talent_pool"
        assert col("talent_pool").find_one({"candidate_id": cid}) is not None


def test_stage_rule_sends_reminder_before_deadline(client):
    ensure_hr(client)
    login(client, "super-admin-001")
    tpl = client.post("/api/pipeline-templates", json={
        "name": "提前提醒规则模板", "stage_rules_enabled": True,
        "stages": [{
            "stage_key": "new_resume", "name": "未处理", "sort_order": 1,
            "unprocessed_days": 5, "reminder_days_before": 2,
            "expiry_action": "none", "auto_reminder": True,
        }],
    }).get_json()["data"]["id"]
    login(client, "hr-001")
    job = make_job(client, name="提前提醒职位", template_id=tpl)
    publish_job(client, job["id"])
    cid = make_candidate(client, phone="13600001003", email="rule-remind@example.com")
    app = assign(client, cid, job["id"])
    with client.application.app_context():
        from common.db import col

        col("applications").update_one(
            {"_id": app["id"]},
            {"$set": {"stage_entered_at": datetime.now() - timedelta(days=4)}},
        )
        assert process_expired_stage_rules() == 0
        assert col("notifications").find_one({"scene": "stage_rule_remind"}) is not None
