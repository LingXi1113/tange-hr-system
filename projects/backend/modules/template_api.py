"""流程模板与面试评价模板 API（MongoDB 版，阶段/维度/绑定内嵌存储）。"""
from flask import Blueprint, current_app, g, request

from common.db import col, delete_doc, get_by_id, insert_doc, paginate, update_doc
from common.decorators import login_required, role_required
from common.errors import BizError
from common.logstore import write_log
from common.response import BizCode, ok, paged
from common.roles import HR, SUPER_ADMIN
from common.stages import (
    DEADLINE_BASES,
    EXPIRY_ACTIONS,
    INTERVIEW_ROUNDS,
    LOCK_DAYS_FALLBACK,
    PARAM_LOCK_DAYS_DEFAULT,
    STAGE_KEYS,
    STAGE_RULE_FALLBACK,
)

bp = Blueprint("template_api", __name__)


def _lock_defaults() -> dict:
    """阶段锁定默认天数：以系统参数为准，参数缺失时用最终兜底。"""
    doc = col("sys_params").find_one({"_id": PARAM_LOCK_DAYS_DEFAULT})
    if doc and doc.get("value"):
        import json

        try:
            return json.loads(doc["value"])
        except (TypeError, ValueError) as exc:
            current_app.logger.warning("默认锁定天数配置格式无效，将使用系统兜底值：%s", exc)
    return dict(LOCK_DAYS_FALLBACK)


# ---------------- 流程模板 ----------------

def _tpl_view(tpl: dict, with_stages: bool = False) -> dict:
    from common.db import dt

    data = {
        "id": tpl["_id"],
        "name": tpl["name"],
        "status": tpl.get("status", "active"),
        "remark": tpl.get("remark", ""),
        "stage_rules_enabled": bool(tpl.get("stage_rules_enabled", False)),
        "stage_count": len(tpl.get("stages", [])),
        "created_at": dt(tpl.get("created_at")),
        "updated_at": dt(tpl.get("updated_at")),
    }
    if with_stages:
        data["stages"] = list(tpl.get("stages", []))
    return data


def _build_stages(stage_payloads: list) -> list:
    lock_defaults = _lock_defaults()
    stages = []
    seen_orders = set()
    for idx, sp in enumerate(stage_payloads):
        stage_key = (sp.get("stage_key") or "").strip()
        name = (sp.get("name") or "").strip()
        if not stage_key or not name:
            raise BizError(BizCode.PARAM_INVALID, f"第 {idx + 1} 个阶段缺少 stage_key 或名称")
        if stage_key not in STAGE_KEYS:
            raise BizError(BizCode.PARAM_INVALID, f"未知阶段: {stage_key}")
        defaults = STAGE_RULE_FALLBACK.get(stage_key, {})
        lock_days = sp.get("lock_days")
        if lock_days is None:
            lock_days = lock_defaults.get(stage_key, defaults.get("lock_days", 0))
        try:
            lock_days = int(lock_days)
        except (TypeError, ValueError) as exc:
            raise BizError(BizCode.PARAM_INVALID, "锁定天数必须是整数") from exc
        if lock_days < 0 or lock_days > 9999:
            raise BizError(BizCode.PARAM_INVALID, "锁定天数必须在 0~9999 之间")
        unprocessed_days = sp.get("unprocessed_days", defaults.get("unprocessed_days", 0))
        try:
            unprocessed_days = int(unprocessed_days)
        except (TypeError, ValueError) as exc:
            raise BizError(BizCode.PARAM_INVALID, "未处理期限必须是整数") from exc
        if unprocessed_days < 0 or unprocessed_days > 3650:
            raise BizError(BizCode.PARAM_INVALID, "未处理期限必须在 0~3650 之间")
        reminder_days_before = sp.get("reminder_days_before", defaults.get("reminder_days_before", 0))
        try:
            reminder_days_before = int(reminder_days_before)
        except (TypeError, ValueError) as exc:
            raise BizError(BizCode.PARAM_INVALID, "提前提醒天数必须是整数") from exc
        if reminder_days_before < 0 or reminder_days_before > 3650:
            raise BizError(BizCode.PARAM_INVALID, "提前提醒天数必须在 0~3650 之间")
        expiry_action = sp.get("expiry_action", defaults.get("expiry_action", "none"))
        if expiry_action not in EXPIRY_ACTIONS:
            raise BizError(BizCode.PARAM_INVALID, f"到期动作必须是: {', '.join(EXPIRY_ACTIONS)}")
        deadline_basis = sp.get("deadline_basis", defaults.get("deadline_basis", "stage_entered"))
        if deadline_basis not in DEADLINE_BASES:
            raise BizError(BizCode.PARAM_INVALID, "期限起算方式不合法")
        sort_order = int(sp.get("sort_order", idx + 1))
        if not sp.get("optional_flag") and sort_order in seen_orders:
            raise BizError(BizCode.PARAM_INVALID, "阶段顺序重复")
        seen_orders.add(sort_order)
        stages.append({
            "stage_key": stage_key,
            "name": name,
            "category": sp.get("category", ""),
            "sort_order": sort_order,
            "lock_days": lock_days,
            "unprocessed_days": unprocessed_days,
            "reminder_days_before": reminder_days_before,
            "expiry_action": expiry_action,
            "deadline_basis": deadline_basis,
            "required": bool(sp.get("required", True)),
            "skippable": bool(sp.get("skippable", False)),
            "requires_interview": bool(sp.get("requires_interview", defaults.get("requires_interview", False))),
            "requires_feedback": bool(sp.get("requires_feedback", defaults.get("requires_feedback", False))),
            "auto_reminder": bool(sp.get("auto_reminder", bool(sp.get("reminder_type")))),
            "enter_talent_pool": bool(sp.get("enter_talent_pool", defaults.get("enter_talent_pool", False))),
            "reminder_type": sp.get("reminder_type", ""),
            "optional_flag": bool(sp.get("optional_flag", False)),
        })
    return stages


@bp.get("/api/pipeline-templates")
@login_required
def list_pipeline_templates():
    query = {}
    if request.args.get("status"):
        query["status"] = request.args["status"]
    items = col("pipeline_templates").find(query).sort("_id", 1)
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 10)), 1), 100)
    sliced, total, page, page_size = paginate(items, page, page_size)
    return paged([_tpl_view(t) for t in sliced], total, page, page_size)


@bp.get("/api/pipeline-templates/<int:template_id>")
@login_required
def get_pipeline_template(template_id: int):
    tpl = get_by_id("pipeline_templates", template_id)
    if tpl is None:
        raise BizError(BizCode.NOT_FOUND, "流程模板不存在")
    return ok(_tpl_view(tpl, with_stages=True))


@bp.post("/api/pipeline-templates")
@role_required(SUPER_ADMIN)
def create_pipeline_template():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    stages_payload = payload.get("stages") or []
    if not name:
        raise BizError(BizCode.PARAM_INVALID, "模板名称必填")
    if not stages_payload:
        raise BizError(BizCode.PARAM_INVALID, "至少需要一个阶段")
    tpl = insert_doc("pipeline_templates", {
        "name": name,
        "status": "active",
        "remark": payload.get("remark", ""),
        "stage_rules_enabled": bool(payload.get(
            "stage_rules_enabled",
            any(any(key in stage for key in (
                    "unprocessed_days", "expiry_action", "requires_interview", "requires_feedback",
                    "auto_reminder", "enter_talent_pool", "deadline_basis", "reminder_days_before",
            )) for stage in stages_payload),
        )),
        "stages": _build_stages(stages_payload),
    })
    write_log("pipeline_template", "create", g.current_user.user_id, g.current_user.name,
              biz_id=str(tpl["_id"]), detail=name)
    return ok(_tpl_view(tpl, with_stages=True))


@bp.put("/api/pipeline-templates/<int:template_id>")
@role_required(SUPER_ADMIN)
def update_pipeline_template(template_id: int):
    tpl = get_by_id("pipeline_templates", template_id)
    if tpl is None:
        raise BizError(BizCode.NOT_FOUND, "流程模板不存在")
    payload = request.get_json(silent=True) or {}
    fields = {}
    if "name" in payload:
        if not (payload["name"] or "").strip():
            raise BizError(BizCode.PARAM_INVALID, "模板名称不能为空")
        fields["name"] = payload["name"].strip()
    if "remark" in payload:
        fields["remark"] = payload["remark"]
    if "stage_rules_enabled" in payload:
        fields["stage_rules_enabled"] = bool(payload["stage_rules_enabled"])
    if "stages" in payload:
        # 修改不影响已进入流程的历史阶段与既有锁定（历史数据在应聘记录侧）
        fields["stages"] = _build_stages(payload["stages"] or [])
    update_doc("pipeline_templates", template_id, fields)
    tpl.update(fields)
    write_log("pipeline_template", "update", g.current_user.user_id, g.current_user.name,
              biz_id=str(template_id))
    return ok(_tpl_view(tpl, with_stages=True))


@bp.put("/api/pipeline-templates/<int:template_id>/status")
@role_required(SUPER_ADMIN)
def set_pipeline_template_status(template_id: int):
    tpl = get_by_id("pipeline_templates", template_id)
    if tpl is None:
        raise BizError(BizCode.NOT_FOUND, "流程模板不存在")
    payload = request.get_json(silent=True) or {}
    status = payload.get("status", "")
    if status not in ("active", "disabled"):
        raise BizError(BizCode.PARAM_INVALID, "status 必须是 active/disabled")
    update_doc("pipeline_templates", template_id, {"status": status})
    tpl["status"] = status
    write_log("pipeline_template", f"status_{status}", g.current_user.user_id,
              g.current_user.name, biz_id=str(template_id))
    return ok(_tpl_view(tpl))


@bp.delete("/api/pipeline-templates/<int:template_id>")
@role_required(SUPER_ADMIN)
def delete_pipeline_template(template_id: int):
    tpl = get_by_id("pipeline_templates", template_id)
    if tpl is None:
        raise BizError(BizCode.NOT_FOUND, "流程模板不存在")
    # 被进行中职位引用时禁止删除（职位模块接入后的校验点）
    if col("jobs").find_one({"template_id": template_id,
                             "status": {"$in": ["pending_publish", "recruiting", "paused"]}}):
        raise BizError(BizCode.STATE_INVALID, "模板被进行中的职位引用，仅允许停用")
    delete_doc("pipeline_templates", template_id)
    write_log("pipeline_template", "delete", g.current_user.user_id, g.current_user.name,
              biz_id=str(template_id))
    return ok(None)


# ---------------- 面试评价模板 ----------------

def _eval_view(tpl: dict, with_detail: bool = False) -> dict:
    from common.db import dt

    dimensions = tpl.get("dimensions", [])
    bindings = tpl.get("bindings", [])
    data = {
        "id": tpl["_id"],
        "name": tpl["name"],
        "remark": tpl.get("remark", ""),
        "dimension_names": [d["name"] for d in dimensions],
        "jobs": sorted({b["job_name"] for b in bindings if b.get("job_name")}),
        "rounds": sorted({b["round"] for b in bindings}),
        "updated_at": dt(tpl.get("updated_at")),
    }
    if with_detail:
        data["dimensions"] = list(dimensions)
        data["bindings"] = list(bindings)
    return data


def _build_eval_detail(payload: dict, existing: dict):
    result = {}
    dimensions = payload.get("dimensions")
    if dimensions is not None:
        names = [(d.get("name") or "").strip() if isinstance(d, dict) else str(d).strip()
                 for d in dimensions]
        names = [n for n in names if n]
        if not names:
            raise BizError(BizCode.PARAM_INVALID, "至少需要一个评分维度")
        result["dimensions"] = [{"name": n, "sort_order": idx + 1}
                                for idx, n in enumerate(names)]
    bindings = payload.get("bindings")
    if bindings is not None:
        new_bindings = []
        for b in bindings:
            round_ = (b.get("round") or "").strip()
            if round_ not in INTERVIEW_ROUNDS:
                raise BizError(BizCode.PARAM_INVALID, f"未知面试轮次: {round_}")
            new_bindings.append({
                "job_id": str(b.get("job_id") or ""),
                "job_name": (b.get("job_name") or "").strip(),
                "round": round_,
            })
        result["bindings"] = new_bindings
    return result


@bp.get("/api/eval-templates")
@login_required
def list_eval_templates():
    query = {}
    keyword = (request.args.get("keyword") or "").strip()
    if keyword:
        import re as re_mod

        query["name"] = {"$regex": re_mod.escape(keyword)}
    items = list(col("eval_templates").find(query).sort("_id", 1))
    round_ = request.args.get("round", "")
    if round_:
        items = [t for t in items if any(b["round"] == round_ for b in t.get("bindings", []))]
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 10)), 1), 100)
    sliced, total, page, page_size = paginate(items, page, page_size)
    return paged([_eval_view(t) for t in sliced], total, page, page_size)


@bp.get("/api/eval-templates/<int:template_id>")
@login_required
def get_eval_template(template_id: int):
    tpl = get_by_id("eval_templates", template_id)
    if tpl is None:
        raise BizError(BizCode.NOT_FOUND, "评价模板不存在")
    return ok(_eval_view(tpl, with_detail=True))


@bp.post("/api/eval-templates")
@role_required(HR)
def create_eval_template():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        raise BizError(BizCode.PARAM_INVALID, "模板名称必填")
    if payload.get("dimensions") is None:
        payload = {**payload, "dimensions": ["专业能力", "沟通表达", "业务理解", "团队协作", "价值观匹配"]}
    doc = {
        "name": name,
        "remark": payload.get("remark", ""),
        "dimensions": [],
        "bindings": [],
    }
    doc.update(_build_eval_detail(payload, doc))
    tpl = insert_doc("eval_templates", doc)
    write_log("eval_template", "create", g.current_user.user_id, g.current_user.name,
              biz_id=str(tpl["_id"]), detail=name)
    return ok(_eval_view(tpl, with_detail=True))


@bp.put("/api/eval-templates/<int:template_id>")
@role_required(HR)
def update_eval_template(template_id: int):
    tpl = get_by_id("eval_templates", template_id)
    if tpl is None:
        raise BizError(BizCode.NOT_FOUND, "评价模板不存在")
    payload = request.get_json(silent=True) or {}
    fields = {}
    if "name" in payload:
        if not (payload["name"] or "").strip():
            raise BizError(BizCode.PARAM_INVALID, "模板名称不能为空")
        fields["name"] = payload["name"].strip()
    if "remark" in payload:
        fields["remark"] = payload["remark"]
    fields.update(_build_eval_detail(payload, tpl))
    update_doc("eval_templates", template_id, fields)
    tpl.update(fields)
    write_log("eval_template", "update", g.current_user.user_id, g.current_user.name,
              biz_id=str(template_id))
    return ok(_eval_view(tpl, with_detail=True))


@bp.delete("/api/eval-templates/<int:template_id>")
@role_required(HR)
def delete_eval_template(template_id: int):
    tpl = get_by_id("eval_templates", template_id)
    if tpl is None:
        raise BizError(BizCode.NOT_FOUND, "评价模板不存在")
    # 面试模块接入后：被面试记录引用时禁止删除
    delete_doc("eval_templates", template_id)
    write_log("eval_template", "delete", g.current_user.user_id, g.current_user.name,
              biz_id=str(template_id))
    return ok(None)
