"""招聘需求管理（MongoDB 版）：CRUD + 状态机（草稿→招聘中→暂停→已完成→已关闭）。"""
from datetime import datetime

from flask import Blueprint, g, request

from common.db import col, delete_doc, get_by_id, insert_doc, paginate, update_doc, date_str, dt
from common.decorators import login_required, role_required
from common.errors import BizError
from common.logstore import write_log
from common.response import BizCode, ok, paged
from common.roles import HR
from common.status import (
    REQ_CLOSED, REQ_COMPLETED, REQ_DRAFT, REQ_PAUSED, REQ_PENDING_CONFIRM,
    REQ_RECRUITING, REQUIREMENT_FLOW,
)

bp = Blueprint("requirement_api", __name__, url_prefix="/api/requirements")

REQUIRED_SUBMIT_FIELDS = ["name", "dept_id", "headcount", "request_type", "priority", "requirements"]
STATUS_ACTION = {
    "submit": REQ_PENDING_CONFIRM,   # PRD v1.1：提交进入待确认
    "confirm": REQ_RECRUITING,       # 确认后进入招聘中
    "pause": REQ_PAUSED,
    "resume": REQ_RECRUITING,
    "complete": REQ_COMPLETED,
    "close": REQ_CLOSED,
}


def _get_or_404(req_id: int) -> dict:
    req = get_by_id("requirements", req_id)
    if req is None:
        raise BizError(BizCode.NOT_FOUND, "招聘需求不存在")
    return req


def _req_view(req: dict) -> dict:
    linked_job = col("jobs").find_one({"requirement_id": req["_id"]}, sort=[("_id", 1)])
    return {
        "id": req["_id"], "name": req.get("name", ""),
        "dept_id": req.get("dept_id", ""), "dept_name": req.get("dept_name", ""),
        "headcount": req.get("headcount", 0), "request_type": req.get("request_type", ""),
        "priority": req.get("priority", ""), "due_date": date_str(req.get("due_date")),
        "owner_id": req.get("owner_id", ""), "owner_name": req.get("owner_name", ""),
        "reason": req.get("reason", ""), "requirements": req.get("requirements", ""),
        "remark": req.get("remark", ""), "status": req.get("status", REQ_DRAFT),
        # 兼容需求编辑页的单选框；需求详情仍返回全部关联职位。
        "job_id": linked_job["_id"] if linked_job else None,
        "created_at": dt(req.get("created_at")), "updated_at": dt(req.get("updated_at")),
    }


_JOB_ID_MISSING = object()


def _requested_job_id(payload: dict):
    """读取并校验需求表单中的职位 ID；未提交该字段时保持原有关联不变。"""
    if "job_id" not in payload:
        return _JOB_ID_MISSING
    raw = payload.get("job_id")
    if raw in (None, "", 0, "0"):
        return None
    try:
        job_id = int(raw)
    except (TypeError, ValueError):
        raise BizError(BizCode.PARAM_INVALID, "关联职位 ID 必须是整数")
    job = get_by_id("jobs", job_id)
    if job is None:
        raise BizError(BizCode.NOT_FOUND, "关联职位不存在")
    return job_id


def _validate_job_link(job_id: int, req_id: int = None):
    """避免把已归属其他招聘需求的职位静默改挂到当前需求。"""
    if job_id is None:
        return
    job = get_by_id("jobs", job_id)
    if job is None:
        raise BizError(BizCode.NOT_FOUND, "关联职位不存在")
    current_req_id = job.get("requirement_id")
    if current_req_id and int(current_req_id) != int(req_id or 0):
        raise BizError(BizCode.STATE_INVALID, "该职位已关联其他招聘需求，请先解除原关联")


def _link_job_to_requirement(job_id: int, req_id: int):
    if job_id is None:
        return
    _validate_job_link(job_id, req_id)
    update_doc("jobs", job_id, {"requirement_id": req_id})
    write_log("job", "link_requirement", g.current_user.user_id, g.current_user.name,
              biz_id=str(job_id), detail=f"关联招聘需求 #{req_id}")


def _unlink_primary_job(req_id: int):
    """解除需求表单当前展示的职位；其余通过职位页建立的关联保留。"""
    job = col("jobs").find_one({"requirement_id": req_id}, sort=[("_id", 1)])
    if job is None:
        return
    update_doc("jobs", job["_id"], {"requirement_id": None})
    write_log("job", "unlink_requirement", g.current_user.user_id, g.current_user.name,
              biz_id=str(job["_id"]), detail=f"解除招聘需求 #{req_id}")


def _fill(req: dict, payload: dict) -> dict:
    fields = {}
    for field in ["name", "dept_id", "dept_name", "request_type", "priority",
                  "owner_id", "owner_name", "reason", "requirements", "remark"]:
        if field in payload:
            fields[field] = payload[field]
    if "headcount" in payload:
        try:
            headcount = int(payload["headcount"])
        except (TypeError, ValueError):
            raise BizError(BizCode.PARAM_INVALID, "招聘人数必须是整数")
        if headcount <= 0:
            raise BizError(BizCode.PARAM_INVALID, "招聘人数必须大于 0")
        fields["headcount"] = headcount
    if "due_date" in payload:
        raw = payload["due_date"]
        if raw:
            try:
                # MongoDB 仅接受 datetime：日期存为当天零点
                fields["due_date"] = datetime.strptime(raw, "%Y-%m-%d")
            except ValueError:
                raise BizError(BizCode.PARAM_INVALID, "期望到岗日期格式应为 YYYY-MM-DD")
        else:
            fields["due_date"] = None
    req.update(fields)
    return fields


def _validate_submit(req: dict):
    missing = [f for f in REQUIRED_SUBMIT_FIELDS if not req.get(f)]
    if missing:
        raise BizError(BizCode.PARAM_INVALID, f"缺少必填字段: {', '.join(missing)}")


@bp.get("")
@login_required
def list_requirements():
    args = request.args
    query = {}
    if args.get("status"):
        query["status"] = args["status"]
    if args.get("dept_id"):
        query["dept_id"] = args["dept_id"]
    if args.get("priority"):
        query["priority"] = args["priority"]
    if args.get("owner_id"):
        query["owner_id"] = args["owner_id"]
    if args.get("keyword"):
        query["name"] = {"$regex": args["keyword"]}
    created_filter = {}
    if args.get("created_from"):
        created_filter["$gte"] = datetime.strptime(args["created_from"], "%Y-%m-%d")
    if args.get("created_to"):
        created_filter["$lte"] = datetime.strptime(args["created_to"], "%Y-%m-%d") \
            .replace(hour=23, minute=59, second=59)
    if created_filter:
        query["created_at"] = created_filter
    items = col("requirements").find(query).sort("_id", -1)
    page = max(int(args.get("page", 1)), 1)
    page_size = min(max(int(args.get("page_size", 10)), 1), 100)
    sliced, total, page, page_size = paginate(items, page, page_size)
    return paged([_req_view(r) for r in sliced], total, page, page_size)


@bp.get("/<int:req_id>")
@login_required
def get_requirement(req_id: int):
    req = _get_or_404(req_id)
    data = _req_view(req)
    jobs = list(col("jobs").find({"requirement_id": req_id}).sort("_id", 1))
    data["jobs"] = [{
        "id": j["_id"], "name": j.get("name", ""), "code": j.get("code", ""),
        "status": j.get("status", ""), "headcount": j.get("headcount", 0),
    } for j in jobs]
    job_ids = [j["_id"] for j in jobs]
    stats = {"total": 0, "stage_distribution": {}}
    if job_ids:
        apps = list(col("applications").find({"job_id": {"$in": job_ids}}))
        stats["total"] = len(apps)
        for app in apps:
            stage = app.get("current_stage", "")
            stats["stage_distribution"][stage] = stats["stage_distribution"].get(stage, 0) + 1
    data["candidate_stats"] = stats
    logs = list(col("operation_logs").find({"biz_type": "requirement", "biz_id": str(req_id)})
                .sort("_id", -1).limit(50))
    data["operation_logs"] = [{
        "action": l["action"], "operator_name": l.get("operator_name", ""),
        "detail": l.get("detail", ""), "created_at": dt(l.get("created_at")),
    } for l in logs]
    return ok(data)


@bp.post("")
@role_required(HR)
def create_requirement():
    payload = request.get_json(silent=True) or {}
    requested_job_id = _requested_job_id(payload)
    if requested_job_id is not _JOB_ID_MISSING:
        _validate_job_link(requested_job_id)
    req = {
        "status": REQ_DRAFT,
        "owner_id": payload.get("owner_id") or g.current_user.user_id,
        "owner_name": payload.get("owner_name") or g.current_user.name,
        "name": "", "dept_id": "", "dept_name": "", "headcount": 0,
        "request_type": "", "priority": "", "due_date": None,
        "reason": "", "requirements": "", "remark": "",
    }
    fields = _fill(req, payload)
    if not payload.get("save_as_draft"):
        _validate_submit(req)
        req["status"] = REQ_PENDING_CONFIRM  # PRD v1.1：提交后进入待确认
    doc = insert_doc("requirements", req)
    if requested_job_id is not _JOB_ID_MISSING:
        _link_job_to_requirement(requested_job_id, doc["_id"])
    write_log("requirement", "create_draft" if doc["status"] == REQ_DRAFT else "submit",
              g.current_user.user_id, g.current_user.name,
              biz_id=str(doc["_id"]),
              detail=f"{doc.get('name', '')}; 关联职位 #{requested_job_id}"
              if requested_job_id not in (_JOB_ID_MISSING, None) else doc.get("name", ""))
    return ok(_req_view(doc))


@bp.put("/<int:req_id>")
@role_required(HR)
def update_requirement(req_id: int):
    req = _get_or_404(req_id)
    if req["status"] not in (REQ_DRAFT, REQ_RECRUITING):
        raise BizError(BizCode.STATE_INVALID, "当前状态不允许编辑")
    payload = request.get_json(silent=True) or {}
    requested_job_id = _requested_job_id(payload)
    if requested_job_id is not _JOB_ID_MISSING:
        _validate_job_link(requested_job_id, req_id)
    fields = _fill(req, payload)
    update_doc("requirements", req_id, fields)
    if requested_job_id is None:
        _unlink_primary_job(req_id)
    elif requested_job_id is not _JOB_ID_MISSING:
        _link_job_to_requirement(requested_job_id, req_id)
    write_log("requirement", "update", g.current_user.user_id, g.current_user.name, biz_id=str(req_id))
    return ok(_req_view(req))


@bp.post("/<int:req_id>/<action>")
@role_required(HR)
def change_status(req_id: int, action: str):
    req = _get_or_404(req_id)
    target = STATUS_ACTION.get(action)
    if target is None:
        raise BizError(BizCode.PARAM_INVALID, f"未知操作: {action}")
    if target not in REQUIREMENT_FLOW.get(req["status"], []):
        raise BizError(BizCode.STATE_INVALID, f"当前状态 {req['status']} 不允许执行 {action}")
    if action == "submit":
        _validate_submit(req)
    update_doc("requirements", req_id, {"status": target})
    req["status"] = target
    write_log("requirement", action, g.current_user.user_id, g.current_user.name,
              biz_id=str(req_id), detail=f"状态变更为 {target}")
    return ok(_req_view(req))
