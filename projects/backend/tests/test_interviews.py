"""面试管理：绑定校验、时间冲突、状态流转、反馈必填、权限、阶段推进、操作日志。"""
from datetime import datetime, timedelta

from conftest import login
from helpers import assign, ensure_hr, make_candidate, make_job, publish_job

FMT = "%Y-%m-%d %H:%M"


def _setup(client):
    ensure_hr(client)
    # v1.1 流程模板（含 interview_passed，供结论联动推进）
    login(client, "super-admin-001")
    tpl = client.post("/api/pipeline-templates", json={
        "name": "面试用例流程",
        "stages": [
            {"stage_key": "new_resume", "name": "新简历", "sort_order": 1},
            {"stage_key": "pending_interview", "name": "待面试", "sort_order": 2},
            {"stage_key": "interviewing", "name": "面试中", "sort_order": 3},
            {"stage_key": "interview_passed", "name": "面试通过", "sort_order": 4},
        ],
    }).get_json()["data"]["id"]
    login(client, "hr-001")
    job = make_job(client, name="面试职位", template_id=tpl)
    publish_job(client, job["id"])
    cid = make_candidate(client, phone="13611110001", email="iv@example.com")
    app = assign(client, cid, job["id"])
    return job, cid, app


def _slot(offset_hours=24, duration_hours=1):
    start = datetime.now() + timedelta(hours=offset_hours)
    end = start + timedelta(hours=duration_hours)
    return start.strftime(FMT), end.strftime(FMT)


def _create(client, app_id, **overrides):
    start, end = _slot(overrides.pop("offset_hours", 24))
    payload = {
        "application_id": app_id, "round": "一面", "type": "video",
        "start_at": start, "end_at": end,
        "interviewer_name": "刘洋", "meeting_link": "https://meet.example.com/1",
    }
    payload.update(overrides)
    return client.post("/api/interviews", json=payload)


def test_create_interview_binds_real_data(client):
    job, cid, app = _setup(client)
    body = _create(client, app["id"]).get_json()
    assert body["code"] == 0, body
    data = body["data"]
    assert data["candidate_id"] == cid and data["job_id"] == job["id"]
    assert data["candidate_name"] == "测试候选人" and data["status"] == "pending"
    # 缺少应聘记录 / 应聘记录不存在 → 拒绝创建（不允许无关联数据）
    assert client.post("/api/interviews", json={"round": "一面"}).get_json()["code"] == 1001
    r = _create(client, 999999, offset_hours=48)
    assert r.get_json()["code"] == 1001
    # candidate_id 与应聘记录不匹配
    r = _create(client, app["id"], candidate_id=999999, offset_hours=72)
    assert r.get_json()["code"] == 1001


def test_time_rules(client):
    job, cid, app = _setup(client)
    past_start = (datetime.now() - timedelta(hours=2)).strftime(FMT)
    past_end = (datetime.now() - timedelta(hours=1)).strftime(FMT)
    r = _create(client, app["id"], start_at=past_start, end_at=past_end)
    assert r.get_json()["code"] == 1001
    start, _ = _slot()
    r = _create(client, app["id"], start_at=start, end_at=start)
    assert r.get_json()["code"] == 1001


def test_same_candidate_time_conflict(client):
    job, cid, app = _setup(client)
    assert _create(client, app["id"], offset_hours=24).get_json()["code"] == 0
    # 重叠时段 → 1004
    r = _create(client, app["id"], offset_hours=24.5)
    assert r.get_json()["code"] == 1004
    # 不重叠 → OK
    assert _create(client, app["id"], offset_hours=30).get_json()["code"] == 0


def test_status_flow_and_complete_requires_feedback(client):
    job, cid, app = _setup(client)
    iid = _create(client, app["id"]).get_json()["data"]["id"]
    # 待安排不能直接确认
    assert client.post(f"/api/interviews/{iid}/status",
                       json={"action": "confirm"}).get_json()["code"] == 1003
    assert client.post(f"/api/interviews/{iid}/status",
                       json={"action": "invite"}).get_json()["data"]["status"] == "invited"
    assert client.post(f"/api/interviews/{iid}/status",
                       json={"action": "confirm"}).get_json()["data"]["status"] == "confirmed"
    # 完成前必须有反馈
    r = client.post(f"/api/interviews/{iid}/complete", json={})
    assert r.get_json()["code"] == 1001
    # 暂不评价可完成
    assert client.post(f"/api/interviews/{iid}/complete",
                       json={"skip_eval": True}).get_json()["data"]["status"] == "completed"
    # 已完成不可再取消
    assert client.post(f"/api/interviews/{iid}/status",
                       json={"action": "cancel"}).get_json()["code"] == 1003


def test_cancel(client):
    job, cid, app = _setup(client)
    iid = _create(client, app["id"]).get_json()["data"]["id"]
    assert client.post(f"/api/interviews/{iid}/status",
                       json={"action": "cancel"}).get_json()["data"]["status"] == "cancelled"
    assert client.post(f"/api/interviews/{iid}/status",
                       json={"action": "invite"}).get_json()["code"] == 1003
    # 取消后释放时间段：同时间可再建
    assert _create(client, app["id"], offset_hours=24).get_json()["code"] == 0


def test_reschedule_keeps_history(client):
    job, cid, app = _setup(client)
    iid = _create(client, app["id"], offset_hours=24).get_json()["data"]["id"]
    # 原因必填
    start, end = _slot(48)
    r = client.post(f"/api/interviews/{iid}/reschedule",
                    json={"start_at": start, "end_at": end, "reason": ""})
    assert r.get_json()["code"] == 1001
    # 不能改到过去
    past = (datetime.now() - timedelta(hours=1)).strftime(FMT)
    past_end = datetime.now().strftime(FMT)
    r = client.post(f"/api/interviews/{iid}/reschedule",
                    json={"start_at": past, "end_at": past_end, "reason": "x"})
    assert r.get_json()["code"] == 1001
    # 正常改期：状态置为已改期，原记录保留在历史中
    body = client.post(f"/api/interviews/{iid}/reschedule",
                       json={"start_at": start, "end_at": end, "reason": "面试官冲突"}).get_json()
    data = body["data"]
    assert data["status"] == "rescheduled"
    assert data["start_at"] == start
    history = data["reschedule_history"]
    assert len(history) == 1 and history[0]["reason"] == "面试官冲突"
    assert history[0]["to_start"] == start
    # 已改期可再确认
    assert client.post(f"/api/interviews/{iid}/status",
                       json={"action": "confirm"}).get_json()["data"]["status"] == "confirmed"


def test_feedback_validation(client):
    job, cid, app = _setup(client)
    iid = _create(client, app["id"]).get_json()["data"]["id"]
    r = client.post(f"/api/interviews/{iid}/feedback", json={"conclusion": "unknown"})
    assert r.get_json()["code"] == 1001
    r = client.post(f"/api/interviews/{iid}/feedback", json={
        "conclusion": "pass", "dimension_scores": [{"name": "专业能力", "score": 6}],
    })
    assert r.get_json()["code"] == 1001
    body = client.post(f"/api/interviews/{iid}/feedback", json={
        "conclusion": "pass",
        "dimension_scores": [{"name": "专业能力", "score": 4}, {"name": "沟通表达", "score": 5}],
        "comment": "表现优秀", "risk_note": "无", "suggested_salary": "30k",
        "evaluator_name": "刘洋",
    }).get_json()
    assert body["code"] == 0
    assert body["data"]["conclusion"] == "pass"
    # 详情带回反馈
    detail = client.get(f"/api/interviews/{iid}").get_json()["data"]
    assert detail["feedback"]["comment"] == "表现优秀"


def _complete_with_feedback(client, app_id, conclusion, offset_hours=24):
    iid = _create(client, app_id, offset_hours=offset_hours).get_json()["data"]["id"]
    client.post(f"/api/interviews/{iid}/status", json={"action": "invite"})
    client.post(f"/api/interviews/{iid}/status", json={"action": "confirm"})
    assert client.post(f"/api/interviews/{iid}/feedback",
                       json={"conclusion": conclusion,
                             "dimension_scores": [{"name": "专业能力", "score": 4}]}).get_json()["code"] == 0
    assert client.post(f"/api/interviews/{iid}/complete", json={}).get_json()["code"] == 0
    return iid


def test_apply_conclusion_pass_advances_stage(client):
    job, cid, app = _setup(client)
    iid = _complete_with_feedback(client, app["id"], "pass")
    body = client.post(f"/api/interviews/{iid}/apply-conclusion",
                       json={"version": app["version"]}).get_json()
    assert body["code"] == 0, body
    assert body["data"]["action"] == "pass"
    assert body["data"]["application"]["current_stage"] == "interview_passed"
    # version 冲突
    iid2 = _complete_with_feedback(client, app["id"], "pass", offset_hours=48)
    r = client.post(f"/api/interviews/{iid2}/apply-conclusion", json={"version": 999})
    assert r.get_json()["code"] == 1007


def test_apply_conclusion_fail_eliminates(client):
    job, cid, app = _setup(client)
    iid = _complete_with_feedback(client, app["id"], "fail")
    # 淘汰必须填写原因
    r = client.post(f"/api/interviews/{iid}/apply-conclusion", json={"version": app["version"]})
    assert r.get_json()["code"] == 1001
    body = client.post(f"/api/interviews/{iid}/apply-conclusion",
                       json={"version": app["version"], "reason": "专业能力不足"}).get_json()
    assert body["code"] == 0
    assert body["data"]["action"] == "fail"
    assert body["data"]["application"]["status"] == "eliminated"


def test_apply_conclusion_hold_and_skip(client):
    job, cid, app = _setup(client)
    iid = _complete_with_feedback(client, app["id"], "hold")
    assert client.post(f"/api/interviews/{iid}/apply-conclusion",
                       json={"version": app["version"]}).get_json()["code"] == 1003
    # 暂不评价的面试不能应用结论
    iid2 = _create(client, app["id"], offset_hours=72).get_json()["data"]["id"]
    client.post(f"/api/interviews/{iid2}/status", json={"action": "invite"})
    client.post(f"/api/interviews/{iid2}/status", json={"action": "confirm"})
    client.post(f"/api/interviews/{iid2}/complete", json={"skip_eval": True})
    assert client.post(f"/api/interviews/{iid2}/apply-conclusion",
                       json={"version": app["version"]}).get_json()["code"] == 1003


def test_configured_interview_rounds_advance_one_by_one(client):
    """配置多轮面试时，只有最后一轮通过才进入面试通过。"""
    job, cid, app = _setup(client)
    assert client.put(f"/api/jobs/{job['id']}", json={
        "interview_rounds": ["一面", "二面", "三面"],
    }).get_json()["code"] == 0
    moved = client.post(f"/api/applications/{app['id']}/move", json={
        "to_stage": "pending_interview", "reason": "进入面试阶段", "version": app["version"],
    }).get_json()["data"]

    def complete_pass(round_name, version, offset):
        iid = _create(client, app["id"], round=round_name, offset_hours=offset).get_json()["data"]["id"]
        client.post(f"/api/interviews/{iid}/status", json={"action": "invite"})
        client.post(f"/api/interviews/{iid}/status", json={"action": "confirm"})
        client.post(f"/api/interviews/{iid}/feedback", json={
            "conclusion": "pass", "dimension_scores": [{"name": "专业能力", "score": 4}],
        })
        client.post(f"/api/interviews/{iid}/complete", json={})
        return client.post(f"/api/interviews/{iid}/apply-conclusion", json={"version": version}).get_json()

    first = complete_pass("一面", moved["version"], 24)
    assert first["code"] == 0
    assert first["data"]["application"]["current_stage"] == "interviewing"
    assert first["data"]["application"]["interview_round"] == "二面"

    second = complete_pass("二面", first["data"]["application"]["version"], 48)
    assert second["code"] == 0
    assert second["data"]["application"]["interview_round"] == "三面"

    third = complete_pass("三面", second["data"]["application"]["version"], 72)
    assert third["code"] == 0
    assert third["data"]["application"]["current_stage"] == "interview_passed"


def test_permissions_non_hr(client):
    job, cid, app = _setup(client)
    login(client, "screen-001")
    start, end = _slot()
    r = client.post("/api/interviews", json={
        "application_id": app["id"], "round": "一面", "type": "video",
        "start_at": start, "end_at": end,
    })
    assert r.get_json()["code"] == 1006
    # 列表可读
    assert client.get("/api/interviews").get_json()["code"] == 0


def test_operation_logs_written(client, app):
    job, cid, app_doc = _setup(client)
    iid = _create(client, app_doc["id"]).get_json()["data"]["id"]
    client.post(f"/api/interviews/{iid}/status", json={"action": "cancel"})
    with app.app_context():
        from common.db import col

        logs = list(col("operation_logs").find({"biz_type": "interview", "biz_id": str(iid)}))
    actions = {l["action"] for l in logs}
    assert "create" in actions and "cancel" in actions
    assert all(l["operator_name"] for l in logs)


def test_list_filters(client):
    job, cid, app = _setup(client)
    iid = _create(client, app["id"]).get_json()["data"]["id"]
    _create(client, app["id"], offset_hours=48, round="二面")
    assert client.get("/api/interviews",
                      query_string={"candidate_id": cid}).get_json()["data"]["total"] == 2
    assert client.get("/api/interviews",
                      query_string={"round": "二面"}).get_json()["data"]["total"] == 1
    assert client.get("/api/interviews",
                      query_string={"status": "pending", "job_id": job["id"]}
                      ).get_json()["data"]["total"] == 2
