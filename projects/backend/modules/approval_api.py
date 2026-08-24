"""Offer 录用审批：固定三级审批链和审批任务。"""
from datetime import datetime, timedelta

from flask import Blueprint, g, request
from pymongo.errors import DuplicateKeyError

from common.db import col, dt, get_by_id, insert_doc, next_id
from common.access import APPROVAL_ACCESS_ROLES
from common.decorators import role_required
from common.errors import BizError
from common.logstore import write_log
from common.response import BizCode, ok, paged
from common.roles import CHAIRMAN, GM, HR, ORG_APPROVER, OFFER_SENDER
from common.flow import job_stage_sequence, move_application, rollback_application_operation
from common.consistency import require_offer_application
from common.atomic import business_transaction
from common.indexes import ensure_core_indexes

bp = Blueprint("approval_api", __name__, url_prefix="/api/approvals")

APPROVER_ROLES = (HR, ORG_APPROVER, GM, CHAIRMAN, OFFER_SENDER)
CHAIN = [
    ("org", "组织统筹审批", "org_approver_id", "org_approver_name", ORG_APPROVER),
    ("gm", "总经理审批", "gm_id", "gm_name", GM),
    ("chairman", "董事长审批", "chairman_id", "chairman_name", CHAIRMAN),
]
APPROVAL_DEADLINE_DAYS = 30


def _deadline_at(doc: dict):
    if doc.get("deadline_at"):
        return doc["deadline_at"]
    created_at = doc.get("created_at")
    return created_at + timedelta(days=APPROVAL_DEADLINE_DAYS) if created_at else None


def _config():
    return col("offer_approver_config").find_one({"_id": 1}) or {}


def _offer_or_404(offer_id):
    offer = get_by_id("offers", offer_id)
    if offer is None:
        raise BizError(BizCode.NOT_FOUND, "Offer 不存在")
    return offer


def _ensure_for_offer(offer, session=None):
    ensure_core_indexes()
    existing = col("offer_approvals").find_one({"offer_id": offer["_id"]}, session=session)
    if existing:
        return existing
    config = _config()
    now = datetime.now()
    steps = [{
        "key": key, "name": name, "role": role,
        "approver_id": config.get(id_field, ""),
        "approver_name": config.get(name_field, ""),
        "status": "pending" if index == 0 else "waiting",
        "reason": "", "acted_at": None,
    } for index, (key, name, id_field, name_field, role) in enumerate(CHAIN)]
    doc = {
        "_id": next_id("offer_approvals", session=session), "offer_id": offer["_id"],
        "status": "pending", "current_index": 0, "version": 1,
        "deadline_at": now + timedelta(days=APPROVAL_DEADLINE_DAYS),
        "steps": steps, "created_by": offer.get("created_by", ""),
        "created_at": now, "updated_at": now,
    }
    try:
        col("offer_approvals").insert_one(doc, session=session)
        return doc
    except DuplicateKeyError as exc:
        if session is not None:
            raise
        existing = col("offer_approvals").find_one({"offer_id": offer["_id"]})
        if existing:
            return existing
        raise exc


def _view(doc):
    offer = get_by_id("offers", doc["offer_id"]) or {}
    candidate = get_by_id("candidates", offer.get("candidate_id")) or {}
    job = get_by_id("jobs", offer.get("job_id")) or {}
    deadline_at = _deadline_at(doc)
    return {
        "id": doc["_id"], "offer_id": doc["offer_id"], "candidate_id": offer.get("candidate_id"),
        "candidate_name": candidate.get("name", ""), "job_id": offer.get("job_id"),
        "job_name": job.get("name", ""), "position": offer.get("position", ""),
        "salary": offer.get("salary", ""), "onboard_date": dt(offer.get("onboard_date"))[:10],
        "offer_status": offer.get("status", ""), "status": doc.get("status", "pending"),
        "current_step": doc.get("steps", [])[doc.get("current_index", 0)]["key"]
        if doc.get("status") == "pending" and doc.get("steps") else "",
        "current_step_name": doc.get("steps", [])[doc.get("current_index", 0)]["name"]
        if doc.get("status") == "pending" and doc.get("steps") else "",
        "steps": [{**step, "acted_at": dt(step.get("acted_at"))} for step in doc.get("steps", [])],
        "deadline_at": dt(deadline_at),
        "overdue": bool(deadline_at and deadline_at < datetime.now() and doc.get("status") == "pending"),
        "days_remaining": max(0, (deadline_at - datetime.now()).days)
        if deadline_at and doc.get("status") == "pending" else 0,
        "version": doc.get("version", 1), "created_at": dt(doc.get("created_at")),
        "updated_at": dt(doc.get("updated_at")),
    }


def _ensure_pending_records():
    for offer in col("offers").find({"status": {"$in": ["pending_send", "sent"]}}):
        _ensure_for_offer(offer)


@bp.get("")
@role_required(*APPROVAL_ACCESS_ROLES)
def list_approvals():
    _ensure_pending_records()
    args = request.args
    query = {}
    status = args.get("status")
    if status:
        query["status"] = status
    if g.current_user.role != HR:
        query["steps.approver_id"] = g.current_user.user_id
    rows = [_view(doc) for doc in col("offer_approvals").find(query).sort("updated_at", -1)]
    page = max(int(args.get("page", 1)), 1)
    page_size = min(max(int(args.get("page_size", 10)), 1), 100)
    total = len(rows)
    return paged(rows[(page - 1) * page_size:page * page_size], total, page, page_size)


@bp.get("/<int:approval_id>")
@role_required(*APPROVAL_ACCESS_ROLES)
def get_approval(approval_id):
    doc = col("offer_approvals").find_one({"_id": approval_id})
    if doc is None:
        raise BizError(BizCode.NOT_FOUND, "审批记录不存在")
    return ok(_view(doc))


@bp.post("")
@role_required(HR)
def create_approval():
    payload = request.get_json(silent=True) or {}
    offer = _offer_or_404(int(payload.get("offer_id") or 0))
    require_offer_application(
        get_by_id("applications", offer.get("application_id")), action="create",
    )
    if offer.get("status") not in ("pending_send", "sent"):
        raise BizError(BizCode.STATE_INVALID, "只有待发送或已发送的 Offer 可以发起审批")
    return ok(_view(_ensure_for_offer(offer)))


@bp.post("/<int:approval_id>/action")
@role_required(*APPROVAL_ACCESS_ROLES)
def approval_action(approval_id):
    doc = col("offer_approvals").find_one({"_id": approval_id})
    if doc is None:
        raise BizError(BizCode.NOT_FOUND, "审批记录不存在")
    offer = _offer_or_404(doc["offer_id"])
    require_offer_application(
        get_by_id("applications", offer.get("application_id")), action="create",
    )
    if doc.get("status") != "pending":
        raise BizError(BizCode.STATE_INVALID, "审批已结束，不能重复操作")
    index = int(doc.get("current_index", 0))
    steps = doc.get("steps", [])
    if index >= len(steps):
        raise BizError(BizCode.STATE_INVALID, "审批链状态异常")
    step = steps[index]
    if step.get("approver_id") != g.current_user.user_id:
        raise BizError(BizCode.FORBIDDEN, "当前用户不是本节点审批人")
    payload = request.get_json(silent=True) or {}
    action = payload.get("action", "")
    if action not in ("approve", "reject"):
        raise BizError(BizCode.PARAM_INVALID, "审批动作必须是 approve 或 reject")
    reason = (payload.get("reason") or "").strip()
    if action == "reject" and not reason:
        raise BizError(BizCode.PARAM_INVALID, "驳回必须填写原因")
    try:
        version = int(payload.get("version", -1))
    except (TypeError, ValueError) as exc:
        raise BizError(BizCode.PARAM_INVALID, "version 必填") from exc
    now = datetime.now()
    steps[index].update({"status": "approved" if action == "approve" else "rejected",
                         "reason": reason, "acted_at": now})
    next_index = index + 1
    status = "approved" if action == "approve" and next_index >= len(steps) else "pending"
    if action == "reject":
        status = "rejected"
    if status == "pending" and next_index < len(steps):
        steps[next_index]["status"] = "pending"
    before_approval = dict(doc)
    moved_app = None
    session = None
    try:
        with business_transaction() as session:
            result = col("offer_approvals").find_one_and_update(
                {"_id": approval_id, "version": version, "status": "pending"},
                {"$set": {"steps": steps, "current_index": next_index,
                           "status": status, "version": version + 1, "updated_at": now}},
                session=session,
            )
            if result is None:
                raise BizError(BizCode.CONFLICT, "审批记录已被其他人更新，请刷新后重试")
            if status == "approved":
                offer = get_by_id("offers", doc["offer_id"], session=session) or {}
                app = get_by_id("applications", offer.get("application_id"), session=session) if offer.get("application_id") else None
                job = get_by_id("jobs", app.get("job_id"), session=session) if app else None
                if app and job and app.get("status") == "in_progress":
                    available = {stage.stage_key for stage in job_stage_sequence(job)}
                    target = "offer_pending" if "offer_pending" in available else ("offer" if "offer" in available else None)
                    if target and app.get("current_stage") != target:
                        moved_app = move_application(
                            app, target, "Offer 审批已全部通过，进入发送 Offer 阶段",
                            g.current_user.user_id, g.current_user.name, app.get("version", 1),
                            session=session,
                        )
            write_log("offer_approval", action, g.current_user.user_id, g.current_user.name,
                      biz_id=str(approval_id), detail=reason or step["name"], session=session)
    except Exception:
        if session is None:
            if moved_app:
                rollback_application_operation(moved_app)
            col("offer_approvals").replace_one(
                {"_id": approval_id, "version": version + 1}, before_approval,
            )
        raise
    return ok(_view({**doc, "steps": steps, "current_index": next_index,
                      "status": status, "version": version + 1, "updated_at": now}))
