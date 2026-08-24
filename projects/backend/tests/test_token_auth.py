"""登录态 Token 化回归测试。

背景：系统作为即先平台内嵌应用运行在第三方 iframe 中，浏览器会拦截第三方
Cookie，导致 Flask session 登录后下一次请求即丢失（现象：登录后任何受保护
页面被踢回登录页）。修复：登录/切换用户签发 Token，前端经 X-Auth-Token
请求头携带，后端优先按 Token 鉴权（兼容 session）。
"""
from conftest import login


def test_login_returns_token_usable_without_cookie(client):
    """RED→GREEN：mock-login 返回 token；新会话不带 cookie 仅凭 X-Auth-Token 可访问受保护接口。"""
    data = login(client, "hr-001")
    token = data.get("token")
    assert token, "mock-login 响应必须返回 token"

    # 全新 client：无 cookie，仅靠 token 头
    fresh = client.application.test_client()
    resp = fresh.get("/api/auth/me", headers={"X-Auth-Token": token})
    assert resp.status_code == 200, "仅凭 X-Auth-Token 应能通过登录态校验"
    me = resp.get_json()["data"]
    assert me["user_id"] == "hr-001"
    assert me["role"] == "hr"


def test_switch_user_issues_new_token(client):
    data = login(client, "hr-001")
    resp = client.post(
        "/api/auth/switch-user", json={"user_id": "ssc-001"},
        headers={"X-Auth-Token": data["token"]},
    )
    body = resp.get_json()
    assert body["code"] == 0
    new_token = body["data"].get("token")
    assert new_token and new_token != data["token"]

    fresh = client.application.test_client()
    me = fresh.get("/api/auth/me", headers={"X-Auth-Token": new_token}).get_json()["data"]
    assert me["user_id"] == "ssc-001"


def test_invalid_token_rejected(client):
    resp = client.get("/api/auth/me", headers={"X-Auth-Token": "forged-token"})
    assert resp.status_code == 401


def test_session_login_still_works(client):
    """兼容保留：cookie session 登录方式仍可用。"""
    login(client, "hr-001")
    assert client.get("/api/auth/me").status_code == 200
