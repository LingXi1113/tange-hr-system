import pytest

from app import create_app
from config import TestConfig


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    # 每个用例使用干净的 MongoDB 测试库
    with app.app_context():
        from common.mongo import get_db

        client = get_db(app).client
        client.drop_database(app.config["MONGODB_DATABASE"])
    yield app
    with app.app_context():
        from common.mongo import get_db

        get_db(app).client.drop_database(app.config["MONGODB_DATABASE"])


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, user_id: str = "hr-001"):
    resp = client.post("/api/auth/mock-login", json={"user_id": user_id})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == 0
    return resp.get_json()["data"]
