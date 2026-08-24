"""招聘需求管理。"""
from conftest import login

FULL = {
    "name": "后端工程师招聘需求", "dept_id": "dept-tech", "dept_name": "技术中心",
    "headcount": 3, "request_type": "new_headcount", "priority": "high",
    "due_date": "2026-10-01", "requirements": "5年以上Java经验",
}


def test_create_draft_allows_missing_fields(client):
    login(client, "hr-001")
    resp = client.post("/api/requirements", json={"name": "草稿需求", "save_as_draft": True})
    body = resp.get_json()
    assert body["code"] == 0
    assert body["data"]["status"] == "draft"


def test_submit_requires_all_fields(client):
    login(client, "hr-001")
    resp = client.post("/api/requirements", json={"name": "缺字段需求"})
    assert resp.get_json()["code"] == 1001


def test_submit_enters_pending_confirm_then_recruiting(client):
    """PRD v1.1：提交→待确认→确认后招聘中。"""
    login(client, "hr-001")
    resp = client.post("/api/requirements", json=FULL)
    data = resp.get_json()["data"]
    assert data["status"] == "pending_confirm"
    rid = data["id"]
    # 待确认状态不能直接暂停
    assert client.post(f"/api/requirements/{rid}/pause").get_json()["code"] == 1003
    confirmed = client.post(f"/api/requirements/{rid}/confirm")
    assert confirmed.get_json()["data"]["status"] == "recruiting"


def test_state_machine_flow(client):
    login(client, "hr-001")
    rid = client.post("/api/requirements", json=FULL).get_json()["data"]["id"]
    assert client.post(f"/api/requirements/{rid}/confirm").get_json()["data"]["status"] == "recruiting"
    assert client.post(f"/api/requirements/{rid}/pause").get_json()["data"]["status"] == "paused"
    assert client.post(f"/api/requirements/{rid}/resume").get_json()["data"]["status"] == "recruiting"
    assert client.post(f"/api/requirements/{rid}/complete").get_json()["data"]["status"] == "completed"
    # 终态不能再变更
    assert client.post(f"/api/requirements/{rid}/resume").get_json()["code"] == 1003
    # 非法流转：草稿不能直接确认/完成
    rid2 = client.post("/api/requirements", json={"name": "x", "save_as_draft": True}).get_json()["data"]["id"]
    assert client.post(f"/api/requirements/{rid2}/confirm").get_json()["code"] == 1003
    assert client.post(f"/api/requirements/{rid2}/complete").get_json()["code"] == 1003
    # 待确认可以直接关闭
    rid3 = client.post("/api/requirements", json=FULL).get_json()["data"]["id"]
    assert client.post(f"/api/requirements/{rid3}/close").get_json()["data"]["status"] == "closed"


def test_list_filters_and_detail(client):
    login(client, "hr-001")
    rid = client.post("/api/requirements", json=FULL).get_json()["data"]["id"]
    client.post(f"/api/requirements/{rid}/confirm")
    lst = client.get("/api/requirements", query_string={"status": "recruiting", "keyword": "后端"}).get_json()["data"]
    assert any(r["id"] == rid for r in lst["list"])
    detail = client.get(f"/api/requirements/{rid}").get_json()["data"]
    assert detail["candidate_stats"]["total"] == 0
    assert "jobs" in detail and "operation_logs" in detail


def test_headcount_validation(client):
    login(client, "hr-001")
    resp = client.post("/api/requirements", json={**FULL, "headcount": 0})
    assert resp.get_json()["code"] == 1001


def test_requirement_job_link_is_saved_and_visible(client):
    """需求表单选择职位后，职位反向关系和需求详情都应可见。"""
    login(client, "hr-001")
    job = client.post("/api/jobs", json={"name": "需求关联职位"}).get_json()["data"]
    req = client.post("/api/requirements", json={
        **FULL, "name": "带职位关联的需求", "job_id": job["id"],
    }).get_json()

    assert req["code"] == 0
    req_id = req["data"]["id"]
    assert req["data"]["job_id"] == job["id"]

    linked_job = client.get(f"/api/jobs/{job['id']}").get_json()["data"]
    assert linked_job["requirement_id"] == req_id

    detail = client.get(f"/api/requirements/{req_id}").get_json()["data"]
    assert [item["id"] for item in detail["jobs"]] == [job["id"]]


def test_requirement_job_link_update_and_conflict_are_checked(client):
    login(client, "hr-001")
    job = client.post("/api/jobs", json={"name": "待关联职位"}).get_json()["data"]
    req = client.post("/api/requirements", json={
        "name": "草稿需求", "save_as_draft": True,
    }).get_json()["data"]

    updated = client.put(f"/api/requirements/{req['id']}", json={
        "job_id": job["id"],
    }).get_json()
    assert updated["code"] == 0
    assert updated["data"]["job_id"] == job["id"]

    cleared = client.put(f"/api/requirements/{req['id']}", json={"job_id": None}).get_json()
    assert cleared["code"] == 0
    assert cleared["data"]["job_id"] is None
    assert client.get(f"/api/jobs/{job['id']}").get_json()["data"]["requirement_id"] is None

    relinked = client.put(f"/api/requirements/{req['id']}", json={
        "job_id": job["id"],
    }).get_json()
    assert relinked["code"] == 0

    another_req = client.post("/api/requirements", json={
        **FULL, "name": "另一个需求",
    }).get_json()["data"]
    conflict = client.put(f"/api/requirements/{another_req['id']}", json={
        "job_id": job["id"],
    }).get_json()
    assert conflict["code"] == 1003
