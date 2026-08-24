from conftest import login


def test_mock_users_listed_without_login(client):
    resp = client.get("/api/auth/mock-users")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["enabled"] is True
    assert len(data["users"]) >= 8
    assert {"user_id", "name", "role", "role_name"} <= set(data["users"][0])


def test_me_requires_login(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.get_json()["code"] == 401


def test_mock_login_and_me(client):
    login(client, "hr-001")
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["user_id"] == "hr-001"
    assert data["name"] == "张薇"
    assert data["role"] == "hr"
    assert data["mock_mode"] is True
    # 开发环境返回可切换用户列表（角色切换器数据源）
    assert len(data["switchable_users"]) >= 8


def test_mock_login_invalid_user(client):
    resp = client.post("/api/auth/mock-login", json={"user_id": "no-such-user"})
    assert resp.status_code == 200
    assert resp.get_json()["code"] == 1001


def test_switch_user_changes_role(client):
    login(client, "hr-001")
    resp = client.post("/api/auth/switch-user", json={"user_id": "ssc-001"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["role"] == "ssc"
    me = client.get("/api/auth/me").get_json()["data"]
    assert me["user_id"] == "ssc-001"


def test_logout(client):
    login(client, "hr-001")
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_all_eight_roles_exist(client):
    login(client, "hr-001")
    data = client.get("/api/auth/me").get_json()["data"]
    roles = {u["role"] for u in data["switchable_users"]}
    assert {
        "hr", "business_screener", "interviewer", "org_approver",
        "gm", "chairman", "offer_sender", "ssc",
    } <= roles
