"""Intelligent resume-to-job screening integration."""
from conftest import login
from helpers import assign


def _candidate(client, payload):
    response = client.post("/api/candidates", json=payload)
    body = response.get_json()
    assert body["code"] == 0, body
    return body["data"]["candidate"]["id"]


def _job(client, payload):
    response = client.post("/api/jobs", json={
        "name": payload.pop("name"),
        "dept_name": "销售部",
        "headcount": 1,
        **payload,
    })
    body = response.get_json()
    assert body["code"] == 0, body
    return body["data"]


def test_sales_screening_has_explainable_dimensions_and_hr_review(client):
    login(client, "hr-001")
    job = _job(client, {
        "name": "AI电商大客户销售",
        "description": "面向品牌商家和MCN销售AI客服SaaS产品",
        "qualification": "2年以上企业软件销售经验，熟悉客户开发、商务谈判和回款",
        "screening_rules": {
            "profile": "sales",
            "min_education": "大专",
            "min_work_years": 2,
            "required_skills": ["客户开发", "商务谈判", "回款"],
            "preferred_skills": ["SaaS", "AI", "电商"],
            "industry_tags": ["AI", "SaaS", "电商"],
            "pass_score": 75,
            "pending_score": 55,
        },
    })
    candidate_id = _candidate(client, {
        "name": "销售匹配候选人",
        "phone": "13988001111",
        "email": "sales-match@example.com",
        "highest_education": "本科",
        "tags": "AI,SaaS,电商,大客户,品牌商家,MCN,客户资源,销售周期",
        "work_experience": [{
            "company": "智能电商科技有限公司",
            "position": "大客户销售经理",
            "start": "2022-01",
            "end": "2025-12",
            "desc": "负责客户开发、需求挖掘、商务谈判、签约和回款，年度销售额580万元，完成率116%，服务品牌商家和MCN客户。",
        }],
    })
    application = assign(client, candidate_id, job["id"])

    response = client.post(f"/api/applications/{application['id']}/screen")
    result = response.get_json()["data"]
    assert response.get_json()["code"] == 0
    assert result["profile"] == "sales"
    assert result["score"] >= 70
    assert {item["name"] for item in result["dimensions"]} == {
        "销售业绩", "行业匹配", "客户类型匹配", "销售能力",
        "客户与渠道资源", "销售周期经验", "学历及其他条件",
    }
    assert any("客户开发" in item for item in result["matched_items"])

    reviewed = client.post(
        f"/api/applications/{application['id']}/screening-review",
        json={"decision": "pass", "note": "销售经历符合要求"},
    ).get_json()["data"]
    assert reviewed["review_status"] == "reviewed"
    assert reviewed["review_decision"] == "pass"

    detail = client.get(f"/api/candidates/{candidate_id}").get_json()["data"]
    assert detail["applications"][0]["screening_score"] == result["score"]
    assert detail["applications"][0]["screening_review_decision"] == "pass"


def test_missing_hard_skill_requires_manual_confirmation(client):
    login(client, "hr-001")
    job = _job(client, {
        "name": "AI应用工程师",
        "dept_name": "研发部",
        "skill_tags": "Python,FastAPI,RAG",
        "screening_rules": {
            "profile": "tech",
            "hard_skills": ["RAG"],
            "required_skills": ["Python", "FastAPI"],
            "pass_score": 70,
            "pending_score": 50,
        },
    })
    candidate_id = _candidate(client, {
        "name": "技术匹配候选人",
        "phone": "13988002222",
        "email": "tech-match@example.com",
        "tags": "Python,FastAPI,AI",
        "work_experience": [{
            "company": "互联网科技有限公司", "position": "Python工程师",
            "start": "2023-01", "end": "2025-12", "desc": "使用Python和FastAPI开发AI应用",
        }],
    })
    application = assign(client, candidate_id, job["id"])
    result = client.post(f"/api/applications/{application['id']}/screen").get_json()["data"]

    assert result["decision"] == "pending"
    assert "硬性技能待确认：RAG" in result["missing_items"]

    fetched = client.get(
        f"/api/applications/{application['id']}/screening-result",
    ).get_json()["data"]
    assert fetched["id"] == result["id"]


def test_job_match_preview_does_not_change_existing_recruitment_flow(client):
    login(client, "hr-001")
    current_job = _job(client, {
        "name": "当前应聘职位",
        "screening_rules": {"profile": "tech"},
    })
    target_job = _job(client, {
        "name": "自选匹配职位",
        "screening_rules": {"profile": "product_ops"},
    })
    candidate_id = _candidate(client, {
        "name": "职位匹配预览候选人",
        "phone": "13988006666",
        "email": "job-preview@example.com",
        "tags": "电商运营,数据分析,AI工具",
    })
    application = assign(client, candidate_id, current_job["id"])

    response = client.post(f"/api/candidates/{candidate_id}/job-match", json={
        "job_id": target_job["id"],
    })
    body = response.get_json()
    assert body["code"] == 0, body
    assert body["data"]["application_id"] is None
    assert body["data"]["job_id"] == target_job["id"]
    assert body["data"]["job_name"] == "自选匹配职位"
    assert body["data"]["match_mode"] == "job_preview"

    template_response = client.post(f"/api/candidates/{candidate_id}/job-match", json={
        "match_template": "ai_application_engineer",
    })
    template_body = template_response.get_json()
    assert template_body["code"] == 0, template_body
    assert template_body["data"]["application_id"] is None
    assert template_body["data"]["job_id"] is None
    assert template_body["data"]["job_name"] == "AI应用工程师"
    assert template_body["data"]["match_template"] == "ai_application_engineer"

    detail = client.get(f"/api/candidates/{candidate_id}").get_json()["data"]
    assert len(detail["applications"]) == 1
    assert detail["applications"][0]["id"] == application["id"]
    assert detail["applications"][0]["current_stage"] == application["current_stage"]


def test_screening_uses_hr_configured_match_items(client):
    login(client, "hr-001")
    meta = client.get(
        "/api/system/screening-match-items", query_string={"profile": "tech"},
    ).get_json()["data"]
    match_scope = next(
        item["key"] for item in meta["profiles"] if item["name"] == "AI应用工程师"
    )
    current = client.get(
        "/api/system/screening-match-items", query_string={"profile": match_scope},
    ).get_json()["data"]["items"]
    for item in current:
        response = client.put(
            f"/api/system/screening-match-items/{item['id']}", json={"enabled": False},
        )
        assert response.get_json()["code"] == 0
    custom = client.post("/api/system/screening-match-items", json={
        "profile": match_scope,
        "name": "跨境平台经验",
        "weight": 100,
        "evaluator": "custom_terms",
        "target_count": 1,
        "terms": ["TikTok Shop"],
        "enabled": True,
    }).get_json()["data"]

    job = _job(client, {
        "name": "AI应用工程师",
        "dept_name": "研发部",
        "screening_rules": {"profile": "tech", "pass_score": 75, "pending_score": 55},
    })
    candidate_id = _candidate(client, {
        "name": "跨境技术候选人",
        "phone": "13988003333",
        "email": "custom-screen@example.com",
        "tags": "负责 TikTok Shop 智能客服项目",
    })
    application = assign(client, candidate_id, job["id"])
    result = client.post(f"/api/applications/{application['id']}/screen").get_json()["data"]

    assert result["score"] == 100
    assert result["decision"] == "pass"
    assert len(result["dimensions"]) == 1
    assert result["dimensions"][0]["name"] == custom["name"]
    assert "TikTok Shop" in result["dimensions"][0]["matched"]
