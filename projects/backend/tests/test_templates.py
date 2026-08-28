"""流程模板与面试评价模板。"""
from conftest import login


def _create_template(client, stages=None):
    stages = stages or [
        {"stage_key": "new_resume", "name": "新简历", "sort_order": 1, "category": "开始"},
        {"stage_key": "business_screen", "name": "业务复筛", "sort_order": 2, "category": "筛选"},
    ]
    login(client, "super-admin-001")
    resp = client.post("/api/pipeline-templates", json={"name": "测试流程模板", "stages": stages})
    login(client, "hr-001")
    body = resp.get_json()
    assert body["code"] == 0, body
    return body["data"]


def test_lock_days_default_from_sys_param(client):
    """阶段锁定默认天数取自系统参数（不写死）。"""
    login(client, "hr-001")
    client.put("/api/system/params", json={
        "items": [{"key": "lock_days_default", "value": {"new_resume": 2, "business_screen": 4}}],
    })
    tpl = _create_template(client)
    locks = {s["stage_key"]: s["lock_days"] for s in tpl["stages"]}
    assert locks["new_resume"] == 2
    assert locks["business_screen"] == 4


def test_pipeline_template_crud(client):
    login(client, "hr-001")
    tpl = _create_template(client)
    tid = tpl["id"]

    got = client.get(f"/api/pipeline-templates/{tid}").get_json()["data"]
    assert got["name"] == "测试流程模板"
    assert len(got["stages"]) == 2

    # 列表
    lst = client.get("/api/pipeline-templates").get_json()["data"]
    assert lst["total"] >= 1

    # 修改：替换阶段并显式指定锁定天数
    login(client, "super-admin-001")
    upd = client.put(f"/api/pipeline-templates/{tid}", json={
        "name": "改名模板",
        "stages": [
            {"stage_key": "new_resume", "name": "新简历", "sort_order": 1, "lock_days": 6},
        ],
    }).get_json()["data"]
    assert upd["name"] == "改名模板"
    assert upd["stages"][0]["lock_days"] == 6

    # 停用
    st = client.put(f"/api/pipeline-templates/{tid}/status", json={"status": "disabled"})
    assert st.get_json()["data"]["status"] == "disabled"

    # 删除
    assert client.delete(f"/api/pipeline-templates/{tid}").get_json()["code"] == 0
    assert client.get(f"/api/pipeline-templates/{tid}").status_code == 200
    assert client.get(f"/api/pipeline-templates/{tid}").get_json()["code"] == 1002


def test_pipeline_template_validation(client):
    login(client, "super-admin-001")
    # 未知阶段
    bad = client.post("/api/pipeline-templates", json={
        "name": "x", "stages": [{"stage_key": "nope", "name": "x"}],
    })
    assert bad.get_json()["code"] == 1001
    # 负锁定天数
    bad2 = client.post("/api/pipeline-templates", json={
        "name": "x", "stages": [{"stage_key": "new_resume", "name": "新简历", "lock_days": -1}],
    })
    assert bad2.get_json()["code"] == 1001
    # 名称必填
    bad3 = client.post("/api/pipeline-templates", json={"name": "", "stages": [{"stage_key": "new_resume", "name": "x"}]})
    assert bad3.get_json()["code"] == 1001
    # 非 HR 不可创建
    login(client, "screen-001")
    resp = client.post("/api/pipeline-templates", json={
        "name": "x", "stages": [{"stage_key": "new_resume", "name": "x"}],
    })
    assert resp.get_json()["code"] == 1006


def test_pipeline_template_writes_are_super_admin_only_and_shared_with_hr(client):
    login(client, "super-admin-001")
    created = client.post("/api/pipeline-templates", json={
        "name": "共享面试流程",
        "stages": [{"stage_key": "new_resume", "name": "新简历", "sort_order": 1}],
    }).get_json()["data"]

    login(client, "hr-001")
    forbidden = client.put(f"/api/pipeline-templates/{created['id']}", json={"name": "HR不应修改"})
    assert forbidden.get_json()["code"] == 1006
    visible = client.get(f"/api/pipeline-templates/{created['id']}").get_json()["data"]
    assert visible["name"] == "共享面试流程"

    login(client, "super-admin-001")
    updated = client.put(f"/api/pipeline-templates/{created['id']}", json={"name": "管理员已更新"})
    assert updated.get_json()["code"] == 0
    login(client, "hr-001")
    shared = client.get(f"/api/pipeline-templates/{created['id']}").get_json()["data"]
    assert shared["name"] == "管理员已更新"


def _create_eval(client, **overrides):
    payload = {
        "name": "技术一面评价表",
        "dimensions": ["专业能力", "沟通表达"],
        "bindings": [{"job_id": "", "job_name": "", "round": "一面"}],
    }
    payload.update(overrides)
    resp = client.post("/api/eval-templates", json=payload)
    body = resp.get_json()
    assert body["code"] == 0, body
    return body["data"]


def test_eval_template_crud(client):
    login(client, "hr-001")
    tpl = _create_eval(client)
    tid = tpl["id"]
    assert tpl["dimension_names"] == ["专业能力", "沟通表达"]
    assert tpl["rounds"] == ["一面"]

    got = client.get(f"/api/eval-templates/{tid}").get_json()["data"]
    assert len(got["dimensions"]) == 2
    assert got["bindings"][0]["round"] == "一面"

    # 修改维度与绑定
    upd = client.put(f"/api/eval-templates/{tid}", json={
        "dimensions": ["专业能力", "价值观匹配", "风险提示"],
        "bindings": [{"round": "二面"}, {"round": "HR面试", "job_name": "Java后端工程师"}],
    }).get_json()["data"]
    assert upd["dimension_names"] == ["专业能力", "价值观匹配", "风险提示"]
    assert sorted(upd["rounds"]) == ["HR面试", "二面"]

    # 按轮次过滤
    lst = client.get("/api/eval-templates", query_string={"round": "二面"}).get_json()["data"]
    assert any(t["id"] == tid for t in lst["list"])

    # 删除
    assert client.delete(f"/api/eval-templates/{tid}").get_json()["code"] == 0


def test_eval_template_validation(client):
    login(client, "hr-001")
    # 默认维度
    tpl = _create_eval(client, dimensions=None, bindings=[])
    assert tpl["dimension_names"] == ["专业能力", "沟通表达", "业务理解", "团队协作", "价值观匹配"]
    # 非法轮次
    bad = client.post("/api/eval-templates", json={
        "name": "x", "dimensions": ["专业能力"], "bindings": [{"round": "终终面"}],
    })
    assert bad.get_json()["code"] == 1001
    # 空维度
    bad2 = client.post("/api/eval-templates", json={"name": "x", "dimensions": []})
    assert bad2.get_json()["code"] == 1001
