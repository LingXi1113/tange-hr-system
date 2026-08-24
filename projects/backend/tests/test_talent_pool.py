"""人才库：唯一约束、加入/移出/激活、批量操作、筛选分页、脱敏、导出留痕、权限。"""
from conftest import login
from helpers import assign, ensure_hr, make_candidate, make_job, make_template, publish_job


def _setup(client, job_name="人才库职位"):
    ensure_hr(client)
    tpl = make_template(client)
    job = make_job(client, name=job_name, template_id=tpl)
    publish_job(client, job["id"])
    return job


def _mk_cand(client, suffix):
    return make_candidate(client, name=f"库候选人{suffix}",
                          phone=f"1351111{suffix.zfill(4)}",
                          email=f"pool{suffix}@example.com")


def _add(client, cid, **overrides):
    payload = {"candidate_id": cid, "category": "tech",
               "tags": ["Java", "高潜"], "reason": "储备"}
    payload.update(overrides)
    return client.post("/api/talent-pool", json=payload)


def test_unique_constraint_and_add(client):
    _setup(client)
    cid = _mk_cand(client, "0001")
    body = _add(client, cid).get_json()
    assert body["code"] == 0, body
    entry = body["data"]["added"][0]
    assert entry["candidate_id"] == cid and entry["category"] == "tech"
    # 同一候选人不能重复进入（唯一约束）
    dup = _add(client, cid)
    assert dup.get_json()["code"] == 1004
    # 唯一索引存在
    with client.application.app_context():
        from common.db import col

        indexes = col("talent_pool").index_information()
        assert any(idx.get("unique") and ("candidate_id", 1) in idx["key"]
                   for idx in indexes.values())
    # 候选人不存在（单条模式直接报错）
    assert _add(client, 999999).get_json()["code"] == 1002


def test_batch_add(client):
    _setup(client)
    c1, c2, c3 = _mk_cand(client, "0002"), _mk_cand(client, "0003"), _mk_cand(client, "0004")
    _add(client, c3)  # 预先入库，制造重复
    body = client.post("/api/talent-pool", json={
        "candidate_ids": [c1, c2, c3], "category": "product", "reason": "批量",
    }).get_json()
    assert body["code"] == 0
    assert len(body["data"]["added"]) == 2
    assert body["data"]["duplicates"][0]["candidate_id"] == c3


def test_update_fields(client):
    job = _setup(client)
    cid = _mk_cand(client, "0005")
    entry = _add(client, cid).get_json()["data"]["added"][0]
    body = client.put(f"/api/talent-pool/{entry['id']}", json={
        "category": "sales", "tags": ["新标签"], "reason": "更新原因",
        "recommended_job_id": job["id"], "last_contact_at": "2026-08-01",
    }).get_json()
    data = body["data"]
    assert data["category"] == "sales" and data["tags"] == ["新标签"]
    assert data["recommended_job_name"] == job["name"]
    assert data["last_contact_at"].startswith("2026-08-01")
    # 非法日期
    assert client.put(f"/api/talent-pool/{entry['id']}",
                      json={"last_contact_at": "bad"}).get_json()["code"] == 1001


def test_batch_tags(client):
    _setup(client)
    c1, c2 = _mk_cand(client, "0006"), _mk_cand(client, "0007")
    e1 = _add(client, c1).get_json()["data"]["added"][0]
    e2 = _add(client, c2, tags=["原有"]).get_json()["data"]["added"][0]
    # 追加模式
    body = client.post("/api/talent-pool/batch-tags", json={
        "entry_ids": [e1["id"], e2["id"]], "tags": ["共同标签"], "mode": "append",
    }).get_json()
    assert body["data"]["updated"] == 2
    lst = {e["id"]: e for e in client.get("/api/talent-pool",
                                          query_string={"page_size": 50}).get_json()["data"]["list"]}
    assert "共同标签" in lst[e1["id"]]["tags"]
    assert lst[e2["id"]]["tags"] == ["原有", "共同标签"]
    # 覆盖模式
    client.post("/api/talent-pool/batch-tags", json={
        "entry_ids": [e1["id"]], "tags": ["仅存"], "mode": "replace"})
    lst = {e["id"]: e for e in client.get("/api/talent-pool",
                                          query_string={"page_size": 50}).get_json()["data"]["list"]}
    assert lst[e1["id"]]["tags"] == ["仅存"]


def test_remove_and_readd(client):
    _setup(client)
    cid = _mk_cand(client, "0008")
    entry = _add(client, cid).get_json()["data"]["added"][0]
    # 需要二次确认
    assert client.delete(f"/api/talent-pool/{entry['id']}").get_json()["code"] == 1001
    assert client.delete(f"/api/talent-pool/{entry['id']}?confirm=1").get_json()["code"] == 0
    assert client.get("/api/talent-pool",
                      query_string={"keyword": "库候选人0008"}).get_json()["data"]["total"] == 0
    # 移出后可再次加入
    assert _add(client, cid).get_json()["code"] == 0


def test_batch_remove(client):
    _setup(client)
    c1, c2 = _mk_cand(client, "0009"), _mk_cand(client, "0010")
    e1 = _add(client, c1).get_json()["data"]["added"][0]
    e2 = _add(client, c2).get_json()["data"]["added"][0]
    body = client.post("/api/talent-pool/batch-remove",
                       json={"entry_ids": [e1["id"], e2["id"]]}).get_json()
    assert body["data"]["removed"] == 2


def test_activate_creates_application(client):
    job = _setup(client)
    cid = _mk_cand(client, "0011")
    entry = _add(client, cid).get_json()["data"]["added"][0]
    body = client.post(f"/api/talent-pool/{entry['id']}/activate",
                       json={"job_id": job["id"]}).get_json()
    assert body["code"] == 0, body
    assert body["data"]["entry"]["status"] == "activated"
    # 应聘记录已创建（来源 talent_pool）
    apps = client.get(f"/api/candidates/{cid}/applications").get_json()["data"]
    assert apps[0]["job_id"] == job["id"] and apps[0]["source"] == "talent_pool"
    # 已激活不能再次激活
    assert client.post(f"/api/talent-pool/{entry['id']}/activate",
                       json={"job_id": job["id"]}).get_json()["code"] == 1003


def test_filters_pagination_and_masking(client):
    _setup(client)
    c1 = _mk_cand(client, "0012")
    c2 = _mk_cand(client, "0013")
    _add(client, c1, category="tech", tags=["Python"], source="elimination_added")
    _add(client, c2, category="sales", tags=["销售"], source="offer_rejected")
    base = "/api/talent-pool"
    assert client.get(base, query_string={"keyword": "库候选人0012"}).get_json()["data"]["total"] == 1
    assert client.get(base, query_string={"category": "tech"}).get_json()["data"]["total"] == 1
    assert client.get(base, query_string={"tag": "销售"}).get_json()["data"]["total"] == 1
    assert client.get(base, query_string={"source": "offer_rejected"}).get_json()["data"]["total"] == 1
    # 分页
    paged_data = client.get(base, query_string={"page": 1, "page_size": 1}).get_json()["data"]
    assert paged_data["total"] >= 2 and len(paged_data["list"]) == 1
    # 脱敏
    row = client.get(base, query_string={"keyword": "库候选人0012"}).get_json()["data"]["list"][0]
    assert "****" in row["phone"] and "***@" in row["email"]
    row_full = client.get(base, query_string={"keyword": "库候选人0012", "mask": "0"}
                          ).get_json()["data"]["list"][0]
    assert row_full["phone"] == "13511110012"


def test_export_writes_export_logs(client):
    _setup(client)
    cid = _mk_cand(client, "0014")
    _add(client, cid)
    resp = client.get("/api/talent-pool/export")
    assert resp.status_code == 200
    assert "库候选人0014" in resp.get_data(as_text=True)
    with client.application.app_context():
        from common.db import col

        log = col("export_logs").find_one({"scene": "talent_pool"})
        assert log and log["row_count"] >= 1


def test_permissions_and_logs(client, app):
    job = _setup(client)
    cid = _mk_cand(client, "0015")
    entry = _add(client, cid).get_json()["data"]["added"][0]
    login(client, "screen-001")  # 非 HR 不能写
    assert client.post("/api/talent-pool",
                       json={"candidate_id": cid}).get_json()["code"] == 1006
    assert client.delete(f"/api/talent-pool/{entry['id']}?confirm=1").get_json()["code"] == 1006
    # 读允许
    assert client.get("/api/talent-pool").get_json()["code"] == 0
    # 操作日志
    with app.app_context():
        from common.db import col

        actions = {l["action"] for l in
                   col("operation_logs").find({"biz_type": "talent_pool"})}
    assert {"add", "remove"} <= actions or "add" in actions
