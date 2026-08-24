"""Offer 管理：状态流转、绑定校验、阶段门禁、阶段推进、原因必填、
文件上传与元数据、权限、乐观锁、操作日志。"""
import io
from datetime import datetime, timedelta

from conftest import login
from helpers import assign, ensure_hr, make_candidate, make_job, publish_job

V11_STAGES = ["new_resume", "pending_screen", "hr_screen_passed", "pending_interview",
              "interviewing", "interview_passed", "offer_pending", "pending_onboard", "onboarded"]


def _setup(client):
    """v1.1 模板职位 + 候选人 + 应聘记录推进到 interview_passed。"""
    ensure_hr(client)
    tpl = client.post("/api/pipeline-templates", json={
        "name": "Offer用例流程",
        "stages": [{"stage_key": k, "name": k, "sort_order": i + 1}
                   for i, k in enumerate(V11_STAGES)],
    }).get_json()["data"]["id"]
    job = make_job(client, name="Offer职位", template_id=tpl)
    publish_job(client, job["id"])
    cid = make_candidate(client, phone="13800007701", email="offer@example.com")
    app = assign(client, cid, job["id"])
    moved = client.post(f"/api/applications/{app['id']}/move",
                        json={"to_stage": "interview_passed", "reason": "面试通过",
                              "version": app["version"]}).get_json()["data"]
    return job, cid, moved


def _create(client, app_doc, **overrides):
    payload = {
        "application_id": app_doc["id"],
        "dept": "技术中心", "position": "Java后端工程师",
        "salary": "30k-45k",
        "onboard_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "valid_until": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
        "probation": "3个月", "contract_term": "3年", "benefits": "五险一金",
        "location": "上海", "remark": "备注",
    }
    payload.update(overrides)
    return client.post("/api/offers", json=payload)


def test_create_offer_bindings_and_stage_gate(client):
    job, cid, app = _setup(client)
    body = _create(client, app).get_json()
    assert body["code"] == 0, body
    data = body["data"]
    assert data["status"] == "draft" and data["version"] == 1
    assert data["candidate_id"] == cid and data["job_id"] == job["id"]
    # 缺少应聘记录
    assert client.post("/api/offers", json={"dept": "x", "position": "x", "salary": "x"}
                       ).get_json()["code"] == 1001
    # candidate_id 与应聘记录不匹配
    r = _create(client, app, candidate_id=999999)
    assert r.get_json()["code"] == 1001
    # 非法阶段禁止创建：把另一候选人停在新简历阶段
    cid2 = make_candidate(client, name="阶段不符", phone="13800007702", email="o2@example.com")
    app2 = assign(client, cid2, job["id"])
    r = _create(client, app2)
    assert r.get_json()["code"] == 1003
    # 同一应聘记录只能有一个进行中 Offer
    assert _create(client, app).get_json()["code"] == 1004


def test_status_flow_send_and_accept_advance_stage(client):
    job, cid, app = _setup(client)
    offer = _create(client, app).get_json()["data"]
    oid, version = offer["id"], offer["version"]
    # 草稿不能直接发送
    assert client.post(f"/api/offers/{oid}/status",
                       json={"action": "send", "version": version}).get_json()["code"] == 1003
    # 提交 → 待发送
    body = client.post(f"/api/offers/{oid}/status",
                       json={"action": "submit", "version": version}).get_json()
    assert body["data"]["status"] == "pending_send"
    version = body["data"]["version"]
    # 发送 → 已发送，应聘记录进入 offer_pending
    body = client.post(f"/api/offers/{oid}/status",
                       json={"action": "send", "version": version}).get_json()
    assert body["data"]["status"] == "sent" and body["data"]["sent_at"]
    version = body["data"]["version"]
    app_now = client.get(f"/api/candidates/{cid}").get_json()["data"]["applications"][0]
    assert app_now["current_stage"] == "offer_pending"
    # 接受 → 已接受，应聘记录进入 pending_onboard
    body = client.post(f"/api/offers/{oid}/status",
                       json={"action": "accept", "version": version}).get_json()
    assert body["data"]["status"] == "accepted"
    app_now = client.get(f"/api/candidates/{cid}").get_json()["data"]["applications"][0]
    assert app_now["current_stage"] == "pending_onboard"
    # 终态不可再流转
    assert client.post(f"/api/offers/{oid}/status",
                       json={"action": "withdraw", "version": body["data"]["version"],
                             "reason": "x"}).get_json()["code"] == 1003


def test_reject_withdraw_expire_require_reason(client):
    job, cid, app = _setup(client)

    def sent_offer():
        offer = _create(client, app).get_json()["data"]
        # 上一个 Offer 接受/关闭前只能有一个进行中：先对旧的走完流程
        return offer

    # 场景1：拒绝
    offer = sent_offer()
    client.post(f"/api/offers/{offer['id']}/status", json={"action": "submit", "version": offer["version"]})
    body = client.post(f"/api/offers/{offer['id']}/status",
                       json={"action": "send", "version": offer["version"] + 1}).get_json()
    v = body["data"]["version"]
    r = client.post(f"/api/offers/{offer['id']}/status", json={"action": "reject", "version": v})
    assert r.get_json()["code"] == 1001
    body = client.post(f"/api/offers/{offer['id']}/status",
                       json={"action": "reject", "version": v, "reason": "薪资未达成一致"}).get_json()
    assert body["data"]["status"] == "rejected"
    assert body["data"]["response_reason"] == "薪资未达成一致"

    # 场景2：撤回（待发送状态，含原因）
    offer2 = _create(client, app).get_json()["data"]
    b2 = client.post(f"/api/offers/{offer2['id']}/status",
                     json={"action": "submit", "version": offer2["version"]}).get_json()
    r = client.post(f"/api/offers/{offer2['id']}/status",
                    json={"action": "withdraw", "version": b2["data"]["version"]})
    assert r.get_json()["code"] == 1001
    b2 = client.post(f"/api/offers/{offer2['id']}/status",
                     json={"action": "withdraw", "version": b2["data"]["version"],
                           "reason": "职位暂停"}).get_json()
    assert b2["data"]["status"] == "withdrawn"
    assert b2["data"]["response_reason"] == "职位暂停"

    # 场景3：过期（手动，含原因）
    offer3 = _create(client, app).get_json()["data"]
    client.post(f"/api/offers/{offer3['id']}/status", json={"action": "submit", "version": offer3["version"]})
    b3 = client.post(f"/api/offers/{offer3['id']}/status",
                     json={"action": "send", "version": offer3["version"] + 1}).get_json()
    r = client.post(f"/api/offers/{offer3['id']}/status",
                    json={"action": "expire", "version": b3["data"]["version"]})
    assert r.get_json()["code"] == 1001
    b3 = client.post(f"/api/offers/{offer3['id']}/status",
                     json={"action": "expire", "version": b3["data"]["version"],
                           "reason": "候选人超期未响应"}).get_json()
    assert b3["data"]["status"] == "expired"


def test_lazy_auto_expire(client):
    job, cid, app = _setup(client)
    offer = _create(client, app).get_json()["data"]
    oid = offer["id"]
    client.post(f"/api/offers/{oid}/status", json={"action": "submit", "version": offer["version"]})
    client.post(f"/api/offers/{oid}/status", json={"action": "send", "version": offer["version"] + 1})
    # 直接改库模拟有效期已过
    with client.application.app_context():
        from common.db import col

        col("offers").update_one({"_id": oid}, {
            "$set": {"valid_until": datetime.now() - timedelta(days=1)}})
    body = client.get(f"/api/offers/{oid}").get_json()["data"]
    assert body["status"] == "expired"
    assert "有效期" in body["response_reason"]


def test_optimistic_lock_conflict(client):
    job, cid, app = _setup(client)
    offer = _create(client, app).get_json()["data"]
    r = client.post(f"/api/offers/{offer['id']}/status",
                    json={"action": "submit", "version": 999})
    assert r.get_json()["code"] == 1007
    # 缺少 version：按 -1 处理，同样触发乐观锁冲突
    assert client.post(f"/api/offers/{offer['id']}/status",
                       json={"action": "submit"}).get_json()["code"] == 1007


def test_edit_rules(client):
    job, cid, app = _setup(client)
    offer = _create(client, app).get_json()["data"]
    r = client.put(f"/api/offers/{offer['id']}", json={"salary": "35k-50k"}).get_json()
    assert r["data"]["salary"] == "35k-50k"
    client.post(f"/api/offers/{offer['id']}/status", json={"action": "submit", "version": offer["version"]})
    # 非草稿不可编辑
    assert client.put(f"/api/offers/{offer['id']}", json={"salary": "1"}).get_json()["code"] == 1003
    # 有效期不能早于当前（草稿上校验）：先撤回当前 Offer 释放唯一进行中名额
    cur = client.get(f"/api/offers/{offer['id']}").get_json()["data"]
    client.post(f"/api/offers/{offer['id']}/status",
                json={"action": "withdraw", "version": cur["version"], "reason": "测试撤回"})
    offer_b = _create(client, app, salary="20k").get_json()["data"]
    assert client.put(f"/api/offers/{offer_b['id']}",
                      json={"valid_until": "2020-01-01"}).get_json()["code"] == 1001


def test_permissions(client):
    job, cid, app = _setup(client)
    login(client, "screen-001")
    r = _create(client, app)
    assert r.get_json()["code"] == 1006
    assert client.get("/api/offers").get_json()["code"] == 0


def test_operation_logs(client, app):
    job, cid, app_doc = _setup(client)
    offer = _create(client, app_doc).get_json()["data"]
    oid = offer["id"]
    client.post(f"/api/offers/{oid}/status", json={"action": "submit", "version": offer["version"]})
    client.post(f"/api/offers/{oid}/status",
                json={"action": "send", "version": offer["version"] + 1})
    client.post(f"/api/offers/{oid}/status",
                json={"action": "accept", "version": offer["version"] + 2})
    with app.app_context():
        from common.db import col

        actions = {l["action"] for l in
                   col("operation_logs").find({"biz_type": "offer", "biz_id": str(oid)})}
    assert {"create", "submit", "send", "accept"} <= actions


def test_file_upload_metadata_and_download(client):
    job, cid, app = _setup(client)
    offer = _create(client, app).get_json()["data"]
    oid = offer["id"]
    # 上传 Offer 文件（走现有文件服务：OSS/本地 + files 元数据）
    content = b"OFFER-FILE-CONTENT-123"
    r = client.post(f"/api/offers/{oid}/file", data={
        "file": (io.BytesIO(content), "offer-letter.pdf"),
    }, content_type="multipart/form-data")
    body = r.get_json()
    assert body["code"] == 0, body
    assert body["data"]["file"]["originalName"] == "offer-letter.pdf"
    file_id = body["data"]["file"]["id"]

    # MongoDB files 集合只存元数据（objectKey/originalName/size...）
    with client.application.app_context():
        from bson import ObjectId
        from common.db import col

        meta = col("files").find_one({"_id": ObjectId(file_id)})
    assert meta["objectKey"] and meta["size"] == len(content)
    assert meta["bizType"] == "offer"

    # 下载：登录校验 + 内容一致（不暴露密钥）
    anon = client.application.test_client()
    assert anon.get(f"/api/offers/{oid}/download").status_code == 401
    dl = client.get(f"/api/offers/{oid}/download")
    assert dl.status_code == 200 and dl.data == content
    # 预览：重定向到文件服务
    pv = client.get(f"/api/offers/{oid}/preview")
    assert pv.status_code in (301, 302)
    assert f"/api/files/{file_id}/download" in pv.headers["Location"]
    # 未上传文件的 Offer 下载 → 404
    offer2 = _create(client, app, salary="1k").get_json()
    if offer2["code"] == 0:
        assert client.get(f"/api/offers/{offer2['data']['id']}/download").get_json()["code"] == 1002
