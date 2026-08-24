"""招聘流程看板：卡片粒度、流转、乐观锁、锁定计时。"""
from conftest import login
from helpers import assign, ensure_hr, make_candidate, make_job, make_template, publish_job


def _setup(client):
    ensure_hr(client)
    tpl = make_template(client)
    job = make_job(client, name="看板职位", template_id=tpl)
    publish_job(client, job["id"])
    cid = make_candidate(client, phone="13888889999", email="board@example.com")
    app = assign(client, cid, job["id"])
    return job, cid, app


def test_board_columns_and_cards(client):
    job, cid, app = _setup(client)
    data = client.get("/api/pipeline/board", query_string={"job_id": job["id"]}).get_json()["data"]
    keys = [c["stage_key"] for c in data["columns"]]
    assert keys[:3] == ["new_resume", "business_screen", "interview_1"]
    assert "eliminated" in keys and "talent_pool" in keys
    cards = data["cards"]
    assert len(cards) == 1
    assert cards[0]["candidate_name"] == "测试候选人"
    assert cards[0]["lock"]  # new_resume 锁定2天，显示锁定信息


def test_move_requires_reason_and_version(client):
    job, cid, app = _setup(client)
    # 缺原因
    resp = client.post(f"/api/applications/{app['id']}/move",
                       json={"to_stage": "business_screen", "version": app["version"]})
    assert resp.get_json()["code"] == 1001
    # 版本错误（乐观锁）
    resp = client.post(f"/api/applications/{app['id']}/move",
                       json={"to_stage": "business_screen", "reason": "推进", "version": 999})
    assert resp.get_json()["code"] == 1007
    # 非法阶段
    resp = client.post(f"/api/applications/{app['id']}/move",
                       json={"to_stage": "not_exist", "reason": "推进", "version": app["version"]})
    assert resp.get_json()["code"] == 1001


def test_move_writes_transition_and_releases_lock(client):
    job, cid, app = _setup(client)
    resp = client.post(f"/api/applications/{app['id']}/move",
                       json={"to_stage": "business_screen", "reason": "初筛通过", "version": app["version"]})
    body = resp.get_json()
    assert body["code"] == 0
    assert body["data"]["current_stage"] == "business_screen"
    assert body["data"]["version"] == app["version"] + 1

    # 流转记录（报表依据）
    trans = client.get(f"/api/applications/{app['id']}/transitions").get_json()["data"]
    assert [(t["from_stage"], t["to_stage"]) for t in trans] == [
        ("", "new_resume"), ("new_resume", "business_screen"),
    ]
    assert trans[-1]["reason"] == "初筛通过"

    # 离开 new_resume 后锁定结束（business_screen 锁定0天）→ 可分配其他职位
    tpl2 = client.get("/api/pipeline-templates").get_json()["data"]["list"][0]["id"]
    job2 = make_job(client, name="另一职位", template_id=tpl2)
    publish_job(client, job2["id"])
    resp = client.post(f"/api/candidates/{cid}/applications", json={"job_id": job2["id"]})
    assert resp.get_json()["code"] == 0, "离开锁定阶段后应可分配其他职位"


def test_eliminate_requires_reason(client):
    job, cid, app = _setup(client)
    resp = client.post(f"/api/applications/{app['id']}/eliminate", json={"reason": ""})
    assert resp.get_json()["code"] == 1001
    resp = client.post(f"/api/applications/{app['id']}/eliminate", json={"reason": "能力不匹配"})
    assert resp.get_json()["data"]["status"] == "eliminated"
    # 看板淘汰列可见
    data = client.get("/api/pipeline/board", query_string={"job_id": job["id"]}).get_json()["data"]
    eliminated = [c for c in data["cards"] if c["current_stage"] == "eliminated"]
    assert len(eliminated) == 1
