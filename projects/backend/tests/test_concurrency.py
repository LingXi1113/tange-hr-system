from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from conftest import login
from helpers import assign, ensure_hr, make_candidate, make_job, publish_job


def _template(client, stages):
    response = client.post("/api/pipeline-templates", json={
        "name": "并发保护模板",
        "stages": [
            {"stage_key": key, "name": key, "sort_order": index + 1, "lock_days": lock_days}
            for index, (key, lock_days) in enumerate(stages)
        ],
    })
    assert response.get_json()["code"] == 0
    return response.get_json()["data"]["id"]


def test_application_unique_index_protects_when_duplicate_check_is_bypassed(client, monkeypatch):
    ensure_hr(client)
    template_id = _template(client, [("new_resume", 0)])
    job = make_job(client, name="并发申请职位", template_id=template_id)
    publish_job(client, job["id"])
    candidate_id = make_candidate(client, phone="13900002001", email="application-race@example.com")
    assign(client, candidate_id, job["id"])

    # 模拟两个请求同时通过了前置查重，最终由 MongoDB 唯一索引拦截第二次插入。
    monkeypatch.setattr("common.flow.check_duplicate_application", lambda *args, **kwargs: None)
    response = client.post(f"/api/candidates/{candidate_id}/applications", json={"job_id": job["id"]})
    # HR assignment now creates a seven-day candidate lock before a duplicate
    # application can be attempted again.
    assert response.get_json()["code"] == 1005


def test_active_lock_unique_index_protects_when_lock_check_is_bypassed(client, monkeypatch):
    ensure_hr(client)
    template_id = _template(client, [("new_resume", 2)])
    job_a = make_job(client, name="并发锁定职位A", template_id=template_id)
    job_b = make_job(client, name="并发锁定职位B", template_id=template_id)
    publish_job(client, job_a["id"])
    publish_job(client, job_b["id"])
    candidate_id = make_candidate(client, phone="13900002002", email="lock-race@example.com")
    assign(client, candidate_id, job_a["id"])

    # 模拟两个请求同时读到“无锁”，由 active candidate lock 唯一索引兜底。
    monkeypatch.setattr("common.flow.active_lock_for_candidate", lambda *args, **kwargs: None)
    response = client.post(f"/api/candidates/{candidate_id}/applications", json={"job_id": job_b["id"]})
    assert response.get_json()["code"] == 1005


def test_offer_edit_rejects_stale_version(client):
    ensure_hr(client)
    template_id = _template(client, [
        ("new_resume", 0), ("interview_passed", 0), ("offer_pending", 0),
    ])
    job = make_job(client, name="并发 Offer 职位", template_id=template_id)
    publish_job(client, job["id"])
    candidate_id = make_candidate(client, phone="13900002003", email="offer-race@example.com")
    application = assign(client, candidate_id, job["id"])
    moved = client.post(f"/api/applications/{application['id']}/move", json={
        "to_stage": "interview_passed", "reason": "并发测试", "version": application["version"],
    }).get_json()["data"]
    offer_payload = {
        "application_id": moved["id"], "dept": "技术中心", "position": "工程师", "salary": "30k",
        "onboard_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "valid_until": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
    }
    offer = client.post("/api/offers", json=offer_payload).get_json()["data"]
    first = client.put(f"/api/offers/{offer['id']}", json={
        "salary": "35k", "version": offer["version"],
    }).get_json()
    assert first["code"] == 0
    stale = client.put(f"/api/offers/{offer['id']}", json={
        "salary": "40k", "version": offer["version"],
    }).get_json()
    assert stale["code"] == 1007


def test_onboarding_start_rejects_stale_version(client):
    # 通过直接构造最小业务记录，专门验证入职记录自身的 CAS。
    ensure_hr(client)
    from common.db import col, insert_doc

    with client.application.app_context():
        app = insert_doc("applications", {
            "candidate_id": 1, "job_id": 1, "current_stage": "pending_onboard",
            "status": "pending_onboard", "version": 1,
        })
        record = insert_doc("onboarding_records", {
            "application_id": app["_id"], "candidate_id": 1, "job_id": 1,
            "status": "pending", "version": 1, "checklist": [],
        })
    response = client.post(f"/api/onboarding/{record['_id']}/start", json={"version": 1})
    assert response.get_json()["code"] == 0
    stale = client.post(f"/api/onboarding/{record['_id']}/start", json={"version": 1})
    assert stale.get_json()["code"] == 1007


def test_candidate_identity_index_protects_racing_create(client, monkeypatch):
    ensure_hr(client)
    first = client.post("/api/candidates", json={
        "name": "第一个候选人", "phone": "13900002011", "email": "race@example.com",
    }).get_json()
    assert first["code"] == 0

    # Simulate both requests passing the application-level duplicate query.
    monkeypatch.setattr("modules.candidate_api._find_duplicates", lambda *args, **kwargs: [])
    second = client.post("/api/candidates", json={
        "name": "并发重复候选人", "phone": "13900002011", "email": "other@example.com",
    }).get_json()
    assert second["code"] == 0
    assert second["data"]["duplicated"] is True
    with client.application.app_context():
        from common.db import col

        assert col("candidates").count_documents({"phone_key": "13900002011"}) == 1


def test_force_duplicate_candidate_does_not_block_normal_identity_key(client):
    ensure_hr(client)
    first = client.post("/api/candidates", json={
        "name": "原始候选人", "phone": "13900002012", "email": "force@example.com",
    }).get_json()["data"]["candidate"]
    forced = client.post("/api/candidates", json={
        "name": "人工确认的重复候选人", "phone": "13900002012", "force": 1,
    }).get_json()
    assert forced["code"] == 0
    with client.application.app_context():
        from common.db import col

        forced_doc = col("candidates").find_one({"_id": forced["data"]["candidate"]["id"]})
        assert forced_doc.get("dedupe_exempt") is True
        assert "phone_key" not in forced_doc
        assert col("candidates").find_one({"_id": first["id"]}).get("phone_key") == "13900002012"


def test_candidate_edit_rejects_stale_version(client):
    ensure_hr(client)
    candidate_id = make_candidate(client, phone="13900002013", email="candidate-version@example.com")
    current = client.get(f"/api/candidates/{candidate_id}").get_json()["data"]
    updated = client.put(f"/api/candidates/{candidate_id}", json={
        "name": "最新名称", "version": current["version"],
    }).get_json()
    assert updated["code"] == 0
    stale = client.put(f"/api/candidates/{candidate_id}", json={
        "name": "旧页面名称", "version": current["version"],
    }).get_json()
    assert stale["code"] == 1007


def test_candidate_import_unique_index_turns_race_into_duplicate_row(client, monkeypatch):
    ensure_hr(client)
    make_candidate(client, phone="13900002014", email="import-race@example.com")
    monkeypatch.setattr("modules.candidate_api._find_duplicates", lambda *args, **kwargs: [])
    import io

    content = "姓名,性别,手机号,邮箱,城市,来源\n并发导入,男,13900002014,other@example.com,上海,import\n"
    response = client.post("/api/candidates/import", data={
        "file": (io.BytesIO(content.encode("utf-8")), "race.csv"),
    }, content_type="multipart/form-data").get_json()
    assert response["code"] == 0
    assert response["data"]["success_count"] == 0
    assert len(response["data"]["duplicates"]) == 1


def _interview_setup(client):
    ensure_hr(client)
    response = client.post("/api/pipeline-templates", json={
        "name": "面试并发保护",
        "stages": [
            {"stage_key": "new_resume", "name": "新简历", "sort_order": 1},
            {"stage_key": "pending_interview", "name": "待面试", "sort_order": 2},
            {"stage_key": "interviewing", "name": "面试中", "sort_order": 3},
        ],
    })
    template_id = response.get_json()["data"]["id"]
    job = make_job(client, name="面试并发职位", template_id=template_id)
    publish_job(client, job["id"])
    candidate_id = make_candidate(client, phone="13900002021", email="interview-race@example.com")
    app = assign(client, candidate_id, job["id"])
    return candidate_id, app["id"]


def _interview_payload(app_id, start, end):
    return {
        "application_id": app_id, "round": "一面", "type": "video",
        "start_at": start, "end_at": end, "interviewer_name": "并发测试",
    }


def test_interview_schedule_guard_allows_only_one_overlapping_create(client):
    _, app_id = _interview_setup(client)
    start = (datetime.now() + timedelta(hours=24)).replace(second=0, microsecond=0)
    end = start + timedelta(hours=1)
    payload = _interview_payload(
        app_id, start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"),
    )
    clients = [client.application.test_client(), client.application.test_client()]
    for item in clients:
        login(item)

    def submit(index):
        return clients[index].post("/api/interviews", json=payload).get_json()["code"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(submit, [0, 1]))
    assert sorted(codes) == [0, 1004]


def test_interview_edit_rejects_stale_version(client):
    _, app_id = _interview_setup(client)
    start = (datetime.now() + timedelta(hours=24)).replace(second=0, microsecond=0)
    end = start + timedelta(hours=1)
    created = client.post("/api/interviews", json=_interview_payload(
        app_id, start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"),
    )).get_json()["data"]
    assert client.put(f"/api/interviews/{created['id']}", json={
        "remark": "最新备注", "version": created["version"],
    }).get_json()["code"] == 0
    stale = client.put(f"/api/interviews/{created['id']}", json={
        "remark": "旧备注", "version": created["version"],
    }).get_json()
    assert stale["code"] == 1007


def test_interview_reschedule_rejects_stale_version(client):
    _, app_id = _interview_setup(client)
    start = (datetime.now() + timedelta(hours=24)).replace(second=0, microsecond=0)
    end = start + timedelta(hours=1)
    created = client.post("/api/interviews", json=_interview_payload(
        app_id, start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"),
    )).get_json()["data"]
    moved_start = start + timedelta(hours=2)
    moved_end = moved_start + timedelta(hours=1)
    first = client.post(f"/api/interviews/{created['id']}/reschedule", json={
        "start_at": moved_start.strftime("%Y-%m-%d %H:%M"),
        "end_at": moved_end.strftime("%Y-%m-%d %H:%M"),
        "reason": "第一次改期", "version": created["version"],
    }).get_json()
    assert first["code"] == 0
    stale = client.post(f"/api/interviews/{created['id']}/reschedule", json={
        "start_at": (moved_start + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
        "end_at": (moved_end + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
        "reason": "旧页面改期", "version": created["version"],
    }).get_json()
    assert stale["code"] == 1007


def test_interview_feedback_uses_unique_key_and_version(client):
    _, app_id = _interview_setup(client)
    start = (datetime.now() + timedelta(hours=24)).replace(second=0, microsecond=0)
    end = start + timedelta(hours=1)
    interview = client.post("/api/interviews", json=_interview_payload(
        app_id, start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"),
    )).get_json()["data"]
    feedback = client.post(f"/api/interviews/{interview['id']}/feedback", json={
        "conclusion": "pass", "dimension_scores": [{"name": "专业能力", "score": 4}],
    }).get_json()["data"]
    updated = client.post(f"/api/interviews/{interview['id']}/feedback", json={
        "conclusion": "pass", "comment": "最新反馈", "version": feedback["version"],
    }).get_json()
    assert updated["code"] == 0
    stale = client.post(f"/api/interviews/{interview['id']}/feedback", json={
        "conclusion": "fail", "comment": "旧反馈", "version": feedback["version"],
    }).get_json()
    assert stale["code"] == 1007
    with client.application.app_context():
        from common.db import col

        assert col("interview_feedback").count_documents({"interview_id": interview["id"]}) == 1
