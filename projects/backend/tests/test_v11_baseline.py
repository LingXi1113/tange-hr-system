"""PRD v1.1 基线：默认九阶段流程、旧阶段兼容映射、种子数据。"""
from conftest import login
from helpers import assign, ensure_hr, make_candidate, make_job, publish_job

V11_STAGES = [
    "new_resume", "pending_screen", "hr_screen_passed", "pending_interview",
    "interviewing", "interview_passed", "offer_pending", "pending_onboard", "onboarded",
]
LEGACY_STAGES = ["business_screen", "interview_1", "interview_2", "interview_3",
                 "hr_interview", "offer_approval", "offer"]


def test_seed_creates_v11_template_and_disables_legacy(app):
    """种子：新建 v1.1 默认模板；旧默认模板停用但保留（不删除）。"""
    with app.app_context():
        from common.db import col
        from seed import seed_demo_data

        col("pipeline_templates").insert_one({
            "_id": 9001, "name": "默认招聘流程模板", "status": "active",
            "stages": [], "remark": "v1.0",
        })
        seed_demo_data()
        v11 = col("pipeline_templates").find_one({"name": "默认招聘流程模板（v1.1）"})
        assert v11 is not None and v11["status"] == "active"
        main = [s for s in v11["stages"] if not s["optional_flag"]]
        assert [s["stage_key"] for s in main] == V11_STAGES
        legacy = col("pipeline_templates").find_one({"_id": 9001})
        assert legacy is not None and legacy["status"] == "disabled"  # 保留但停用


def test_template_api_accepts_new_and_legacy_stages(client):
    """模板校验：v1.1 新阶段与 v1.0 旧阶段都合法（兼容）。"""
    login(client, "super-admin-001")
    for key in ["pending_screen", "offer_pending"] + LEGACY_STAGES[:2]:
        resp = client.post("/api/pipeline-templates", json={
            "name": f"模板-{key}",
            "stages": [{"stage_key": key, "name": key, "sort_order": 1}],
        })
        assert resp.get_json()["code"] == 0, key


def test_board_with_v11_template(client):
    """v1.1 模板职位的看板：9 主干列 + 淘汰/放弃/人才库；卡片可沿新流程流转。"""
    ensure_hr(client)
    login(client, "super-admin-001")
    tpl = client.post("/api/pipeline-templates", json={
        "name": "v1.1流程",
        "stages": [{"stage_key": k, "name": k, "sort_order": i + 1}
                   for i, k in enumerate(V11_STAGES)],
    }).get_json()["data"]["id"]
    login(client, "hr-001")
    job = make_job(client, name="v1.1职位", template_id=tpl)
    publish_job(client, job["id"])
    cid = make_candidate(client, phone="13500001111", email="v11@example.com")
    app = assign(client, cid, job["id"])

    data = client.get("/api/pipeline/board", query_string={"job_id": job["id"]}).get_json()["data"]
    keys = [c["stage_key"] for c in data["columns"]]
    assert keys[:9] == V11_STAGES
    assert keys[-3:] == ["eliminated", "abandoned", "talent_pool"]

    # 沿新流程流转（含放弃终态）
    version = app["version"]
    # 分配职位后按当前规则直接进入 HR 筛选阶段。
    for target in ["pending_interview"]:
        resp = client.post(f"/api/applications/{app['id']}/move",
                           json={"to_stage": target, "reason": "推进", "version": version})
        assert resp.get_json()["code"] == 0, target
        version = resp.get_json()["data"]["version"]
    resp = client.post(f"/api/applications/{app['id']}/move",
                       json={"to_stage": "abandoned", "reason": "候选人放弃", "version": version})
    assert resp.get_json()["code"] == 0
    assert resp.get_json()["data"]["current_stage"] == "abandoned"


def test_legacy_stage_display_compatible(client):
    """旧阶段的历史应聘记录在看板/流转名称上仍可正确映射。"""
    from common.stages import STAGE_NAMES

    assert STAGE_NAMES["business_screen"] == "业务复筛"
    assert STAGE_NAMES["interview_1"] == "一面"
    assert STAGE_NAMES["offer_approval"] == "录用审批"
    assert STAGE_NAMES["offer_pending"] == "Offer中"
    assert STAGE_NAMES["abandoned"] == "放弃"
