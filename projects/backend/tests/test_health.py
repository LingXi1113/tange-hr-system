def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ok"
    assert body["data"]["platform_provider"] == "mock"


def test_unknown_api_returns_json_error(client):
    resp = client.get("/api/not-exists")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == 1002
