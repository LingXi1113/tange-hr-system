"""候选人与简历管理（MongoDB 版）：主档/应聘记录/查重/导入导出/简历上传解析。"""
import csv
import io
import json
import mimetypes
import os
import tempfile
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, Response, current_app, g, request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from werkzeug.utils import secure_filename

from common.access import (
    CANDIDATE_READ_ROLES, RESUME_ACCESS_ROLES, can_view_pii, redact_candidate,
    require_candidate_lock_owner,
)
from common.candidate_identity import ensure_candidate_indexes, identity_keys, identity_update
from common.candidate_query import CandidateQuery
from common.candidate_duplicates import find_matches, full_identity_key, log_review, review_token, validate_review
from common.atomic import business_transaction
from common.db import col, get_by_id, insert_doc, paginate, update_doc, dt
from common.decorators import role_required
from common.errors import BizError
from common.file_service import (
    read_file_bytes,
    resolve_local,
    save_uploaded_file,
)
from common.flow import (
    active_lock_for_candidate,
    application_to_dict,
    create_application,
    job_stage_sequence,
    lock_info_for_candidate,
)
from common.logstore import write_log
from common.mongo import MongoUnavailable
from common.privacy import purge_candidate
from common.resume_parser import (
    candidate_highest_education,
    highest_education_record,
    highest_education_from_records,
    major_from_records,
    parse_resume_file,
    parse_resume_file_with_text,
)
from common.response import BizCode, ok, paged
from common.roles import HR, SUPER_ADMIN
from common.status import APP_IN_PROGRESS
from common.status import APP_PENDING_ONBOARD
from common.consistency import reconcile_application_status
from common.stages import STAGE_NAMES
from common.storage import StorageError

bp = Blueprint("candidate_api", __name__)


def _get_candidate_or_404(cid: int) -> dict:
    c = get_by_id("candidates", cid)
    if c is None:
        raise BizError(BizCode.NOT_FOUND, "候选人不存在")
    return c


def _latest_application(candidate_id: int):
    app = col("applications").find_one({"candidate_id": candidate_id}, sort=[("_id", -1)])
    return reconcile_application_status(app) if app else None




def _candidate_view(c: dict, mask: bool = True) -> dict:
    # mask 参数仅保留兼容性，不能让普通角色通过 mask=0 关闭脱敏。
    data = redact_candidate(c, include_pii=can_view_pii() and not mask)
    data["highest_education"] = candidate_highest_education(c)
    data["version"] = int(c.get("version", 1))
    return data


def _duplicate_candidate_view(c: dict) -> dict:
    data = _candidate_view(c, mask=False)
    data["lock"] = lock_info_for_candidate(c["_id"])
    data["education"] = c.get("education") or []
    data["work_experience"] = c.get("work_experience") or []
    return data


def _duplicate_report_data(payload, matches, exclude_id=None):
    rows = []
    for candidate, matched_fields in matches:
        row = _duplicate_candidate_view(candidate)
        row["matched_fields"] = matched_fields
        rows.append(row)
    return {
        "duplicated": True,
        "duplicate_kind": "exact" if any(len(fields) == 3 for _, fields in matches) else "suspected",
        "review_token": review_token(payload, matches, exclude_id),
        "duplicates": rows,
    }


def _duplicate_report(payload, matches, exclude_id=None):
    return ok(_duplicate_report_data(payload, matches, exclude_id))


def _selected_candidate_job(payload):
    """Resolve an explicitly selected position before writing candidate data."""
    if "job_id" not in payload:
        return None  # Metadata-only records are also used by the talent pool.
    value = payload["job_id"]
    if isinstance(value, bool) or not str(value or "").isdigit() or int(value) <= 0:
        raise BizError(BizCode.PARAM_INVALID, "请选择应聘职位后再保存")
    job = get_by_id("jobs", int(value))
    if job is None:
        raise BizError(BizCode.PARAM_INVALID, "应聘职位不存在，请重新选择")
    return job


def _bind_candidate_job(candidate, job, session=None):
    require_candidate_lock_owner(candidate["_id"])
    existing = col("applications").find_one({
        "candidate_id": candidate["_id"], "job_id": job["_id"],
        "status": {"$in": [APP_IN_PROGRESS, APP_PENDING_ONBOARD]},
    }, session=session)
    if existing:
        return existing, False
    configured_stages = {stage.stage_key for stage in job_stage_sequence(job)}
    stage = "hr_screen_passed" if "hr_screen_passed" in configured_stages else "new_resume"
    application = create_application(
        candidate, job, source=candidate.get("source") or "manual",
        operator_id=g.current_user.user_id, operator_name=g.current_user.name,
        initial_stage=stage, initial_lock_days=7,
        initial_reason="HR分配职位并进入HR筛选", hr_assignment=True, session=session,
    )
    return application, True


def _undo_new_application(application):
    """Compensate only an application created by the current save request."""
    if not application:
        return
    aid = application["_id"]
    col("lock_records").delete_many({"application_id": aid})
    col("stage_transitions").delete_many({"application_id": aid})
    col("notifications").delete_many({"biz_type": "application", "biz_id": str(aid)})
    col("operation_logs").delete_many({"biz_type": "application", "biz_id": str(aid)})
    col("applications").delete_one({"_id": aid})


def _insert_candidate_with_job(doc, job):
    candidate = None
    application = None
    session = None
    try:
        with business_transaction() as session:
            candidate = insert_doc("candidates", doc, session=session)
            if job:
                application, _ = _bind_candidate_job(candidate, job, session=session)
        return candidate, application
    except Exception:
        if session is None and candidate:
            _undo_new_application(application)
            col("candidates").delete_one({"_id": candidate["_id"]})
        raise


def _merge_incoming_candidate(existing, payload):
    """Keep the master identity; add missing information and distinct histories."""
    require_candidate_lock_owner(existing["_id"])
    incoming = _fill_candidate(payload)
    fields = {key: value for key, value in incoming.items()
              if value and not existing.get(key) and key not in {"name", "phone", "email"}}
    for key in ("education", "work_experience"):
        records = list(existing.get(key) or [])
        for record in incoming.get(key) or []:
            if record not in records:
                records.append(record)
        fields[key] = records
    # Identity values only fill blanks; existing non-empty values remain authoritative.
    for key in ("name", "phone", "email"):
        if not existing.get(key) and incoming.get(key):
            fields[key] = incoming[key]
    merged = {**existing, **fields}
    identity_set, identity_unset = identity_update(
        merged.get("phone"), merged.get("email"), exempt=bool(existing.get("dedupe_exempt")),
    )
    fields.update(identity_set)
    full_key = full_identity_key(merged)
    if full_key:
        fields["identity_full_key"] = full_key
    update = {"$set": {**fields, "updated_at": datetime.now()}, "$inc": {"version": 1}}
    if identity_unset:
        update["$unset"] = identity_unset
    updated = col("candidates").find_one_and_update(
        {"_id": existing["_id"], "version": existing.get("version", 1)},
        update, return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise BizError(BizCode.CONFLICT, "已有档案已被修改，请重新查重确认")
    write_log("candidate", "merge", g.current_user.user_id, g.current_user.name,
              biz_id=str(existing["_id"]), detail="HR确认同一人，补充新提交的简历信息到已有主档")
    return updated


def _candidate_row(c: dict, mask: bool, application=None, use_context=False) -> dict:
    data = _candidate_view(c, mask=mask)
    education = list(c.get("education") or [])
    work_experience = list(c.get("work_experience") or [])

    def latest_record(records):
        return max(
            records,
            key=lambda item: str(item.get("end") or item.get("graduate_at") or item.get("start") or ""),
            default={},
        )

    data["education_summary"] = highest_education_record(education)
    data["work_summary"] = latest_record(work_experience)
    app = application if use_context else _latest_application(c["_id"])
    data["application_id"] = app["_id"] if app else None
    if app:
        data["latest_application"] = application_to_dict(app)
    else:
        data["latest_application"] = None
    data["current_stage"] = app.get("current_stage", "") if app else "pending_screen"
    data["lock"] = lock_info_for_candidate(c["_id"])
    return data


@bp.get("/api/candidates")
@role_required(*CANDIDATE_READ_ROLES)
def list_candidates():
    args = request.args
    mask = True if not can_view_pii() else args.get("mask", "1") != "0"
    snapshot = CandidateQuery()
    matches = snapshot.filter(args)
    page = max(int(args.get("page", 1)), 1)
    page_size = min(max(int(args.get("page_size", 10)), 1), 100)
    sliced, total, page, page_size = paginate(matches, page, page_size)
    data = {
        "list": [_candidate_row(candidate, mask, application=application, use_context=True)
                 for candidate, application in sliced],
        "total": total, "page": page, "page_size": page_size,
    }
    if args.get("include_summary") == "1":
        data["classification"] = snapshot.summary(args)
    write_log("candidate", "list_view", g.current_user.user_id, g.current_user.name,
              detail=f"page={page}; page_size={page_size}; rows={len(sliced)}")
    return ok(data)


@bp.get("/api/candidates/classification-summary")
@role_required(*CANDIDATE_READ_ROLES)
def candidate_classification_summary():
    return ok(CandidateQuery().summary(request.args))


@bp.get("/api/candidates/<int:cid>")
@role_required(*CANDIDATE_READ_ROLES)
def get_candidate(cid: int):
    c = _get_candidate_or_404(cid)
    mask = True if not can_view_pii() else request.args.get("mask", "1") != "0"
    data = _candidate_view(c, mask=mask)
    data["education"] = c.get("education") or []
    data["work_experience"] = c.get("work_experience") or []
    # Older candidate records predate the summary fields. Derive them on read
    # so their existing education data is immediately visible without migration.
    if not data.get("highest_education"):
        data["highest_education"] = highest_education_from_records(data["education"])
    if not data.get("major"):
        data["major"] = major_from_records(data["education"])
    data["attachments"] = [{
        "id": a["_id"], "file_name": a.get("file_name", ""), "file_type": a.get("file_type", ""),
        "parse_status": a.get("parse_status", ""), "created_at": dt(a.get("created_at")),
    } for a in col("attachments").find({"candidate_id": cid}).sort("_id", 1)]
    data["lock"] = lock_info_for_candidate(cid)
    pool_entry = col("talent_pool").find_one(
        {"candidate_id": cid, "status": {"$ne": "removed"}},
        {"_id": 1, "status": 1, "source": 1, "reason": 1},
    )
    data["talent_pool_entry"] = (
        {"id": pool_entry["_id"], "status": pool_entry.get("status", "active"),
         "source": pool_entry.get("source", ""), "reason": pool_entry.get("reason", "")}
        if pool_entry else None
    )
    data["applications"] = []
    apps = list(col("applications").find({"candidate_id": cid}).sort("_id", -1))
    for app in apps:
        app = reconcile_application_status(app)
        d = application_to_dict(app)
        d["lock"] = lock_info_for_candidate(cid) if app.get("status") in (
            APP_IN_PROGRESS, APP_PENDING_ONBOARD,
        ) else None
        data["applications"].append(d)
    data["current_stage"] = apps[0].get("current_stage", "") if apps else "pending_screen"
    app_ids = [a["_id"] for a in apps]
    app_jobs = {app_id: get_by_id("jobs", app.get("job_id")) or {}
                for app_id, app in ((a["_id"], a) for a in apps)}

    def stage_name(application_id, stage_key):
        job = app_jobs.get(application_id, {})
        for stage in job_stage_sequence(job):
            if stage.stage_key == stage_key:
                return stage.name
        return STAGE_NAMES.get(stage_key, stage_key or "未标记")

    screening_records = []
    interview_stage_keys = {
        "pending_interview", "interviewing", "interview_passed",
        "interview_1", "interview_2", "interview_3", "hr_interview", "re_interview",
    }
    offer_stage_keys = {
        "hrbp_interview", "offer_approval", "offer_pending", "offer",
        "pending_onboard", "onboarded",
    }

    def record_category(from_stage: str, to_stage: str, record_type: str = "stage") -> str:
        if record_type == "recommendation":
            return "recommendation"
        if from_stage in offer_stage_keys or to_stage in offer_stage_keys:
            return "offer"
        if from_stage in interview_stage_keys or to_stage in interview_stage_keys:
            return "interview"
        return "recommendation"

    transitions = col("stage_transitions").find({
        "application_id": {"$in": app_ids},
    }).sort("_id", -1).limit(100)
    for transition in transitions:
        application_id = transition.get("application_id")
        from_stage = transition.get("from_stage", "")
        to_stage = transition.get("to_stage", "")
        reason = transition.get("reason", "")
        # 推荐给业务复筛单独展示“推荐记录”，避免与阶段推进重复显示。
        if to_stage == "business_screen" and ("推送" in reason or "指派" in reason):
            continue
        screening_records.append({
            "type": "stage",
            "category": record_category(from_stage, to_stage),
            "title": "推进阶段",
            "from_stage": stage_name(application_id, from_stage),
            "to_stage": stage_name(application_id, to_stage),
            "operator_name": transition.get("operator_name", ""),
            "detail": reason or f"推进至{stage_name(application_id, to_stage)}",
            "created_at": dt(transition.get("created_at")),
        })

    recommendation_logs = col("operation_logs").find({
        "biz_type": "application",
        "biz_id": {"$in": [str(app_id) for app_id in app_ids]},
        "action": {"$in": ["assign_business_screener", "recommend_business_screener"]},
    }).sort("_id", -1).limit(100)
    for log in recommendation_logs:
        screening_records.append({
            "type": "recommendation",
            "category": "recommendation",
            "title": "推荐给业务复筛",
            "from_stage": "",
            "to_stage": "业务复筛",
            "operator_name": log.get("operator_name", ""),
            "detail": log.get("detail", "") or "已推荐给业务复筛人员",
            "created_at": dt(log.get("created_at")),
        })

    interview_docs = list(col("interviews").find({
        "application_id": {"$in": app_ids},
    }, {"_id": 1, "round": 1, "application_id": 1}))
    interview_rounds = {str(item.get("_id")): item.get("round", "") for item in interview_docs}
    interview_ids = list(interview_rounds)
    if interview_ids:
        interview_action_titles = {
            "create": "安排面试",
            "update": "编辑面试",
            "invite": "发出面试邀请",
            "confirm": "确认面试",
            "complete": "完成面试",
            "cancel": "取消面试",
            "reschedule": "面试改期",
            "feedback": "提交面试评价",
            "apply_conclusion_pass": "面试评价通过",
            "apply_conclusion_fail": "面试评价不通过",
        }
        interview_logs = col("operation_logs").find({
            "biz_type": "interview",
            "biz_id": {"$in": interview_ids},
        }).sort("_id", -1).limit(100)
        for log in interview_logs:
            round_name = interview_rounds.get(str(log.get("biz_id")), "")
            action = log.get("action", "")
            title = interview_action_titles.get(action, "面试操作")
            detail = log.get("detail", "")
            if action == "reschedule":
                detail = f"{round_name}：改期原因：{detail}" if round_name else f"改期原因：{detail}"
            elif action == "complete" and detail == "状态变更为 completed":
                detail = "面试已完成"
            elif action == "feedback" and detail.startswith("结论="):
                detail = f"{round_name}：{detail}" if round_name else detail
            elif not detail:
                detail = f"{round_name}：{title}" if round_name else title
            screening_records.append({
                "type": "interview",
                "category": "interview",
                "title": title,
                "from_stage": "",
                "to_stage": round_name,
                "operator_name": log.get("operator_name", ""),
                "detail": detail,
                "created_at": dt(log.get("created_at")),
            })
    screening_records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    data["screening_records"] = screening_records[:100]
    write_log("candidate", "view", g.current_user.user_id, g.current_user.name, biz_id=str(cid))
    return ok(data)


def _fill_candidate(payload: dict) -> dict:
    fields = {}
    for field in [
        "name", "gender", "phone", "email", "city", "highest_education", "major",
        "tags", "remark", "source",
    ]:
        if field in payload:
            value = payload[field]
            fields[field] = (value or "").strip() if isinstance(value, str) else value
    if "age" in payload:
        value = payload.get("age")
        if value in (None, ""):
            fields["age"] = None
        else:
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise BizError(BizCode.PARAM_INVALID, "年龄必须是数字")
            if not 16 <= value <= 75:
                raise BizError(BizCode.PARAM_INVALID, "年龄必须在 16 到 75 岁之间")
            fields["age"] = value
    for jfield in ["education", "work_experience"]:
        if jfield in payload:
            value = payload[jfield]
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except ValueError:
                    raise BizError(BizCode.PARAM_INVALID, f"{jfield} 必须是 JSON 数组")
            fields[jfield] = value or []
    if "education" in fields:
        fields["highest_education"] = candidate_highest_education(fields)
        if not str(payload.get("major") or "").strip():
            fields["major"] = major_from_records(fields["education"])
    return fields


@bp.post("/api/candidates")
@role_required(HR)
def create_candidate():
    ensure_candidate_indexes()
    payload = request.get_json(silent=True) or {}
    if not (payload.get("name") or "").strip():
        raise BizError(BizCode.PARAM_INVALID, "姓名必填")
    job = _selected_candidate_job(payload)
    matches = find_matches(payload)
    decisions = validate_review(payload, matches) if matches else None
    if matches and decisions is None:
        return _duplicate_report(payload, matches)
    if decisions and "same" in decisions.values():
        existing = next(c for c, _ in matches if decisions[str(c["_id"])] == "same")
        application, created_application = _bind_candidate_job(existing, job) if job else (None, False)
        try:
            c = _merge_incoming_candidate(existing, payload)
        except Exception:
            if created_application:
                _undo_new_application(application)
            raise
        log_review(matches, decisions, c["_id"])
        return ok({"duplicated": False, "merged": True, "candidate": _candidate_view(c, mask=False),
                   "application": application_to_dict(application) if application else None})
    doc = {
        "name": "", "gender": "", "phone": "", "email": "", "city": "",
        "age": None, "highest_education": "", "major": "",
        "education": [], "work_experience": [], "tags": "", "remark": "",
        "source": "manual",
        "owner_id": payload.get("owner_id") or g.current_user.user_id,
        "owner_name": payload.get("owner_name") or g.current_user.name,
    }
    doc.update(_fill_candidate(payload))
    set_identity, _ = identity_update(doc.get("phone"), doc.get("email"), exempt=bool(decisions))
    doc.update(set_identity)
    full_key = full_identity_key(doc)
    if full_key:
        doc["identity_full_key"] = full_key
    doc["version"] = 1
    try:
        c, application = _insert_candidate_with_job(doc, job)
    except DuplicateKeyError:
        # The pre-check can race with another request; the unique identity
        # index is authoritative and the response keeps the existing UX.
        return _duplicate_report(payload, find_matches(payload))
    if decisions:
        log_review(matches, decisions, c["_id"])
    write_log("candidate", "create", g.current_user.user_id, g.current_user.name,
              biz_id=str(c["_id"]), detail=c.get("name", ""))
    return ok({"duplicated": False, "candidate": _candidate_view(c, mask=False),
               "application": application_to_dict(application) if application else None})


@bp.put("/api/candidates/<int:cid>")
@role_required(HR)
def update_candidate(cid: int):
    ensure_candidate_indexes()
    c = _get_candidate_or_404(cid)
    require_candidate_lock_owner(cid)
    payload = request.get_json(silent=True) or {}
    next_identity = {key: payload.get(key, c.get(key, "")) for key in ("name", "phone", "email")}
    identity_changed = any(next_identity[key] != c.get(key, "") for key in next_identity)
    matches = find_matches(next_identity, exclude_id=cid) if identity_changed else []
    decisions = validate_review(payload, matches, cid) if matches else None
    if matches and decisions is None:
        return _duplicate_report(payload, matches, cid)
    if decisions and "same" in decisions.values():
        raise BizError(BizCode.PARAM_INVALID, "该人员已有主档，请在已有主档维护资料，勿将两个现有档案改为同一人")
    fields = _fill_candidate(payload)
    set_fields = dict(fields)
    unset_fields = {}
    if identity_changed:
        next_phone = fields.get("phone", c.get("phone", ""))
        next_email = fields.get("email", c.get("email", ""))
        identity_set, identity_unset = identity_update(
            next_phone, next_email, exempt=bool(decisions) or bool(c.get("dedupe_exempt")),
        )
        set_fields.update(identity_set)
        unset_fields.update(identity_unset)
        full_key = full_identity_key({**c, **fields})
        if full_key:
            set_fields["identity_full_key"] = full_key
        else:
            unset_fields["identity_full_key"] = ""
    set_fields["updated_at"] = datetime.now()
    query = {"_id": cid}
    has_version = "version" in payload
    if has_version:
        try:
            query["version"] = int(payload["version"])
        except (TypeError, ValueError):
            raise BizError(BizCode.PARAM_INVALID, "version 必须是整数")
    update = {"$set": set_fields, "$inc": {"version": 1}}
    if unset_fields:
        update["$unset"] = unset_fields
    try:
        updated = col("candidates").find_one_and_update(
            query, update, return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        return _duplicate_report(payload, find_matches({**c, **fields}, exclude_id=cid), cid)
    if updated is None:
        if get_by_id("candidates", cid) is None:
            raise BizError(BizCode.NOT_FOUND, "候选人不存在")
        if has_version:
            raise BizError(BizCode.CONFLICT, "候选人信息已被其他人修改，请刷新后重试")
        raise BizError(BizCode.CONFLICT, "候选人信息更新失败，请刷新后重试")
    c = updated
    if decisions:
        log_review(matches, decisions, cid)
    write_log("candidate", "update", g.current_user.user_id, g.current_user.name, biz_id=str(cid))
    return ok({"duplicated": False, "candidate": _candidate_view(c, mask=False)})


@bp.delete("/api/candidates/<int:cid>")
@role_required(HR)
def delete_candidate(cid: int):
    """删除候选人（二次确认）：级联清理所有招聘数据和文件对象。"""
    _get_candidate_or_404(cid)
    require_candidate_lock_owner(cid)
    if request.args.get("confirm") != "1":
        raise BizError(BizCode.PARAM_INVALID, "删除需要二次确认（confirm=1）")
    return ok(purge_candidate(current_app, cid, g.current_user.user_id, g.current_user.name))


@bp.post("/api/candidates/<int:cid>/applications")
@role_required(HR, SUPER_ADMIN)
def assign_job(cid: int):
    c = _get_candidate_or_404(cid)
    require_candidate_lock_owner(cid)
    payload = request.get_json(silent=True) or {}
    job = get_by_id("jobs", int(payload.get("job_id") or 0))
    if job is None:
        raise BizError(BizCode.PARAM_INVALID, "职位不存在")
    # A manual HR assignment is the HR screening action itself. Legacy custom
    # templates without the v1.1 HR stage keep their original entry stage.
    configured_stages = {stage.stage_key for stage in job_stage_sequence(job)}
    assigned_stage = "hr_screen_passed" if "hr_screen_passed" in configured_stages else "new_resume"
    app_doc = create_application(
        c, job, source=payload.get("source", "manual"),
        operator_id=g.current_user.user_id,
        operator_name=g.current_user.name,
        initial_stage=assigned_stage,
        initial_lock_days=7,
        initial_reason="HR分配职位并进入HR筛选",
        hr_assignment=True,
    )
    return ok(application_to_dict(app_doc))


@bp.get("/api/candidates/<int:cid>/applications")
@role_required(*CANDIDATE_READ_ROLES)
def candidate_applications(cid: int):
    _get_candidate_or_404(cid)
    apps = col("applications").find({"candidate_id": cid}).sort("_id", -1)
    return ok([application_to_dict(a) for a in apps])


@bp.post("/api/candidates/<int:cid>/change-job")
@role_required(HR, SUPER_ADMIN)
def change_job(cid: int):
    from common.job_change import change_application_job

    candidate = _get_candidate_or_404(cid)
    require_candidate_lock_owner(cid)
    payload = request.get_json(silent=True) or {}
    job = _selected_candidate_job(payload)
    if not job:
        raise BizError(BizCode.PARAM_INVALID, "请选择新投递职位")
    try:
        application_id = int(payload.get("application_id", ""))
        version = int(payload.get("version", ""))
    except (ValueError, TypeError) as exc:
        raise BizError(BizCode.PARAM_INVALID, "application_id 和 version 必填") from exc
    application = change_application_job(
        candidate, application_id, job, version,
        str(payload.get("reason") or "HR更换投递职位").strip(),
    )
    return ok(application_to_dict(application))


@bp.get("/api/candidates/<int:cid>/delivery-analysis")
@role_required(*CANDIDATE_READ_ROLES)
def delivery_analysis(cid: int):
    """候选人的全量投递、阶段流转和面试评价统计。"""
    candidate = _get_candidate_or_404(cid)
    apps = list(col("applications").find({"candidate_id": cid}).sort("_id", -1))
    app_ids = [item["_id"] for item in apps]
    interviews = list(col("interviews").find({
        "application_id": {"$in": app_ids},
    }).sort("_id", -1)) if app_ids else []
    interview_ids = [item["_id"] for item in interviews]
    feedback_by_interview = {
        item["interview_id"]: item
        for item in col("interview_feedback").find({
            "interview_id": {"$in": interview_ids},
        })
    } if interview_ids else {}

    evaluated = []
    passed = 0
    for item in interviews:
        feedback = feedback_by_interview.get(item["_id"])
        if item.get("status") == "completed" and feedback and not feedback.get("skip_eval"):
            evaluated.append(item)
            if feedback.get("conclusion") == "pass":
                passed += 1

    details = []
    overall_highest = {"rank": -1, "name": "-"}
    recommendation_count = 0
    recommendation_passed = 0
    for app in apps:
        job = get_by_id("jobs", app.get("job_id")) or {}
        sequence = job_stage_sequence(job)
        rank_by_key = {stage.stage_key: index for index, stage in enumerate(sequence)}
        rank_by_key.update({
            "new_resume": 0, "pending_screen": 5, "hr_screen_passed": 10, "business_screen": 20,
            "pending_interview": 30, "interviewing": 30, "interview_passed": 30,
            "interview_1": 30, "interview_2": 40, "interview_3": 50, "hr_interview": 55,
            "hrbp_interview": 60, "offer_pending": 70, "offer_approval": 70, "offer": 75,
            "pending_onboard": 80, "onboarded": 90,
        })
        name_by_key = {stage.stage_key: stage.name for stage in sequence}
        transitions = list(col("stage_transitions").find({
            "application_id": app["_id"],
        }).sort("_id", 1))
        reached_keys = [app.get("current_stage", "")]
        reached_keys.extend(item.get("from_stage", "") for item in transitions)
        reached_keys.extend(item.get("to_stage", "") for item in transitions)
        reached = max(
            (key for key in reached_keys if key in rank_by_key),
            key=lambda key: rank_by_key[key],
            default=app.get("current_stage", ""),
        )
        reached_rank = rank_by_key.get(reached, -1)
        app_interviews = [item for item in interviews if item.get("application_id") == app["_id"]]
        round_rank = {"一面": 30, "二面": 40, "三面": 50, "HR面试": 55, "复试": 55}
        rounds = [item.get("round", "") for item in app_interviews if item.get("status") != "cancelled"]
        # A fresh screening delivery already has the template's first round
        # configured, but has not actually reached that round yet.
        round_stage = app.get("archived_from_stage") or app.get("current_stage", "")
        if app.get("interview_round") and round_stage in {
            "pending_interview", "interviewing", "interview_passed", "interview_1",
            "interview_2", "interview_3", "hr_interview", "re_interview",
        }:
            rounds.append(app["interview_round"])
        highest_round = max(rounds, key=lambda value: round_rank.get(value, -1), default="")
        reached_name = name_by_key.get(reached, STAGE_NAMES.get(reached, reached or "-"))
        if highest_round in round_rank and round_rank[highest_round] >= reached_rank:
            reached_rank = round_rank[highest_round]
            reached_name = highest_round
        if reached_rank > overall_highest["rank"]:
            overall_highest = {
                "rank": reached_rank,
                "name": reached_name,
            }
        recommendations = [item for item in transitions if item.get("to_stage") == "business_screen"]
        recommendation_count += len(recommendations)
        for recommendation in recommendations:
            departure = next((item for item in transitions
                              if item.get("from_stage") == "business_screen"
                              and item.get("to_stage") != "business_screen"
                              and item.get("_id", 0) > recommendation.get("_id", 0)), None)
            if departure and departure.get("to_stage") not in {
                "job_changed",
                "eliminated", "abandoned", "talent_pool", "new_resume", "pending_screen", "hr_screen_passed",
            }:
                recommendation_passed += 1
        timeline = [{
            "id": f"application-{app['_id']}", "title": "投递简历",
            "detail": "HR更换投递职位，重新开始简历筛选" if app.get("source") == "job_change" else app.get("source", ""),
            "operator_name": app.get("owner_name", ""),
            "created_at": dt(app.get("created_at")),
        }]
        timeline.extend({
            "id": f"transition-{item['_id']}",
            "title": "推荐业务复筛" if item.get("to_stage") == "business_screen"
                else f"进入{name_by_key.get(item.get('to_stage'), STAGE_NAMES.get(item.get('to_stage'), item.get('to_stage', '')))}",
            "detail": item.get("reason", ""), "operator_name": item.get("operator_name", ""),
            "created_at": dt(item.get("created_at")),
        } for item in transitions if item.get("from_stage"))
        for interview in app_interviews:
            timeline.append({
                "id": f"interview-{interview['_id']}", "title": f"安排{interview.get('round', '')}面试",
                "detail": f"面试时间：{dt(interview.get('start_at'))}；面试官：{interview.get('interviewer_name', '')}",
                "operator_name": "", "created_at": dt(interview.get("created_at")),
            })
            feedback = feedback_by_interview.get(interview["_id"])
            if feedback:
                timeline.append({
                    "id": f"feedback-{feedback['_id']}", "title": "提交面试评价",
                    "detail": {"pass": "通过", "fail": "不通过", "hold": "待定"}.get(feedback.get("conclusion"), "待核对")
                        + "；" + feedback.get("comment", ""),
                    "operator_name": feedback.get("evaluator_name", ""),
                    "created_at": dt(feedback.get("updated_at") or feedback.get("created_at")),
                })
        timeline.reverse()
        timeline.sort(key=lambda item: item["created_at"], reverse=True)
        details.append({
            **application_to_dict(app),
            "created_at": dt(app.get("created_at")),
            "stage_name": name_by_key.get(
                app.get("current_stage", ""),
                STAGE_NAMES.get(app.get("current_stage", ""), app.get("current_stage", "-")),
            ),
            "highest_stage_name": reached_name,
            "timeline": timeline,
            "transitions": [{
                "from_stage": item.get("from_stage", ""),
                "to_stage": item.get("to_stage", ""),
                "to_stage_name": name_by_key.get(
                    item.get("to_stage", ""),
                    STAGE_NAMES.get(item.get("to_stage", ""), item.get("to_stage", "-")),
                ),
                "reason": item.get("reason", ""),
                "operator_name": item.get("operator_name", ""),
                "created_at": dt(item.get("created_at")),
            } for item in transitions],
            "interviews": [{
                "id": item["_id"],
                "round": item.get("round", ""),
                "status": item.get("status", ""),
                "interviewer_name": item.get("interviewer_name", ""),
                "start_at": dt(item.get("start_at")),
                "conclusion": (feedback_by_interview.get(item["_id"]) or {}).get("conclusion", ""),
            } for item in app_interviews],
        })

    app_by_id = {item["_id"]: item for item in apps}
    interview_by_id = {item["_id"]: item for item in interviews}
    offers = list(col("offers").find({"application_id": {"$in": app_ids}})) if app_ids else []
    offer_ids = [item["_id"] for item in offers]
    approvals = list(col("offer_approvals").find({"offer_id": {"$in": offer_ids}})) if offer_ids else []
    offer_by_id = {item["_id"]: item for item in offers}
    approval_by_id = {item["_id"]: item for item in approvals}
    attachment_docs = list(col("attachments").find({"candidate_id": cid}).sort("_id", 1))

    activities = []

    def add_activity(activity_id, title, detail, created_at, operator_name="", job_name="", kind="operation"):
        activities.append({
            "id": str(activity_id), "kind": kind, "title": title,
            "detail": detail or "", "operator_name": operator_name or "系统",
            "job_name": job_name or "", "created_at": dt(created_at),
            "_sort_at": created_at or datetime.min,
        })

    # 候选人创建/首次投递和后续简历附件上传时间。
    add_activity(
        f"candidate-{cid}", "简历投递", candidate.get("source") or "候选人进入系统",
        candidate.get("created_at"), kind="resume",
    )
    for attachment in attachment_docs:
        add_activity(
            f"attachment-{attachment['_id']}", "简历附件上传",
            attachment.get("file_name", ""), attachment.get("created_at"), kind="resume",
        )

    related = [("candidate", [cid]), ("application", app_ids), ("interview", interview_ids),
               ("offer", offer_ids), ("offer_approval", list(approval_by_id)),
               ("attachment", [item["_id"] for item in attachment_docs])]
    logs = col("operation_logs").find({
        "$or": [{"biz_type": kind, "biz_id": {"$in": [str(value) for value in ids]}}
                for kind, ids in related if ids],
    }).sort("_id", 1)
    passive_actions = {"view", "list_view", "file_preview", "file_download", "download"}
    for log in logs:
        if log.get("action") in passive_actions:
            continue
        biz_type = log.get("biz_type", "")
        related_job = ""
        if biz_type == "application":
            related_job = (get_by_id("jobs", app_by_id.get(int(log.get("biz_id", 0)), {}).get("job_id")) or {}).get("name", "")
        elif biz_type == "interview":
            interview = interview_by_id.get(int(log.get("biz_id", 0)), {})
            app = app_by_id.get(interview.get("application_id"), {})
            related_job = (get_by_id("jobs", app.get("job_id")) or {}).get("name", "")
        elif biz_type == "offer":
            offer = offer_by_id.get(int(log.get("biz_id", 0)), {})
            related_job = (get_by_id("jobs", offer.get("job_id")) or {}).get("name", "")
        elif biz_type == "offer_approval":
            approval = approval_by_id.get(int(log.get("biz_id", 0)), {})
            offer = offer_by_id.get(approval.get("offer_id"), {})
            related_job = (get_by_id("jobs", offer.get("job_id")) or {}).get("name", "")
        add_activity(
            f"log-{log['_id']}", log.get("action", "系统操作"), log.get("detail", ""),
            log.get("created_at"), log.get("operator_name", ""), related_job,
        )
    activities.sort(key=lambda item: item.pop("_sort_at"), reverse=True)

    return ok({
        "summary": {
            "total_deliveries": len(apps),
            "highest_stage": overall_highest["name"],
            "recommendations": recommendation_count,
            "passed_recommendations": recommendation_passed,
            "recommendation_pass_rate": round(recommendation_passed / recommendation_count * 100, 1) if recommendation_count else 0,
            "interviews": sum(item.get("status") != "cancelled" for item in interviews),
            "evaluated_interviews": len(evaluated),
            "passed_interviews": passed,
            "interview_pass_rate": round(passed / len(evaluated) * 100, 1) if evaluated else 0,
        },
        "applications": details,
        "activities": activities,
    })


@bp.get("/api/applications/<int:app_id>/transitions")
@role_required(*CANDIDATE_READ_ROLES)
def application_transitions(app_id: int):
    rows = col("stage_transitions").find({"application_id": app_id}).sort("_id", 1)
    return ok([{
        "from_stage": t.get("from_stage", ""), "to_stage": t.get("to_stage", ""),
        "reason": t.get("reason", ""), "operator_name": t.get("operator_name", ""),
        "created_at": dt(t.get("created_at")),
    } for t in rows])


# ---------------- 导入导出 ----------------

@bp.get("/api/candidates/import-template")
@role_required(*CANDIDATE_READ_ROLES)
def import_template():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["姓名", "性别", "手机号", "邮箱", "城市", "来源"])
    writer.writerow(["张三", "男", "13800000000", "zhangsan@example.com", "上海", "manual"])
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=candidate_template.csv"})


@bp.post("/api/candidates/import")
@role_required(HR)
def import_candidates():
    ensure_candidate_indexes()
    job = _selected_candidate_job(request.form)
    file = request.files.get("file")
    if file is None or not file.filename:
        raise BizError(BizCode.PARAM_INVALID, "请上传导入文件")
    ext = os.path.splitext(file.filename)[1].lower()
    rows = []
    try:
        if ext == ".csv":
            content = io.TextIOWrapper(file.stream, encoding="utf-8-sig")
            reader = csv.reader(content)
            next(reader, None)
            rows = [r for r in reader if any(x.strip() for x in r)]
        elif ext == ".xlsx":
            import openpyxl

            wb = openpyxl.load_workbook(file.stream, read_only=True)
            sheet = wb.active
            data = list(sheet.iter_rows(values_only=True))
            rows = [[str(v or "") for v in r] for r in data[1:] if any(v for v in r)]
        else:
            raise BizError(BizCode.PARAM_INVALID, "仅支持 CSV/XLSX 导入")
    except BizError:
        raise
    except Exception as e:
        raise BizError(BizCode.PARAM_INVALID, f"文件解析失败: {e}")

    success, duplicates, errors = 0, [], []
    for idx, row in enumerate(rows, start=2):
        row = list(row) + [""] * (6 - len(row))
        name, gender, phone, email, city, source = [x.strip() for x in row[:6]]
        if not name:
            errors.append({"row": idx, "msg": "姓名缺失"})
            continue
        payload = {"name": name, "gender": gender, "phone": phone, "email": email,
                   "city": city, "source": source or "manual"}
        if job:
            payload["job_id"] = job["_id"]
        matches = find_matches(payload)
        if matches:
            duplicates.append({"row": idx, "name": name, "phone": phone, "email": email,
                               "payload": payload, "review": _duplicate_report_data(payload, matches)})
            continue
        candidate_doc = {
            "name": name, "gender": gender, "phone": phone, "email": email, "city": city,
            "age": None, "highest_education": "", "major": "",
            "education": [], "work_experience": [], "tags": "", "remark": "",
            "source": source or "manual",
            "owner_id": g.current_user.user_id, "owner_name": g.current_user.name,
            "version": 1,
        }
        candidate_doc.update(identity_keys(phone, email))
        full_key = full_identity_key(candidate_doc)
        if full_key:
            candidate_doc["identity_full_key"] = full_key
        try:
            _insert_candidate_with_job(candidate_doc, job)
        except DuplicateKeyError:
            duplicates.append({"row": idx, "name": name, "phone": phone, "email": email,
                               "payload": payload, "review": _duplicate_report_data(payload, find_matches(payload))})
            continue
        except BizError as exc:
            errors.append({"row": idx, "msg": str(exc)})
            continue
        success += 1
    write_log("candidate", "import", g.current_user.user_id, g.current_user.name,
              detail=f"成功{success} 重复{len(duplicates)} 错误{len(errors)}")
    return ok({"success_count": success, "duplicates": duplicates, "errors": errors})


@bp.get("/api/candidates/export")
@role_required(HR)
def export_candidates():
    args = request.args
    query = {}
    if args.get("keyword"):
        kw = args["keyword"]
        query["$or"] = [{"name": {"$regex": kw}}, {"phone": {"$regex": kw}}]
    items = list(col("candidates").find(query).sort("_id", 1))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["姓名", "性别", "手机号", "邮箱", "城市", "来源", "创建时间"])
    for c in items:
        writer.writerow([c.get("name", ""), c.get("gender", ""), c.get("phone", ""),
                         c.get("email", ""), c.get("city", ""), c.get("source", ""),
                         dt(c.get("created_at"))])
    col("export_logs").insert_one({
        "exporter_id": g.current_user.user_id, "exporter_name": g.current_user.name,
        "scene": "candidates", "conditions": json.dumps(dict(args), ensure_ascii=False),
        "row_count": len(items), "created_at": __import__("datetime").datetime.now(),
    })
    write_log("export", "candidates", g.current_user.user_id, g.current_user.name,
              detail=f"rows={len(items)}")
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=candidates.csv"})


# ---------------- 简历上传与解析 ----------------

@bp.post("/api/resume/parse-upload")
@role_required(*RESUME_ACCESS_ROLES)
def resume_parse_upload():
    """解析尚未关联候选人的简历，供新增候选人表单预填基础信息。"""
    file = request.files.get("file")
    if file is None or not file.filename:
        raise BizError(BizCode.PARAM_INVALID, "请上传简历文件")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".pdf", ".docx", ".jpg", ".jpeg", ".png"}:
        raise BizError(BizCode.PARAM_INVALID, "新增候选人自动解析支持 PDF、DOCX、JPG、PNG")

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="resume-parse-", suffix=ext, delete=False) as temp:
            temp_path = temp.name
        file.save(temp_path)
        if os.path.getsize(temp_path) > 10 * 1024 * 1024:
            raise BizError(BizCode.PARAM_INVALID, "简历文件不能超过 10MB")
        fields, status = parse_resume_file(temp_path, file.filename)
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass

    return ok({
        "file_name": secure_filename(file.filename) or "resume",
        "parse_status": status,
        "fields": fields,
        "message": "解析成功，请核对并修改" if status == "system" else "未能识别出基础信息，请人工填写",
    })

@bp.post("/api/resume/upload")
@role_required(*RESUME_ACCESS_ROLES)
def resume_upload():
    file = request.files.get("file")
    if file is None or not file.filename:
        raise BizError(BizCode.PARAM_INVALID, "请上传简历文件")
    try:
        candidate_id = int(request.form.get("candidate_id") or 0)
    except (TypeError, ValueError):
        raise BizError(BizCode.PARAM_INVALID, "候选人编号无效")
    if candidate_id <= 0:
        raise BizError(BizCode.PARAM_INVALID, "请先创建候选人并绑定应聘职位后再上传简历")
    _get_candidate_or_404(candidate_id)
    require_candidate_lock_owner(candidate_id)
    query = {"candidate_id": candidate_id}
    if "job_id" in request.form:
        job = _selected_candidate_job(request.form)
        query["job_id"] = job["_id"]
    application = next((app for app in col("applications").find(query).sort("_id", -1)
                        if get_by_id("jobs", app.get("job_id")) is not None), None)
    if application is None:
        raise BizError(BizCode.PARAM_INVALID, "请先为候选人绑定应聘职位后再上传简历")
    try:
        meta = save_uploaded_file(
            current_app, file, biz_type="resume",
            operator_id=g.current_user.user_id, operator_name=g.current_user.name,
        )
    except MongoUnavailable:
        raise BizError(5001, "文件服务不可用：MongoDB 未连接", http_status=200)
    except StorageError as e:
        raise BizError(BizCode.PARAM_INVALID, str(e))
    att = insert_doc("attachments", {
        "candidate_id": candidate_id, "file_name": meta["originalName"],
        "job_id": application["job_id"], "application_id": application["_id"],
        "file_path": meta["objectKey"], "file_id": meta["id"],
        "file_type": "resume", "parse_status": "",
    })
    if candidate_id:
        from bson import ObjectId

        col("files").update_one(
            {"_id": ObjectId(meta["id"])},
            {"$set": {"candidate_id": candidate_id, "job_id": application["job_id"]}},
        )
    return ok({"attachment_id": att["_id"], "file_name": att["file_name"], "file_id": meta["id"]})


@bp.post("/api/resume/parse")
@role_required(*RESUME_ACCESS_ROLES)
def resume_parse():
    payload = request.get_json(silent=True) or {}
    att = get_by_id("attachments", int(payload.get("attachment_id") or 0))
    if att is None:
        raise BizError(BizCode.NOT_FOUND, "附件不存在")
    local_path, is_tmp = resolve_local(current_app, att.get("file_path", ""))
    try:
        fields, status, parsed_text = parse_resume_file_with_text(local_path, att.get("file_name", ""))
    finally:
        if is_tmp:
            from common.file_service import get_storage

            get_storage(current_app).cleanup_local(local_path, att.get("file_path", ""))
    update_doc("attachments", att["_id"], {
        "parse_status": status,
        "parsed_fields": fields,
        "parsed_text": parsed_text,
    })
    if status == "failed":
        return ok({
            "parse_status": status, "fields": fields,
            "message": "未能识别出可靠信息，请人工录入或检查 OCR/AI 配置",
        })
    return ok({"parse_status": status, "fields": fields, "message": "解析成功，请核对后保存"})


@bp.get("/api/attachments/<int:att_id>")
@role_required(*RESUME_ACCESS_ROLES)
def download_attachment(att_id: int):
    att = get_by_id("attachments", att_id)
    if att is None:
        raise BizError(BizCode.NOT_FOUND, "附件不存在")
    try:
        data = read_file_bytes(current_app, att.get("file_path", ""))
    except StorageError as e:
        raise BizError(BizCode.NOT_FOUND, str(e))
    write_log("attachment", "download", g.current_user.user_id, g.current_user.name,
              biz_id=str(att_id), detail=f"candidate={att.get('candidate_id', '')}; file={att.get('file_name', '')}")
    filename = att.get("file_name", "") or "resume"
    # Werkzeug 的开发服务器和部分代理只能用 Latin-1 编码响应头，直接把
    # 中文简历名放进 Content-Disposition 会导致响应头编码异常、浏览器显示
    # “请求错误”。同时提供 ASCII 兜底名和 RFC 5987 UTF-8 文件名。
    fallback_name = secure_filename(filename) or "resume"
    encoded_name = quote(filename, safe="")
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Response(data.getvalue(), mimetype=content_type,
                    headers={"Content-Disposition":
                             f'inline; filename="{fallback_name}"; filename*=UTF-8\'\'{encoded_name}'})
