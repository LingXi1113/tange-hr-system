"""入职资料与入职办理。"""
import json
from datetime import datetime

from flask import Blueprint, current_app, g, request
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument

from common.db import col, dt, get_by_id, insert_doc, update_doc
from common.decorators import login_required, role_required
from common.errors import BizError
from common.flow import move_application, rollback_application_operation
from common.consistency import require_onboarding_application
from common.logstore import write_log
from common.response import BizCode, ok, paged
from common.roles import HR, SSC
from common.stages import ONBOARDING_CHECKLIST_FALLBACK, PARAM_ONBOARDING_CHECKLIST_DEFAULT
from common.atomic import business_transaction
from common.indexes import ensure_core_indexes

bp = Blueprint("onboarding_api", __name__, url_prefix="/api/onboarding")

ITEM_STATUSES = ("pending", "submitted", "verified", "rejected")


def _checklist_names():
    param = col("sys_params").find_one({"_id": PARAM_ONBOARDING_CHECKLIST_DEFAULT})
    if param:
        try:
            values = json.loads(param.get("value", "[]"))
            if isinstance(values, list) and values:
                return [str(value) for value in values if str(value).strip()]
        except (TypeError, ValueError) as exc:
            current_app.logger.warning("默认入职资料清单配置格式无效，将使用系统兜底值：%s", exc)
    return list(ONBOARDING_CHECKLIST_FALLBACK)


def _application_or_404(application_id):
    app = get_by_id("applications", application_id)
    if app is None:
        raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
    return app


def _offer_for_app(application_id):
    return col("offers").find_one({"application_id": application_id, "status": "accepted"}, sort=[("_id", -1)])


def _ensure_for_application(app):
    app = require_onboarding_application(app)
    ensure_core_indexes()
    existing = col("onboarding_records").find_one({"application_id": app["_id"]})
    if existing:
        return existing
    candidate = get_by_id("candidates", app["candidate_id"]) or {}
    offer = _offer_for_app(app["_id"]) or {}
    now = datetime.now()
    try:
        record = insert_doc("onboarding_records", {
            "application_id": app["_id"], "candidate_id": app["candidate_id"], "job_id": app["job_id"],
            "offer_id": offer.get("_id"), "planned_date": offer.get("onboard_date"),
            "status": "completed" if app.get("current_stage") == "onboarded" else "pending",
            "checklist": [{"key": f"item_{index}", "name": name, "status": "pending",
                           "remark": "", "updated_at": None, "verified_at": None}
                          for index, name in enumerate(_checklist_names(), 1)],
            "notes": "", "owner_id": g.current_user.user_id, "owner_name": g.current_user.name,
            "version": 1,
            "created_at": now, "updated_at": now,
        })
        return record
    except DuplicateKeyError:
        # 两个列表请求同时补建记录时，返回先成功写入的那一条。
        return col("onboarding_records").find_one({"application_id": app["_id"]})


def _view(record):
    candidate = get_by_id("candidates", record["candidate_id"]) or {}
    job = get_by_id("jobs", record["job_id"]) or {}
    app = get_by_id("applications", record["application_id"]) or {}
    offer = get_by_id("offers", record.get("offer_id")) if record.get("offer_id") else None
    checklist = [{**item, "updated_at": dt(item.get("updated_at")), "verified_at": dt(item.get("verified_at"))}
                 for item in record.get("checklist", [])]
    return {
        "id": record["_id"], "application_id": record["application_id"],
        "candidate_id": record["candidate_id"], "candidate_name": candidate.get("name", ""),
        "job_id": record["job_id"], "job_name": job.get("name", ""),
        "offer_id": record.get("offer_id"), "planned_date": dt(record.get("planned_date"))[:10],
        "application_stage": app.get("current_stage", ""), "status": record.get("status", "pending"),
        "version": record.get("version", 1),
        "checklist": checklist, "completed_count": sum(i.get("status") == "verified" for i in checklist),
        "total_count": len(checklist), "notes": record.get("notes", ""),
        "owner_id": record.get("owner_id", ""), "owner_name": record.get("owner_name", ""),
        "created_at": dt(record.get("created_at")), "updated_at": dt(record.get("updated_at")),
        "offer_position": offer.get("position", "") if offer else "",
    }


def _ensure_pending_records():
    for app in col("applications").find({"current_stage": {"$in": ["pending_onboard", "onboarded"]}}):
        _ensure_for_application(app)


def _get_record(record_id):
    record = get_by_id("onboarding_records", record_id)
    if record is None:
        raise BizError(BizCode.NOT_FOUND, "入职记录不存在")
    return record


@bp.get("")
@role_required(HR, SSC)
def list_onboarding():
    _ensure_pending_records()
    args = request.args
    query = {}
    if args.get("status"):
        query["status"] = args["status"]
    if args.get("job_id"):
        query["job_id"] = int(args["job_id"])
    records = list(col("onboarding_records").find(query).sort("_id", -1))
    if args.get("keyword"):
        keyword = args["keyword"]
        records = [record for record in records
                   if keyword in (get_by_id("candidates", record["candidate_id"]) or {}).get("name", "")]
    page = max(int(args.get("page", 1)), 1)
    page_size = min(max(int(args.get("page_size", 10)), 1), 100)
    total = len(records)
    return paged([_view(record) for record in records[(page - 1) * page_size:page * page_size]], total, page, page_size)


@bp.get("/<int:record_id>")
@role_required(HR, SSC)
def get_onboarding(record_id):
    return ok(_view(_get_record(record_id)))


@bp.post("/<int:record_id>/start")
@role_required(HR, SSC)
def start_onboarding(record_id):
    record = _get_record(record_id)
    require_onboarding_application(_application_or_404(record["application_id"]))
    if record.get("status") not in ("pending", "in_progress"):
        raise BizError(BizCode.STATE_INVALID, "当前入职记录不能开始办理")
    payload = request.get_json(silent=True) or {}
    try:
        version = int(payload.get("version", record.get("version", 1)))
    except (TypeError, ValueError) as exc:
        raise BizError(BizCode.PARAM_INVALID, "version 必须为数字") from exc
    updated = col("onboarding_records").find_one_and_update(
        {"_id": record_id, "version": version, "status": {"$in": ["pending", "in_progress"]}},
        {"$set": {"status": "in_progress", "owner_id": g.current_user.user_id,
                   "owner_name": g.current_user.name}, "$inc": {"version": 1},
         "$currentDate": {"updated_at": True}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise BizError(BizCode.CONFLICT, "入职记录已被其他人更新，请刷新后重试")
    record = updated
    write_log("onboarding", "start", g.current_user.user_id, g.current_user.name, biz_id=str(record_id))
    return ok(_view(record))


@bp.post("/<int:record_id>/items/<item_key>")
@role_required(HR, SSC)
def update_item(record_id, item_key):
    record = _get_record(record_id)
    require_onboarding_application(_application_or_404(record["application_id"]))
    if record.get("status") in ("completed", "cancelled"):
        raise BizError(BizCode.STATE_INVALID, "已结束的入职记录不能修改资料")
    payload = request.get_json(silent=True) or {}
    status = payload.get("status", "")
    if status not in ITEM_STATUSES:
        raise BizError(BizCode.PARAM_INVALID, "资料状态不合法")
    found = False
    now = datetime.now()
    for item in record.get("checklist", []):
        if item.get("key") == item_key:
            item.update({"status": status, "remark": (payload.get("remark") or "").strip(), "updated_at": now,
                         "verified_at": now if status == "verified" else None})
            found = True
            break
    if not found:
        raise BizError(BizCode.NOT_FOUND, "入职资料条目不存在")
    try:
        version = int(payload.get("version", record.get("version", 1)))
    except (TypeError, ValueError) as exc:
        raise BizError(BizCode.PARAM_INVALID, "version 必须为数字") from exc
    fields = {"checklist": record["checklist"], "status": "in_progress", "owner_id": g.current_user.user_id,
              "owner_name": g.current_user.name}
    updated = col("onboarding_records").find_one_and_update(
        {"_id": record_id, "version": version, "status": {"$nin": ["completed", "cancelled"]}},
        {"$set": fields, "$inc": {"version": 1}, "$currentDate": {"updated_at": True}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise BizError(BizCode.CONFLICT, "入职资料已被其他人更新，请刷新后重试")
    record = updated
    write_log("onboarding", "item_" + status, g.current_user.user_id, g.current_user.name,
              biz_id=str(record_id), detail=item_key)
    return ok(_view(record))


@bp.post("/<int:record_id>/complete")
@role_required(HR, SSC)
def complete_onboarding(record_id):
    record = _get_record(record_id)
    if record.get("status") == "completed":
        raise BizError(BizCode.STATE_INVALID, "入职记录已经完成，不能重复操作")
    if any(item.get("status") != "verified" for item in record.get("checklist", [])):
        raise BizError(BizCode.STATE_INVALID, "所有入职资料核验通过后才能完成入职")
    app = require_onboarding_application(
        _application_or_404(record["application_id"]), completing=True,
    )
    payload = request.get_json(silent=True) or {}
    try:
        version = int(payload.get("version", record.get("version", 1)))
    except (TypeError, ValueError) as exc:
        raise BizError(BizCode.PARAM_INVALID, "version 必须为数字") from exc
    before_record = dict(record)
    moved_app = None
    session = None
    try:
        with business_transaction() as session:
            if app.get("current_stage") == "pending_onboard":
                moved_app = move_application(
                    app, "onboarded", "入职资料已全部核验通过",
                    g.current_user.user_id, g.current_user.name, app.get("version", 1),
                    session=session,
                )
                updated_app = moved_app
            else:
                updated_app = app
            updated_record = col("onboarding_records").find_one_and_update(
                {"_id": record_id, "version": version, "status": {"$ne": "completed"}},
                {"$set": {"status": "completed"}, "$inc": {"version": 1},
                 "$currentDate": {"updated_at": True}},
                return_document=ReturnDocument.AFTER, session=session,
            )
            if updated_record is None:
                raise BizError(BizCode.CONFLICT, "入职记录已被其他人更新，请刷新后重试")
            record = updated_record
            write_log("onboarding", "complete", g.current_user.user_id, g.current_user.name,
                      biz_id=str(record_id), detail=f"application={record['application_id']}",
                      session=session)
    except Exception:
        if session is None:
            if moved_app:
                rollback_application_operation(moved_app)
            col("onboarding_records").replace_one(
                {"_id": record_id, "status": "completed"}, before_record,
            )
        raise
    result = _view(record)
    result["application_stage"] = updated_app.get("current_stage", "onboarded")
    return ok(result)
