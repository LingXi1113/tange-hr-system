"""埋点兼容端点与生产环境开关测试。"""
import importlib


def test_env_stub(client):
    resp = client.get("/env")
    assert resp.status_code == 200
    assert resp.get_json()["env_name"] == "dev"


def test_tracking_batch_stub(client):
    resp = client.post("/api/v1/events/batch", json={"events": []})
    assert resp.status_code == 200
    assert resp.get_json()["code"] == 0


def test_tracking_schema_stub(client):
    resp = client.post("/api/v1/tenants/t1/projects/p1/tracking-schema", json={})
    assert resp.status_code == 200
    assert resp.get_json()["code"] == 0


def test_production_disables_mock_and_seed(monkeypatch):
    """HRATS_ENV=production：Mock 登录与演示数据默认关闭。"""
    monkeypatch.setenv("HRATS_ENV", "production")
    import config as cfg_mod

    importlib.reload(cfg_mod)
    try:
        from app import create_app

        class ProdTestConfig(cfg_mod.Config):
            MONGODB_DATABASE = "hr_ats_prod_test"
            TESTING = True  # 测试模式跳过生产启动阻断，仅验证生产默认开关

        app = create_app(ProdTestConfig)
        client = app.test_client()

        resp = client.post("/api/auth/mock-login", json={"user_id": "hr-001"})
        assert resp.status_code == 200
        assert resp.get_json()["code"] == 1006  # FORBIDDEN

        data = client.get("/api/auth/mock-users").get_json()["data"]
        assert data["enabled"] is False

        with app.app_context():
            from common.mongo import get_db

            db = get_db(app)
            assert db["operation_logs"].count_documents({}) == 0  # 未写演示数据
            db.client.drop_database("hr_ats_prod_test")
    finally:
        monkeypatch.delenv("HRATS_ENV", raising=False)
        importlib.reload(cfg_mod)
