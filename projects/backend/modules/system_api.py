"""系统设置（MongoDB 版）：系统参数、字典、Offer 审批人配置。"""
import json

from flask import Blueprint, current_app, g, request

from common.db import col, delete_doc, get_by_id, insert_doc, next_id, paginate, update_doc
from common.decorators import login_required, role_required
from common.errors import BizError
from common.logstore import write_log
from common.response import BizCode, ok, paged
from common.roles import HR
from common.stages import (
    LOCK_DAYS_FALLBACK,
    ONBOARDING_CHECKLIST_FALLBACK,
    PARAM_LOCK_DAYS_DEFAULT,
    PARAM_ONBOARDING_CHECKLIST_DEFAULT,
)
from platform_identity import get_identity

bp = Blueprint("system_api", __name__, url_prefix="/api/system")

PARAM_VALIDATORS = {
    PARAM_LOCK_DAYS_DEFAULT: "json_int_map",
    PARAM_ONBOARDING_CHECKLIST_DEFAULT: "json_str_list",
}


# ---------------- 系统参数 ----------------

def _param_value(key: str) -> str:
    doc = col("sys_params").find_one({"_id": key})
    return doc["value"] if doc else ""


def _param_json(key: str, default):
    raw = _param_value(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _validate_param(key: str, value: str):
    kind = PARAM_VALIDATORS.get(key)
    if kind == "json_int_map":
        try:
            data = json.loads(value)
        except (TypeError, ValueError):
            raise BizError(BizCode.PARAM_INVALID, f"参数 {key} 必须是 JSON 对象")
        if not isinstance(data, dict) or not all(
            isinstance(v, int) and v >= 0 for v in data.values()
        ):
            raise BizError(BizCode.PARAM_INVALID, f"参数 {key} 的值必须是非负整数")
    elif kind == "json_str_list":
        try:
            data = json.loads(value)
        except (TypeError, ValueError):
            raise BizError(BizCode.PARAM_INVALID, f"参数 {key} 必须是 JSON 数组")
        if not isinstance(data, list) or not all(isinstance(v, str) and v for v in data):
            raise BizError(BizCode.PARAM_INVALID, f"参数 {key} 的值必须是非空字符串数组")


@bp.get("/params")
@login_required
def list_params():
    data = {}
    for key in PARAM_VALIDATORS:
        raw = _param_value(key)
        if not raw:
            data[key] = (
                dict(LOCK_DAYS_FALLBACK) if key == PARAM_LOCK_DAYS_DEFAULT
                else list(ONBOARDING_CHECKLIST_FALLBACK)
            )
        else:
            data[key] = json.loads(raw)
    return ok(data)


@bp.put("/params")
@role_required(HR)
def update_params():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    if not items:
        raise BizError(BizCode.PARAM_INVALID, "缺少 items")
    for item in items:
        key, value = item.get("key", ""), item.get("value")
        if key not in PARAM_VALIDATORS:
            raise BizError(BizCode.PARAM_INVALID, f"不支持的参数: {key}")
        raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        _validate_param(key, raw)
        col("sys_params").update_one(
            {"_id": key}, {"$set": {"value": raw}}, upsert=True)
    write_log("system", "update_params", g.current_user.user_id, g.current_user.name,
              detail=json.dumps([i.get("key") for i in items], ensure_ascii=False))
    return ok(None)


# ---------------- 字典 ----------------

DICT_TYPES = [
    "source_channel", "request_type", "job_level",
    "eliminate_reason", "pool_category", "job_type",
]


def _dict_to_view(d: dict) -> dict:
    return {
        "id": d["_id"], "type": d["type"], "code": d["code"],
        "name": d["name"], "enabled": d["enabled"], "sort": d["sort"],
    }


@bp.get("/dicts")
@login_required
def list_dicts():
    type_ = request.args.get("type", "")
    query = {"type": type_} if type_ else {}
    items = col("dict_items").find(query).sort([("type", 1), ("sort", 1), ("_id", 1)])
    return ok([_dict_to_view(d) for d in items])


@bp.post("/dicts")
@role_required(HR)
def create_dict():
    payload = request.get_json(silent=True) or {}
    type_, code, name = payload.get("type", ""), payload.get("code", ""), payload.get("name", "")
    if not type_ or not code or not name:
        raise BizError(BizCode.PARAM_INVALID, "type/code/name 必填")
    if type_ not in DICT_TYPES:
        raise BizError(BizCode.PARAM_INVALID, f"不支持的字典类型: {type_}")
    if col("dict_items").find_one({"type": type_, "code": code}):
        raise BizError(BizCode.DUPLICATED, "该字典编码已存在")
    doc = insert_doc("dict_items", {
        "type": type_, "code": code, "name": name,
        "enabled": bool(payload.get("enabled", True)),
        "sort": int(payload.get("sort", 0)),
    })
    write_log("dict", "create", g.current_user.user_id, g.current_user.name,
              biz_id=str(doc["_id"]), detail=f"{type_}/{code}")
    return ok(_dict_to_view(doc))


@bp.put("/dicts/<int:item_id>")
@role_required(HR)
def update_dict(item_id: int):
    item = get_by_id("dict_items", item_id)
    if item is None:
        raise BizError(BizCode.NOT_FOUND, "字典条目不存在")
    payload = request.get_json(silent=True) or {}
    fields = {}
    if "name" in payload:
        if not payload["name"]:
            raise BizError(BizCode.PARAM_INVALID, "名称不能为空")
        fields["name"] = payload["name"]
    if "enabled" in payload:
        fields["enabled"] = bool(payload["enabled"])
    if "sort" in payload:
        fields["sort"] = int(payload["sort"])
    update_doc("dict_items", item_id, fields)
    item.update(fields)
    write_log("dict", "update", g.current_user.user_id, g.current_user.name, biz_id=str(item_id))
    return ok(_dict_to_view(item))


# ---------------- Offer 审批人配置 ----------------

APPROVER_FIELDS = [
    ("org_approver_id", "org_approver_name", "组织统筹审批人"),
    ("gm_id", "gm_name", "总经理审批人"),
    ("chairman_id", "chairman_name", "董事长审批人"),
    ("offer_sender_id", "offer_sender_name", "Offer发送专人"),
]


def _approver_view(doc: dict) -> dict:
    from common.db import dt

    return {
        "org_approver": {"user_id": doc.get("org_approver_id", ""), "name": doc.get("org_approver_name", "")},
        "gm": {"user_id": doc.get("gm_id", ""), "name": doc.get("gm_name", "")},
        "chairman": {"user_id": doc.get("chairman_id", ""), "name": doc.get("chairman_name", "")},
        "offer_sender": {"user_id": doc.get("offer_sender_id", ""), "name": doc.get("offer_sender_name", "")},
        "updated_at": dt(doc.get("updated_at")),
    }


def _get_approver_config() -> dict:
    doc = col("offer_approver_config").find_one({"_id": 1})
    if doc is None:
        doc = {"_id": 1}
        col("offer_approver_config").insert_one(doc)
    return doc


@bp.get("/offer-approvers")
@login_required
def get_offer_approvers():
    return ok(_approver_view(_get_approver_config()))


@bp.put("/offer-approvers")
@role_required(HR)
def update_offer_approvers():
    payload = request.get_json(silent=True) or {}
    identity = get_identity(current_app)
    _get_approver_config()  # 确保单行配置存在
    fields = {}
    for id_field, name_field, label in APPROVER_FIELDS:
        user_id = (payload.get(id_field) or "").strip()
        if not user_id:
            raise BizError(BizCode.PARAM_INVALID, f"{label}不能为空")
        user = identity.get_user(user_id)
        if user is None:
            raise BizError(BizCode.PARAM_INVALID, f"{label}用户不存在: {user_id}")
        fields[id_field] = user.user_id
        fields[name_field] = user.name  # 名称快照
    update_doc("offer_approver_config", 1, fields)
    write_log("offer_approver", "update", g.current_user.user_id, g.current_user.name,
              detail="审批链配置变更，立即生效，不影响进行中审批历史节点")
    return ok(_approver_view(_get_approver_config()))
