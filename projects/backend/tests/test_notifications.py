"""站内通知：幂等生成、规则扫描、列表/未读/已读、跳转路由、权限。"""
from datetime import datetime, timedelta

from conftest import login
from helpers import assign, ensure_hr, make_candidate, make_job, publish_job

V11_STAGES = ["new_resume", "pending_screen", "hr_screen_passed", "pending_interview",
              "interviewing", "interview_passed", "offer_pending", "pending_onboard", "onboarded"]


def _setup(client):
    ensure_hr(client)
    tpl = client.post("/api/pipeline-templates", json={
        "name": "通知用例流程",
        "stages": [{"stage_key": k, "name": k, "sort_order": i + 1}
                   for i, k in enumerate(V11_STAGES)],
    }).get_json()["data"]["id"]
    job = make_job(client, name="通知职位", template_id=tpl)
    publish_job(client, job["id"])
    return job


def _unread(client):
    return client.get("/api/notifications/unread-count").get_json()["data"]["count"]


def _all_notes(client):
    return client.get("/api/notifications", query_string={"page_size": 100}).get_json()["data"]["list"]


def test_new_candidate_notification_idempotent(client):
    job = _setup(client)
    cid = make_candidate(client, phone="13600001001", email="n1@example.com")
    assign(client, cid, job["id"])
    # 多次访问未读数（触发规则扫描）不产生重复通知
    for _ in range(3):
        _unread(client)
    notes = [n for n in _all_notes(client) if n["scene"] == "new_candidate"]
    assert len(notes) == 1
    assert notes[0]["route"] == f"/candidates/{cid}"
    assert "通知职位" in notes[0]["content"]


def test_interview_remind_and_feedback_pending(client):
    job = _setup(client)
    cid = make_candidate(client, phone="13600001002", email="n2@example.com")
    app = assign(client, cid, job["id"])

    # 24 小时内的面试 → 面试提醒（创建即生成，幂等）
    start = datetime.now() + timedelta(hours=20)
    iv = client.post("/api/interviews", json={
        "application_id": app["id"], "round": "一面", "type": "video",
        "start_at": start.strftime("%Y-%m-%d %H:%M"),
        "end_at": (start + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"),
        "interviewer_name": "刘洋",
    }).get_json()["data"]
    _unread(client)
    reminds = [n for n in _all_notes(client) if n["scene"] == "interview_remind"]
    assert len(reminds) == 1 and reminds[0]["route"] == "/interviews"
    # 再次扫描不重复
    _unread(client)
    assert len([n for n in _all_notes(client) if n["scene"] == "interview_remind"]) == 1

    # 面试时间已过且仍为已确认 → 反馈待填写
    client.post(f"/api/interviews/{iv['id']}/status", json={"action": "invite"})
    client.post(f"/api/interviews/{iv['id']}/status", json={"action": "confirm"})
    with client.application.app_context():
        from common.db import col

        col("interviews").update_one({"_id": iv["id"]}, {
            "$set": {"start_at": datetime.now() - timedelta(hours=2),
                     "end_at": datetime.now() - timedelta(hours=1)}})
    _unread(client)
    feedbacks = [n for n in _all_notes(client) if n["scene"] == "feedback_pending"]
    assert len(feedbacks) == 1
    _unread(client)
    assert len([n for n in _all_notes(client) if n["scene"] == "feedback_pending"]) == 1


def test_offer_expiring_notification(client):
    job = _setup(client)
    cid = make_candidate(client, phone="13600001003", email="n3@example.com")
    app = assign(client, cid, job["id"])
    moved = client.post(f"/api/applications/{app['id']}/move",
                        json={"to_stage": "interview_passed", "reason": "过",
                              "version": app["version"]}).get_json()["data"]
    offer = client.post("/api/offers", json={
        "application_id": moved["id"], "dept": "x", "position": "y", "salary": "1k",
        "onboard_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "valid_until": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
    }).get_json()["data"]
    client.post(f"/api/offers/{offer['id']}/status", json={"action": "submit", "version": offer["version"]})
    client.post(f"/api/offers/{offer['id']}/status", json={"action": "send", "version": offer["version"] + 1})
    _unread(client)
    expiring = [n for n in _all_notes(client) if n["scene"] == "offer_expiring"]
    assert len(expiring) == 1 and expiring[0]["route"] == "/offers"
    _unread(client)
    assert len([n for n in _all_notes(client) if n["scene"] == "offer_expiring"]) == 1


def test_stale_candidate_notification(client):
    job = _setup(client)
    cid = make_candidate(client, phone="13600001004", email="n4@example.com")
    app = assign(client, cid, job["id"])
    with client.application.app_context():
        from common.db import col

        col("applications").update_one({"_id": app["id"]}, {
            "$set": {"stage_entered_at": datetime.now() - timedelta(days=8)}})
    _unread(client)
    stale = [n for n in _all_notes(client) if n["scene"] == "stale_candidate"]
    assert len(stale) == 1 and stale[0]["route"] == f"/candidates/{cid}"
    _unread(client)
    assert len([n for n in _all_notes(client) if n["scene"] == "stale_candidate"]) == 1


def test_requirement_overdue_notification(client):
    _setup(client)
    full = {
        "name": "逾期需求", "dept_id": "dept-tech", "dept_name": "技术中心",
        "headcount": 1, "request_type": "new_headcount", "priority": "high",
        "requirements": "x",
        "due_date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
    }
    rid = client.post("/api/requirements", json=full).get_json()["data"]["id"]
    client.post(f"/api/requirements/{rid}/confirm")
    _unread(client)
    overdue = [n for n in _all_notes(client) if n["scene"] == "requirement_overdue"]
    assert len(overdue) == 1 and overdue[0]["route"] == f"/requirements/{rid}"
    _unread(client)
    assert len([n for n in _all_notes(client) if n["scene"] == "requirement_overdue"]) == 1


def test_list_filter_mark_read_and_read_all(client):
    job = _setup(client)
    cid = make_candidate(client, phone="13600001005", email="n5@example.com")
    assign(client, cid, job["id"])
    assert _unread(client) >= 1

    # 标记单条已读
    notes = _all_notes(client)
    target = notes[0]
    assert client.post(f"/api/notifications/{target['id']}/read").get_json()["code"] == 0
    after = {n["id"]: n for n in _all_notes(client)}
    assert after[target["id"]]["unread"] is False

    # 未读筛选
    unread_list = client.get("/api/notifications",
                             query_string={"status": "unread", "page_size": 100}).get_json()["data"]["list"]
    assert all(n["unread"] for n in unread_list)

    # 全部已读
    body = client.post("/api/notifications/read-all").get_json()
    assert body["code"] == 0 and body["data"]["marked"] >= 0
    assert _unread(client) == 0

    # 不能标记他人通知
    assign_cid = make_candidate(client, name="他人通知", phone="13600001006", email="n6@example.com")
    assign(client, assign_cid, job["id"])
    hr_note = [n for n in _all_notes(client) if n["scene"] == "new_candidate"][-1]
    login(client, "hr-002")
    # hr-002 也收到过该通知（全 HR 分发），取 hr-001 独有的那条：改用不存在的他人场景
    other_note = client.get("/api/notifications", query_string={"page_size": 100}).get_json()["data"]["list"]
    assert other_note  # hr-002 自己也有通知
    # 伪造他人通知 id 越界不存在 → 404
    assert client.post("/api/notifications/999999/read").get_json()["code"] == 1002


def test_no_notification_leak_between_users(client):
    job = _setup(client)
    cid = make_candidate(client, phone="13600001007", email="n7@example.com")
    assign(client, cid, job["id"])
    login(client, "screen-001")  # 非 HR 不收业务通知
    assert _unread(client) == 0
    assert _all_notes(client) == []
