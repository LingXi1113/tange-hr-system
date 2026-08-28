"""阶段A 共享构造辅助。"""
from conftest import login

TPL_PAYLOAD = {
    "name": "测试流程",
    "stages": [
        {"stage_key": "new_resume", "name": "新简历", "sort_order": 1, "lock_days": 2},
        {"stage_key": "business_screen", "name": "业务复筛", "sort_order": 2, "lock_days": 0},
        {"stage_key": "interview_1", "name": "一面", "sort_order": 3, "lock_days": 0},
    ],
}


def make_template(client) -> int:
    # 流程模板由超级管理员维护；业务测试创建后恢复为普通 HR 会话。
    login(client, "super-admin-001")
    resp = client.post("/api/pipeline-templates", json=TPL_PAYLOAD)
    login(client, "hr-001")
    assert resp.get_json()["code"] == 0, resp.get_data(as_text=True)
    return resp.get_json()["data"]["id"]


def make_job(client, name="Java后端工程师", template_id=None, requirement_id=None) -> dict:
    payload = {"name": name, "template_id": template_id, "requirement_id": requirement_id,
               "dept_name": "技术中心", "headcount": 2}
    resp = client.post("/api/jobs", json=payload)
    assert resp.get_json()["code"] == 0, resp.get_data(as_text=True)
    return resp.get_json()["data"]


def publish_job(client, job_id: int):
    for action in ("submit", "publish"):
        resp = client.post(f"/api/jobs/{job_id}/status", json={"action": action})
        assert resp.get_json()["code"] == 0, resp.get_data(as_text=True)


def make_candidate(client, name="测试候选人", phone="13900001111", email="t1@example.com") -> int:
    resp = client.post("/api/candidates", json={"name": name, "phone": phone, "email": email})
    body = resp.get_json()
    assert body["code"] == 0, body
    return body["data"]["candidate"]["id"]


def assign(client, candidate_id: int, job_id: int, source="manual") -> dict:
    resp = client.post(f"/api/candidates/{candidate_id}/applications",
                       json={"job_id": job_id, "source": source})
    body = resp.get_json()
    assert body["code"] == 0, body
    return body["data"]


def ensure_hr(client):
    login(client, "hr-001")
