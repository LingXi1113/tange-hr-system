from conftest import login


def test_departments_require_login(client):
    assert client.get("/api/platform/departments").status_code == 401


def test_department_tree(client):
    login(client, "hr-001")
    resp = client.get("/api/platform/departments")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert any(d["dept_id"] == "dept-tech" for d in data)


def test_user_search(client):
    login(client, "hr-001")
    resp = client.get("/api/platform/users", query_string={"keyword": "张"})
    data = resp.get_json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == "张薇"


def test_mongo_initialized_and_writable(app):
    """MongoDB 初始化机制：连接可用、集合可读写、自增 id 生效。"""
    with app.app_context():
        from common.db import get_by_id, insert_doc

        doc = insert_doc("operation_logs", {"biz_type": "t", "action": "a"})
        assert isinstance(doc["_id"], int)
        assert doc["created_at"] is not None
        assert get_by_id("operation_logs", doc["_id"])["biz_type"] == "t"
