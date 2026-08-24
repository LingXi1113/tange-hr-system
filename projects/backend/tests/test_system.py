"""系统设置：参数、字典、Offer 审批人。"""
from conftest import login


def test_params_defaults_available(client):
    login(client, "hr-001")
    data = client.get("/api/system/params").get_json()["data"]
    assert "lock_days_default" in data
    assert data["lock_days_default"]["business_screen"] == 3
    assert "onboarding_checklist_default" in data
    assert "离职证明" in data["onboarding_checklist_default"]


def test_update_params_and_lock_source(client):
    login(client, "hr-001")
    resp = client.put("/api/system/params", json={
        "items": [{"key": "lock_days_default", "value": {"business_screen": 9}}],
    })
    assert resp.get_json()["code"] == 0
    data = client.get("/api/system/params").get_json()["data"]
    assert data["lock_days_default"]["business_screen"] == 9


def test_update_params_requires_hr(client):
    login(client, "interviewer-001")
    resp = client.put("/api/system/params", json={"items": [{"key": "lock_days_default", "value": {}}]})
    assert resp.get_json()["code"] == 1006


def test_update_params_invalid_value(client):
    login(client, "hr-001")
    resp = client.put("/api/system/params", json={
        "items": [{"key": "lock_days_default", "value": {"a": -1}}],
    })
    assert resp.get_json()["code"] == 1001
    resp = client.put("/api/system/params", json={"items": [{"key": "unknown_key", "value": 1}]})
    assert resp.get_json()["code"] == 1001


def test_dict_crud(client):
    login(client, "hr-001")
    created = client.post("/api/system/dicts", json={
        "type": "source_channel", "code": "website", "name": "官网投递",
    }).get_json()["data"]
    assert created["id"]
    # 重复编码
    dup = client.post("/api/system/dicts", json={
        "type": "source_channel", "code": "website", "name": "重复",
    })
    assert dup.get_json()["code"] == 1004
    # 停用
    resp = client.put(f"/api/system/dicts/{created['id']}", json={"enabled": False})
    assert resp.get_json()["data"]["enabled"] is False
    # 按类型过滤
    items = client.get("/api/system/dicts", query_string={"type": "source_channel"}).get_json()["data"]
    assert all(i["type"] == "source_channel" for i in items)
    # 非法类型
    bad = client.post("/api/system/dicts", json={"type": "nope", "code": "x", "name": "x"})
    assert bad.get_json()["code"] == 1001


def test_offer_approvers(client):
    login(client, "hr-001")
    resp = client.put("/api/system/offer-approvers", json={
        "org_approver_id": "org-001", "gm_id": "gm-001",
        "chairman_id": "chairman-001", "offer_sender_id": "offer-001",
    })
    data = resp.get_json()["data"]
    assert resp.get_json()["code"] == 0
    assert data["org_approver"] == {"user_id": "org-001", "name": "陈静"}
    assert data["offer_sender"]["name"] == "周婷"

    # 重新读取
    got = client.get("/api/system/offer-approvers").get_json()["data"]
    assert got["gm"]["user_id"] == "gm-001"

    # 用户不存在
    bad = client.put("/api/system/offer-approvers", json={
        "org_approver_id": "no-such", "gm_id": "gm-001",
        "chairman_id": "chairman-001", "offer_sender_id": "offer-001",
    })
    assert bad.get_json()["code"] == 1001

    # 缺字段
    bad2 = client.put("/api/system/offer-approvers", json={"org_approver_id": "org-001"})
    assert bad2.get_json()["code"] == 1001

    # 非 HR 不可修改
    login(client, "ssc-001")
    resp = client.put("/api/system/offer-approvers", json={
        "org_approver_id": "org-001", "gm_id": "gm-001",
        "chairman_id": "chairman-001", "offer_sender_id": "offer-001",
    })
    assert resp.get_json()["code"] == 1006
