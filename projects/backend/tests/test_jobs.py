"""职位管理 + 公开页免登投递。"""
import io

from conftest import login
from helpers import make_job, make_template, publish_job


def test_job_crud_and_unique_code(client):
    login(client, "hr-001")
    job = make_job(client)
    assert job["status"] == "draft"
    assert job["public_token"]
    # 编码唯一
    dup = client.post("/api/jobs", json={"name": "x", "code": job["code"]})
    assert dup.get_json()["code"] == 1004
    # 编辑
    upd = client.put(f"/api/jobs/{job['id']}", json={"location": "上海"}).get_json()["data"]
    assert upd["location"] == "上海"
    # 复制
    cp = client.post(f"/api/jobs/{job['id']}/copy").get_json()["data"]
    assert cp["name"].endswith("（副本）") and cp["id"] != job["id"]


def test_job_status_flow(client):
    login(client, "hr-001")
    job = make_job(client)
    assert client.post(f"/api/jobs/{job['id']}/status", json={"action": "publish"}).get_json()["code"] == 1003
    client.post(f"/api/jobs/{job['id']}/status", json={"action": "submit"})
    assert client.post(f"/api/jobs/{job['id']}/status", json={"action": "publish"}).get_json()["data"]["status"] == "recruiting"
    client.post(f"/api/jobs/{job['id']}/status", json={"action": "pause"})
    assert client.post(f"/api/jobs/{job['id']}/status", json={"action": "resume"}).get_json()["data"]["status"] == "recruiting"
    client.post(f"/api/jobs/{job['id']}/status", json={"action": "close"})
    assert client.post(f"/api/jobs/{job['id']}/status", json={"action": "resume"}).get_json()["code"] == 1003


def _apply(client, token, **overrides):
    data = {
        "name": "投递候选人", "phone": "13700002222", "email": "apply@example.com",
        "city": "北京", "expected_salary": "30k", "onboard_time": "随时",
        "privacy_agreed": "1",
    }
    data.update(overrides)
    return client.post(f"/api/public/jobs/{token}/apply", data=data,
                       content_type="multipart/form-data")


def test_public_page_and_apply_flow(client):
    login(client, "hr-001")
    # 无锁定模板：本用例聚焦投递与查重复用，锁定期行为在候选人用例覆盖
    tpl = client.post("/api/pipeline-templates", json={
        "name": "投递用例流程",
        "stages": [{"stage_key": "new_resume", "name": "新简历", "sort_order": 1, "lock_days": 0}],
    }).get_json()["data"]["id"]
    job = make_job(client, template_id=tpl)
    publish_job(client, job["id"])
    token = job["public_token"]

    # 公开页免登录可见
    anon = client.application.test_client()
    pub = anon.get(f"/api/public/jobs/{token}")
    assert pub.status_code == 200
    body = pub.get_json()["data"]
    assert body["name"] == "Java后端工程师" and body["accepting"] is True

    # 首次投递
    resp = anon.post(f"/api/public/jobs/{token}/apply", data={
        "name": "投递候选人", "phone": "13700002222", "email": "apply@example.com",
        "privacy_agreed": "1",
    }, content_type="multipart/form-data")
    body = resp.get_json()
    assert body["code"] == 0, body
    assert body["data"]["application_id"]

    # 重复投递同一职位
    dup = _apply(anon, token)
    assert dup.get_json()["code"] == 1004

    # 未勾选隐私授权
    no_privacy = _apply(anon, token, phone="13700003333", email="p3@example.com", privacy_agreed="")
    assert no_privacy.get_json()["code"] == 1001

    # 手机号命中已有候选人：复用主档，不重复建档
    login(client, "hr-001")
    before = client.get("/api/candidates", query_string={"keyword": "13700002222"}).get_json()["data"]["total"]
    job2 = make_job(client, name="前端工程师", template_id=tpl)
    publish_job(client, job2["id"])
    resp = anon.post(f"/api/public/jobs/{job2['public_token']}/apply", data={
        "name": "投递候选人", "phone": "13700002222", "privacy_agreed": "1",
    }, content_type="multipart/form-data")
    assert resp.get_json()["code"] == 0
    after = client.get("/api/candidates", query_string={"keyword": "13700002222"}).get_json()["data"]["total"]
    assert after == before  # 复用主档，候选人数量不变


def test_public_apply_auto_parses_resume(client):
    login(client, "hr-001")
    tpl = make_template(client)
    job = make_job(client, name="自动解析职位", template_id=tpl)
    publish_job(client, job["id"])

    import docx

    document = docx.Document()
    document.add_paragraph("姓名：王小明\n手机号：13966667777\n邮箱：wangxm@example.com\n城市：杭州")
    resume = io.BytesIO()
    document.save(resume)
    resume.seek(0)

    anon = client.application.test_client()
    response = anon.post(f"/api/public/jobs/{job['public_token']}/apply", data={
        "name": "公开候选人", "phone": "13966667777", "email": "",
        "privacy_agreed": "1", "resume": (resume, "auto-resume.docx"),
    }, content_type="multipart/form-data")
    body = response.get_json()
    assert body["code"] == 0
    assert body["data"]["resume_parse_status"] == "system"
    assert body["data"]["resume_fields"]["name"] == "王小明"

    login(client, "hr-001")
    candidate = client.get(f"/api/candidates/{body['data']['candidate_id']}").get_json()["data"]
    assert candidate["name"] == "公开候选人"  # 不覆盖投递时已经填写的姓名
    assert candidate["city"] == "杭州"  # 自动补齐空白字段
    assert candidate["attachments"][0]["parse_status"] == "system"


def test_public_apply_resume_parse_failure_does_not_block_application(client):
    login(client, "hr-001")
    tpl = make_template(client)
    job = make_job(client, name="解析失败仍可投递", template_id=tpl)
    publish_job(client, job["id"])

    anon = client.application.test_client()
    response = anon.post(f"/api/public/jobs/{job['public_token']}/apply", data={
        "name": "图片候选人", "phone": "13866667777", "privacy_agreed": "1",
        "resume": (io.BytesIO(b"not-real-image"), "resume.png"),
    }, content_type="multipart/form-data")
    body = response.get_json()
    assert body["code"] == 0
    assert body["data"]["resume_parse_status"] == "failed"
    assert body["data"]["application_id"]


def test_paused_job_rejects_apply(client):
    login(client, "hr-001")
    tpl = make_template(client)
    job = make_job(client, template_id=tpl)
    publish_job(client, job["id"])
    client.post(f"/api/jobs/{job['id']}/status", json={"action": "pause"})
    resp = _apply(client.application.test_client(), job["public_token"])
    assert resp.get_json()["code"] == 1003


def test_closed_requirement_blocks_apply(client):
    login(client, "hr-001")
    full = {
        "name": "关需求", "dept_id": "dept-tech", "headcount": 1,
        "request_type": "new_headcount", "priority": "mid", "requirements": "x",
    }
    rid = client.post("/api/requirements", json=full).get_json()["data"]["id"]
    tpl = make_template(client)
    job = make_job(client, template_id=tpl, requirement_id=rid)
    publish_job(client, job["id"])
    client.post(f"/api/requirements/{rid}/close")
    resp = _apply(client.application.test_client(), job["public_token"])
    assert resp.get_json()["code"] == 1003


def test_export_jobs_logs(client):
    login(client, "hr-001")
    make_job(client)
    resp = client.get("/api/jobs/export")
    assert resp.status_code == 200
    assert "职位名称" in resp.get_data(as_text=True)
