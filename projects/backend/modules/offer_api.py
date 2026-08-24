"""Offer 管理（PRD v1.1 Sprint 4）。

- 集合：offers；状态严格为 草稿/待发送/已发送/已接受/已拒绝/已过期/已撤回，无审批链；
- 创建前校验候选人/职位/应聘记录一致，且应聘记录处于 interview_passed 或 offer_pending；
- 发送后应聘记录进入 offer_pending；接受后进入 pending_onboard（走乐观锁阶段流转）；
- 拒绝/过期/撤回必须记录原因并写 operation_logs；
- Offer 文件走现有 OSS 文件服务（files 集合存元数据），下载经登录校验，不暴露密钥；
- 状态流转带 version 乐观锁；超过有效期未响应惰性置为已过期。
"""
from datetime import datetime

from flask import Blueprint, Response, current_app, g, request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from common.db import col, get_by_id, insert_doc, update_doc, dt
from common.access import OFFER_FILE_ACCESS_ROLES, OFFER_READ_ROLES
from common.decorators import role_required
from common.errors import BizError
from common.file_service import get_storage, save_uploaded_file
from common.flow import application_to_dict, move_application, rollback_application_operation
from common.logstore import write_log
from common.mongo import MongoUnavailable
from common.response import BizCode, ok, paged
from common.roles import HR, SSC
from common.status import APP_IN_PROGRESS
from common.consistency import require_offer_application
from common.indexes import ensure_core_indexes
from common.storage import StorageError
from common.atomic import business_transaction

bp = Blueprint("offer_api", __name__, url_prefix="/api/offers")

# 状态：草稿 / 待发送 / 已发送 / 已接受 / 已拒绝 / 已过期 / 已撤回
OF_DRAFT, OF_PENDING_SEND, OF_SENT, OF_ACCEPTED, OF_REJECTED, OF_EXPIRED, OF_WITHDRAWN = (
    "draft", "pending_send", "sent", "accepted", "rejected", "expired", "withdrawn",
)
OFFER_FLOW = {
    OF_DRAFT: [OF_PENDING_SEND, OF_WITHDRAWN],
    OF_PENDING_SEND: [OF_SENT, OF_WITHDRAWN],
    OF_SENT: [OF_ACCEPTED, OF_REJECTED, OF_EXPIRED, OF_WITHDRAWN],
    OF_ACCEPTED: [], OF_REJECTED: [], OF_EXPIRED: [], OF_WITHDRAWN: [],
}
# 同一应聘记录同时只能有一个进行中的 Offer
ACTIVE_STATUSES = [OF_DRAFT, OF_PENDING_SEND, OF_SENT]
# 允许创建 Offer 的应聘记录阶段
ALLOWED_STAGES = ["interview_passed", "offer_pending"]
# 需要记录原因的动作
REASON_REQUIRED = {"reject", "withdraw", "expire"}

ACTION_TARGET = {
    "submit": OF_PENDING_SEND,
    "send": OF_SENT,
    "accept": OF_ACCEPTED,
    "reject": OF_REJECTED,
    "expire": OF_EXPIRED,
    "withdraw": OF_WITHDRAWN,
}


def _get_or_404(offer_id: int) -> dict:
    doc = get_by_id("offers", offer_id)
    if doc is None:
        raise BizError(BizCode.NOT_FOUND, "Offer 不存在")
    return doc


def _parse_date(value, field: str, end_of_day: bool = False) -> datetime:
    try:
        base = datetime.strptime((value or "").strip(), "%Y-%m-%d")
    except (TypeError, ValueError):
        raise BizError(BizCode.PARAM_INVALID, f"{field} 格式应为 YYYY-MM-DD")
    if end_of_day:
        return base.replace(hour=23, minute=59, second=59)
    return base


def _offer_view(doc: dict) -> dict:
    candidate = get_by_id("candidates", doc["candidate_id"]) or {}
    job = get_by_id("jobs", doc["job_id"]) or {}
    file_meta = None
    if doc.get("file_id"):
        from bson import ObjectId
        from bson.errors import InvalidId

        f = None
        try:
            f = col("files").find_one({"_id": ObjectId(doc["file_id"])})
        except (InvalidId, TypeError) as exc:
            current_app.logger.warning(
                "Offer 附件元数据 ID 无效 offer_id=%s file_id=%s error=%s",
                doc.get("_id"), doc.get("file_id"), exc,
            )
        if f:
            file_meta = {
                "id": str(f["_id"]), "originalName": f.get("originalName", ""),
                "size": f.get("size", 0), "mimeType": f.get("mimeType", ""),
                "url": f"/api/offers/{doc['_id']}/preview",
            }
    return {
        "id": doc["_id"],
        "candidate_id": doc["candidate_id"],
        "candidate_name": candidate.get("name", ""),
        "job_id": doc["job_id"],
        "job_name": job.get("name", ""),
        "application_id": doc.get("application_id"),
        "dept": doc.get("dept", ""),
        "position": doc.get("position", ""),
        "onboard_date": dt(doc.get("onboard_date"))[:10],
        "location": doc.get("location", ""),
        "salary": doc.get("salary", ""),
        "probation": doc.get("probation", ""),
        "contract_term": doc.get("contract_term", ""),
        "benefits": doc.get("benefits", ""),
        "valid_until": dt(doc.get("valid_until"))[:10],
        "remark": doc.get("remark", ""),
        "status": doc.get("status", OF_DRAFT),
        "response_reason": doc.get("response_reason", ""),
        "sent_at": dt(doc.get("sent_at")),
        "responded_at": dt(doc.get("responded_at")),
        "file": file_meta,
        "version": doc.get("version", 1),
        "created_at": dt(doc.get("created_at")),
        "updated_at": dt(doc.get("updated_at")),
    }


def _lazy_expire(doc: dict) -> dict:
    """超过有效期未响应：惰性置为已过期并记录原因。"""
    if doc.get("status") == OF_SENT and doc.get("valid_until") \
            and doc["valid_until"] < datetime.now():
        reason = "Offer 有效期已过，系统自动过期"
        updated = col("offers").find_one_and_update(
            {"_id": doc["_id"], "status": OF_SENT},
            {"$set": {"status": OF_EXPIRED, "response_reason": reason,
                      "responded_at": datetime.now(), "updated_at": datetime.now()}},
            return_document=ReturnDocument.AFTER,
        )
        if updated is not None:
            doc = updated
            write_log("offer", "expire_auto", "system", "系统",
                      biz_id=str(doc["_id"]), detail=reason)
        else:
            doc = col("offers").find_one({"_id": doc["_id"]}) or doc
    return doc


def _resolve_bindings(payload: dict):
    app_doc = get_by_id("applications", int(payload.get("application_id") or 0))
    if app_doc is None:
        raise BizError(BizCode.PARAM_INVALID, "必须绑定有效的应聘记录")
    candidate = get_by_id("candidates", app_doc["candidate_id"])
    job = get_by_id("jobs", app_doc["job_id"])
    if candidate is None or job is None:
        raise BizError(BizCode.PARAM_INVALID, "应聘记录关联的候选人或职位不存在")
    if payload.get("candidate_id") and int(payload["candidate_id"]) != candidate["_id"]:
        raise BizError(BizCode.PARAM_INVALID, "候选人与应聘记录不匹配")
    if payload.get("job_id") and int(payload["job_id"]) != job["_id"]:
        raise BizError(BizCode.PARAM_INVALID, "职位与应聘记录不匹配")
    return candidate, job, app_doc


def _check_stage_gate(app_doc: dict):
    app_doc = require_offer_application(app_doc, action="create")
    if app_doc.get("status") != APP_IN_PROGRESS:
        raise BizError(BizCode.STATE_INVALID, "应聘记录已结束，不能创建 Offer")
    if app_doc.get("current_stage") not in ALLOWED_STAGES:
        raise BizError(BizCode.STATE_INVALID,
                       "仅面试通过（interview_passed）或 Offer 中阶段的候选人可创建 Offer")


def _check_single_active(application_id: int, exclude_id: int = None):
    query = {"application_id": application_id, "status": {"$in": ACTIVE_STATUSES}}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    if col("offers").find_one(query):
        raise BizError(BizCode.DUPLICATED, "该应聘记录已存在进行中的 Offer")


@bp.get("")
@role_required(*OFFER_READ_ROLES)
def list_offers():
    args = request.args
    query = {}
    if args.get("status"):
        query["status"] = args["status"]
    if args.get("job_id"):
        query["job_id"] = int(args["job_id"])
    if args.get("candidate_id"):
        query["candidate_id"] = int(args["candidate_id"])
    rows = [_offer_view(_lazy_expire(d)) for d in
            col("offers").find(query).sort("_id", -1)]
    page = max(int(args.get("page", 1)), 1)
    page_size = min(max(int(args.get("page_size", 10)), 1), 100)
    total = len(rows)
    sliced = rows[(page - 1) * page_size: page * page_size]
    return paged(sliced, total, page, page_size)


@bp.get("/<int:offer_id>")
@role_required(*OFFER_READ_ROLES)
def get_offer(offer_id: int):
    doc = _lazy_expire(_get_or_404(offer_id))
    return ok(_offer_view(doc))


@bp.post("")
@role_required(HR)
def create_offer():
    ensure_core_indexes()
    payload = request.get_json(silent=True) or {}
    candidate, job, app_doc = _resolve_bindings(payload)
    _check_stage_gate(app_doc)
    _check_single_active(app_doc["_id"])

    for field in ("dept", "position", "salary"):
        if not (payload.get(field) or "").strip():
            raise BizError(BizCode.PARAM_INVALID, f"缺少必填字段: {field}")
    onboard_date = _parse_date(payload.get("onboard_date"), "入职日期")
    valid_until = _parse_date(payload.get("valid_until"), "有效期", end_of_day=True)
    if valid_until < datetime.now():
        raise BizError(BizCode.PARAM_INVALID, "有效期不能早于当前时间")

    try:
        doc = insert_doc("offers", {
        "candidate_id": candidate["_id"],
        "job_id": job["_id"],
        "application_id": app_doc["_id"],
        "dept": payload["dept"].strip(),
        "position": payload["position"].strip(),
        "onboard_date": onboard_date,
        "location": (payload.get("location") or "").strip(),
        "salary": payload["salary"].strip(),
        "probation": (payload.get("probation") or "").strip(),
        "contract_term": (payload.get("contract_term") or "").strip(),
        "benefits": (payload.get("benefits") or "").strip(),
        "valid_until": valid_until,
        "remark": (payload.get("remark") or "").strip(),
        "status": OF_DRAFT,
        "response_reason": "",
        "file_id": None,
        "sent_at": None,
        "responded_at": None,
        "version": 1,
            "created_by": g.current_user.user_id,
        })
    except DuplicateKeyError as exc:
        raise BizError(BizCode.DUPLICATED, "该应聘记录已存在进行中的 Offer") from exc
    write_log("offer", "create", g.current_user.user_id, g.current_user.name,
              biz_id=str(doc["_id"]),
              detail=f"候选人{candidate['_id']} 职位{job['_id']}")
    return ok(_offer_view(doc))


EDITABLE_FIELDS = ["dept", "position", "location", "salary", "probation",
                   "contract_term", "benefits", "remark"]


@bp.put("/<int:offer_id>")
@role_required(HR)
def update_offer(offer_id: int):
    doc = _get_or_404(offer_id)
    if doc["status"] != OF_DRAFT:
        raise BizError(BizCode.STATE_INVALID, "仅草稿状态的 Offer 可编辑")
    payload = request.get_json(silent=True) or {}
    fields = {}
    for field in EDITABLE_FIELDS:
        if field in payload:
            fields[field] = (payload[field] or "").strip()
    if "onboard_date" in payload:
        fields["onboard_date"] = _parse_date(payload["onboard_date"], "入职日期")
    if "valid_until" in payload:
        valid_until = _parse_date(payload["valid_until"], "有效期", end_of_day=True)
        if valid_until < datetime.now():
            raise BizError(BizCode.PARAM_INVALID, "有效期不能早于当前时间")
        fields["valid_until"] = valid_until
    if "version" not in payload:
        # 兼容旧调用方；当前前端会始终携带 version，进入下面的 CAS 分支。
        update_doc("offers", offer_id, fields)
        updated = col("offers").find_one({"_id": offer_id})
    else:
        try:
            version = int(payload["version"])
        except (TypeError, ValueError) as exc:
            raise BizError(BizCode.PARAM_INVALID, "version 必须为数字") from exc
        updated = col("offers").find_one_and_update(
            {"_id": offer_id, "status": OF_DRAFT, "version": version},
            {"$set": fields, "$inc": {"version": 1},
             "$currentDate": {"updated_at": True}},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            raise BizError(BizCode.CONFLICT, "Offer 已被其他人更新，请刷新后重试")
    doc = updated
    write_log("offer", "update", g.current_user.user_id, g.current_user.name,
              biz_id=str(offer_id))
    return ok(_offer_view(doc))


def _move_application_stage(app_doc: dict, to_stage: str, reason: str, session=None):
    """使用现有乐观锁阶段流转机制推进应聘记录。"""
    app_doc = get_by_id("applications", app_doc["_id"], session=session)
    return move_application(
        app_doc, to_stage=to_stage, reason=reason,
        operator_id=g.current_user.user_id, operator_name=g.current_user.name,
        version=app_doc["version"], session=session,
    )


@bp.post("/<int:offer_id>/status")
@role_required(HR, SSC)
def change_status(offer_id: int):
    doc = _lazy_expire(_get_or_404(offer_id))
    payload = request.get_json(silent=True) or {}
    action = payload.get("action", "")
    target = ACTION_TARGET.get(action)
    if target is None:
        raise BizError(BizCode.PARAM_INVALID, f"未知操作: {action}")
    if target not in OFFER_FLOW.get(doc["status"], []):
        raise BizError(BizCode.STATE_INVALID,
                       f"当前状态 {doc['status']} 不允许执行 {action}")
    app_doc = get_by_id("applications", doc.get("application_id"))
    if app_doc is None:
        raise BizError(BizCode.STATE_INVALID, "Offer 关联的应聘记录不存在")
    check_action = action if action in {"submit", "send", "accept"} else "create"
    require_offer_application(app_doc, action=check_action)
    reason = (payload.get("reason") or "").strip()
    if action in REASON_REQUIRED and not reason:
        raise BizError(BizCode.PARAM_INVALID, f"{action} 必须填写原因")

    # 乐观锁：仅当 version 一致时流转
    try:
        version = int(payload.get("version", -1))
    except (TypeError, ValueError):
        raise BizError(BizCode.PARAM_INVALID, "version 必填")
    set_fields = {"status": target, "version": doc["version"] + 1,
                  "updated_at": datetime.now()}
    if action in REASON_REQUIRED:
        set_fields["response_reason"] = reason
        set_fields["responded_at"] = datetime.now()
    if action == "accept":
        set_fields["responded_at"] = datetime.now()
    if action == "send":
        set_fields["sent_at"] = datetime.now()
    before_offer = dict(doc)
    moved_app = None
    session = None
    try:
        with business_transaction() as session:
            updated = col("offers").find_one_and_update(
                {"_id": offer_id, "version": version, "status": doc["status"]},
                {"$set": set_fields}, session=session,
            )
            if updated is None:
                raise BizError(BizCode.CONFLICT, "数据已被其他人更新，请刷新后重试")

    # 阶段联动（现有阶段流转机制）
            app_doc = get_by_id("applications", doc["application_id"], session=session)
            if app_doc and app_doc.get("status") == APP_IN_PROGRESS:
                if action == "send" and app_doc.get("current_stage") != "offer_pending":
                    moved_app = _move_application_stage(app_doc, "offer_pending", f"Offer 已发送（#{offer_id}）", session=session)
                elif action == "accept":
                    moved_app = _move_application_stage(app_doc, "pending_onboard", f"Offer 已接受（#{offer_id}）", session=session)

    # 审批页使用固定审批人配置；保留 Offer 原有状态机兼容性，同时在提交时建立审批任务。
            if action == "submit":
                from modules.approval_api import _ensure_for_offer

                _ensure_for_offer(doc, session=session)

            doc.update(set_fields)
            write_log("offer", action, g.current_user.user_id, g.current_user.name,
                      biz_id=str(offer_id),
                      detail=reason or f"状态变更为 {target}", session=session)
    except Exception:
        if session is None:
            if moved_app:
                rollback_application_operation(moved_app)
            col("offers").replace_one(
                {"_id": offer_id, "version": set_fields["version"]}, before_offer,
            )
        raise
    return ok(_offer_view(doc))


# ---------------- Offer 文件（OSS 文件服务） ----------------

@bp.post("/<int:offer_id>/file")
@role_required(HR)
def upload_offer_file(offer_id: int):
    doc = _get_or_404(offer_id)
    if doc["status"] not in (OF_DRAFT, OF_PENDING_SEND):
        raise BizError(BizCode.STATE_INVALID, "仅草稿/待发送状态可上传 Offer 文件")
    file = request.files.get("file")
    if file is None or not file.filename:
        raise BizError(BizCode.PARAM_INVALID, "请上传 Offer 文件")
    try:
        meta = save_uploaded_file(
            current_app, file, biz_type="offer",
            operator_id=g.current_user.user_id, operator_name=g.current_user.name,
        )
    except MongoUnavailable:
        raise BizError(5001, "文件服务不可用：MongoDB 未连接")
    except StorageError as e:
        raise BizError(BizCode.PARAM_INVALID, str(e))
    # files 集合的 _id 为 ObjectId 字符串，转存为字符串引用
    update_doc("offers", offer_id, {"file_id": meta["id"]})
    write_log("offer", "file_upload", g.current_user.user_id, g.current_user.name,
              biz_id=str(offer_id), detail=meta["originalName"])
    return ok(_offer_view(_get_or_404(offer_id)))


def _file_doc_or_404(doc: dict) -> dict:
    if not doc.get("file_id"):
        raise BizError(BizCode.NOT_FOUND, "该 Offer 尚未上传文件")
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        oid = ObjectId(doc["file_id"])
    except (InvalidId, TypeError):
        raise BizError(BizCode.NOT_FOUND, "文件元数据不存在")
    f = col("files").find_one({"_id": oid})
    if f is None:
        raise BizError(BizCode.NOT_FOUND, "文件元数据不存在")
    return f


@bp.get("/<int:offer_id>/preview")
@role_required(*OFFER_FILE_ACCESS_ROLES)
def preview_offer_file(offer_id: int):
    """预览：登录校验后重定向到文件服务（OSS 签名 URL 或后端代理），不暴露密钥。"""
    doc = _get_or_404(offer_id)
    _file_doc_or_404(doc)
    write_log("offer", "file_preview", g.current_user.user_id, g.current_user.name,
              biz_id=str(offer_id))
    from flask import redirect

    return redirect(f"/api/files/{doc['file_id']}/download")


@bp.get("/<int:offer_id>/download")
@role_required(*OFFER_FILE_ACCESS_ROLES)
def download_offer_file(offer_id: int):
    """下载：登录校验 + 后端代理/签名，不暴露 OSS 密钥。"""
    doc = _get_or_404(offer_id)
    f = _file_doc_or_404(doc)
    storage = get_storage(current_app)
    if storage is None:
        raise BizError(5001, "文件存储不可用")
    url = storage.signed_url(f["objectKey"], expires=600)
    write_log("offer", "file_download", g.current_user.user_id, g.current_user.name,
              biz_id=str(offer_id))
    if url:
        from flask import redirect

        return redirect(url)
    from common.file_service import read_file_bytes

    data = read_file_bytes(current_app, f["objectKey"])
    return Response(
        data.getvalue(),
        mimetype=f.get("mimeType") or "application/octet-stream",
        headers={"Content-Disposition":
                 f"attachment; filename*=UTF-8''{f.get('originalName', '')}"},
    )
