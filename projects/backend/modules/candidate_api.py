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
    highest_education_from_records,
    major_from_records,
    parse_resume_file,
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


def _find_duplicates(phone: str, email: str, exclude_id: int = None):
    conds = []
    if phone:
        conds.extend([{"phone": phone}, {"phone_key": identity_keys(phone, {}).get("phone_key")}])
    if email:
        conds.extend([{"email": email}, {"email_key": identity_keys({}, email).get("email_key")}])
    if not conds:
        return []
    query = {"$or": conds}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    return list(col("candidates").find(query))


def _latest_application(candidate_id: int):
    app = col("applications").find_one({"candidate_id": candidate_id}, sort=[("_id", -1)])
    return reconcile_application_status(app) if app else None


def _candidate_view(c: dict, mask: bool = True) -> dict:
    # mask 参数仅保留兼容性，不能让普通角色通过 mask=0 关闭脱敏。
    data = redact_candidate(c, include_pii=can_view_pii() and not mask)
    data["version"] = int(c.get("version", 1))
    return data


def _duplicate_candidate_view(c: dict) -> dict:
    data = _candidate_view(c, mask=False)
    data["lock"] = lock_info_for_candidate(c["_id"])
    return data


def _candidate_row(c: dict, mask: bool) -> dict:
    data = _candidate_view(c, mask=mask)
    education = list(c.get("education") or [])
    work_experience = list(c.get("work_experience") or [])

    def latest_record(records):
        return max(
            records,
            key=lambda item: str(item.get("end") or item.get("graduate_at") or item.get("start") or ""),
            default={},
        )

    data["education_summary"] = latest_record(education)
    data["work_summary"] = latest_record(work_experience)
    app = _latest_application(c["_id"])
    if app:
        job = get_by_id("jobs", app["job_id"]) or {}
        data["latest_application"] = {
            "id": app["_id"], "job_name": job.get("name", ""),
            "current_stage": app.get("current_stage", ""), "status": app.get("status", ""),
        }
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
    query = {}
    if args.get("keyword"):
        kw = args["keyword"]
        query["$or"] = [{"name": {"$regex": kw}}, {"phone": {"$regex": kw}},
                        {"email": {"$regex": kw}}]
    if args.get("highest_education"):
        query["highest_education"] = args["highest_education"]
    if args.get("tag"):
        query["tags"] = {"$regex": args["tag"]}
    items = list(col("candidates").find(query).sort("_id", -1))
    if args.get("source"):
        source = args["source"]
        source_candidate_ids = set(col("applications").distinct("candidate_id", {"source": source}))
        items = [
            item for item in items
            if item.get("source") == source or item["_id"] in source_candidate_ids
        ]
    if args.get("job_dept_id"):
        job_ids = col("jobs").distinct("_id", {"dept_id": args["job_dept_id"]})
        department_candidate_ids = set(col("applications").distinct(
            "candidate_id", {"job_id": {"$in": job_ids}},
        )) if job_ids else set()
        items = [item for item in items if item["_id"] in department_candidate_ids]
    category = args.get("category", "")
    if category == "pending":
        items = [item for item in items if "待定" in (item.get("tags") or "")]
    elif category == "recommended":
        recommended_sources = ["referral", "headhunt", "talent_pool", "business_recommendation"]
        recommended_ids = set(col("applications").distinct(
            "candidate_id", {"source": {"$in": recommended_sources}},
        ))
        items = [
            item for item in items
            if item["_id"] in recommended_ids or item.get("source") in recommended_sources
        ]
    # 应聘记录相关过滤（职位/阶段）
    if args.get("job_id") or args.get("stage"):
        filtered = []
        for c in items:
            app_query = {"candidate_id": c["_id"]}
            if args.get("job_id"):
                app_query["job_id"] = int(args["job_id"])
            if args.get("stage"):
                requested_stage = args["stage"]
                if requested_stage == "pending_screen":
                    app_query["current_stage"] = {"$in": ["pending_screen", "new_resume"]}
                else:
                    app_query["current_stage"] = requested_stage
            if col("applications").find_one(app_query):
                filtered.append(c)
            elif args.get("stage") == "pending_screen" and not args.get("job_id") \
                    and not col("applications").find_one({"candidate_id": c["_id"]}):
                # No application means the candidate is still waiting for HR screening.
                filtered.append(c)
        items = filtered
    if args.get("locked") == "1":
        items = [c for c in items if active_lock_for_candidate(c["_id"])]
    page = max(int(args.get("page", 1)), 1)
    page_size = min(max(int(args.get("page_size", 10)), 1), 100)
    sliced, total, page, page_size = paginate(items, page, page_size)
    write_log("candidate", "list_view", g.current_user.user_id, g.current_user.name,
              detail=f"page={page}; page_size={page_size}; rows={len(sliced)}")
    return paged([_candidate_row(c, mask) for c in sliced], total, page, page_size)


@bp.get("/api/candidates/classification-summary")
@role_required(*CANDIDATE_READ_ROLES)
def candidate_classification_summary():
    candidates = list(col("candidates").find({}, {"_id": 1, "source": 1, "tags": 1}))
    applications = list(col("applications").find(
        {}, {"_id": 1, "candidate_id": 1, "current_stage": 1, "source": 1},
    ).sort("_id", -1))
    latest_by_candidate = {}
    recommended_ids = set()
    recommended_sources = {"referral", "headhunt", "talent_pool", "business_recommendation"}
    for application in applications:
        candidate_id = application.get("candidate_id")
        if candidate_id not in latest_by_candidate:
            latest_by_candidate[candidate_id] = application
        if application.get("source") in recommended_sources:
            recommended_ids.add(candidate_id)

    stage_counts = {}
    for candidate in candidates:
        application = latest_by_candidate.get(candidate["_id"])
        stage = application.get("current_stage", "pending_screen") if application else "pending_screen"
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    stage_counts["pending_screen"] = (
        stage_counts.get("pending_screen", 0) + stage_counts.get("new_resume", 0)
    )
    pending_count = sum(1 for candidate in candidates if "待定" in (candidate.get("tags") or ""))
    recommended_count = sum(
        1 for candidate in candidates
        if candidate["_id"] in recommended_ids or candidate.get("source") in recommended_sources
    )
    unassigned_count = sum(1 for candidate in candidates if candidate["_id"] not in latest_by_candidate)
    return ok({
        "stage_counts": stage_counts,
        "categories": {
            "unprocessed": stage_counts.get("pending_screen", 0),
            "pending": pending_count,
            "recommended": recommended_count,
        },
        "unassigned": unassigned_count,
    })


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
        if not str(payload.get("highest_education") or "").strip():
            fields["highest_education"] = highest_education_from_records(fields["education"])
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
    phone = (payload.get("phone") or "").strip()
    email = (payload.get("email") or "").strip()
    duplicates = _find_duplicates(phone, email)
    if duplicates and not payload.get("force"):
        return ok({
            "duplicated": True,
            "duplicates": [_duplicate_candidate_view(c) for c in duplicates],
        })
    doc = {
        "name": "", "gender": "", "phone": "", "email": "", "city": "",
        "age": None, "highest_education": "", "major": "",
        "education": [], "work_experience": [], "tags": "", "remark": "",
        "source": "manual",
        "owner_id": payload.get("owner_id") or g.current_user.user_id,
        "owner_name": payload.get("owner_name") or g.current_user.name,
    }
    doc.update(_fill_candidate(payload))
    set_identity, _ = identity_update(doc.get("phone"), doc.get("email"), exempt=bool(payload.get("force")))
    doc.update(set_identity)
    doc["version"] = 1
    try:
        c = insert_doc("candidates", doc)
    except DuplicateKeyError:
        # The pre-check can race with another request; the unique identity
        # index is authoritative and the response keeps the existing UX.
        duplicates = _find_duplicates(phone, email)
        return ok({
            "duplicated": True,
            "duplicates": [_duplicate_candidate_view(d) for d in duplicates],
        })
    write_log("candidate", "create", g.current_user.user_id, g.current_user.name,
              biz_id=str(c["_id"]), detail=c.get("name", ""))
    return ok({"duplicated": False, "candidate": _candidate_view(c, mask=False)})


@bp.put("/api/candidates/<int:cid>")
@role_required(HR)
def update_candidate(cid: int):
    ensure_candidate_indexes()
    c = _get_candidate_or_404(cid)
    require_candidate_lock_owner(cid)
    payload = request.get_json(silent=True) or {}
    if "phone" in payload or "email" in payload:
        duplicates = _find_duplicates(
            payload.get("phone", c.get("phone", "")),
            payload.get("email", c.get("email", "")), exclude_id=cid)
        if duplicates and not payload.get("force"):
            return ok({"duplicated": True,
                       "duplicates": [_candidate_view(d, mask=False) for d in duplicates]})
    fields = _fill_candidate(payload)
    identity_changed = "phone" in payload or "email" in payload or bool(payload.get("force"))
    set_fields = dict(fields)
    unset_fields = {}
    if identity_changed:
        next_phone = fields.get("phone", c.get("phone", ""))
        next_email = fields.get("email", c.get("email", ""))
        identity_set, identity_unset = identity_update(
            next_phone, next_email, exempt=bool(payload.get("force")),
        )
        set_fields.update(identity_set)
        unset_fields.update(identity_unset)
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
        next_phone = fields.get("phone", c.get("phone", ""))
        next_email = fields.get("email", c.get("email", ""))
        duplicates = _find_duplicates(next_phone, next_email, exclude_id=cid)
        return ok({
            "duplicated": True,
            "duplicates": [_candidate_view(d, mask=False) for d in duplicates],
        })
    if updated is None:
        if get_by_id("candidates", cid) is None:
            raise BizError(BizCode.NOT_FOUND, "候选人不存在")
        if has_version:
            raise BizError(BizCode.CONFLICT, "候选人信息已被其他人修改，请刷新后重试")
        raise BizError(BizCode.CONFLICT, "候选人信息更新失败，请刷新后重试")
    c = updated
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
    for app in apps:
        job = get_by_id("jobs", app.get("job_id")) or {}
        sequence = job_stage_sequence(job)
        rank_by_key = {stage.stage_key: index for index, stage in enumerate(sequence)}
        name_by_key = {stage.stage_key: stage.name for stage in sequence}
        transitions = list(col("stage_transitions").find({
            "application_id": app["_id"],
        }).sort("_id", 1))
        reached_keys = [app.get("current_stage", "")]
        reached_keys.extend(item.get("to_stage", "") for item in transitions)
        reached = max(
            (key for key in reached_keys if key in rank_by_key),
            key=lambda key: rank_by_key[key],
            default=app.get("current_stage", ""),
        )
        reached_rank = rank_by_key.get(reached, -1)
        if reached_rank > overall_highest["rank"]:
            overall_highest = {
                "rank": reached_rank,
                "name": name_by_key.get(reached, STAGE_NAMES.get(reached, reached or "-")),
            }
        app_interviews = [item for item in interviews if item.get("application_id") == app["_id"]]
        details.append({
            **application_to_dict(app),
            "created_at": dt(app.get("created_at")),
            "stage_name": name_by_key.get(
                app.get("current_stage", ""),
                STAGE_NAMES.get(app.get("current_stage", ""), app.get("current_stage", "-")),
            ),
            "highest_stage_name": name_by_key.get(
                reached, STAGE_NAMES.get(reached, reached or "-"),
            ),
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

    related_ids = {str(cid)}
    related_ids.update(str(item["_id"]) for item in apps)
    related_ids.update(str(item["_id"]) for item in interviews)
    related_ids.update(str(item["_id"]) for item in offers)
    related_ids.update(str(item["_id"]) for item in approvals)
    related_ids.update(str(item["_id"]) for item in attachment_docs)
    logs = col("operation_logs").find({
        "biz_id": {"$in": list(related_ids)},
        "biz_type": {"$in": ["candidate", "application", "interview", "offer", "offer_approval", "attachment"]},
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
            "interviews": len(interviews),
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
        if _find_duplicates(phone, email):
            duplicates.append({"row": idx, "name": name, "phone": phone, "email": email})
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
        try:
            insert_doc("candidates", candidate_doc)
        except DuplicateKeyError:
            duplicates.append({"row": idx, "name": name, "phone": phone, "email": email})
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
    if ext not in {".pdf", ".docx"}:
        raise BizError(BizCode.PARAM_INVALID, "新增候选人自动解析目前仅支持 PDF/DOCX")

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
    candidate_id = int(request.form.get("candidate_id") or 0)
    if candidate_id:
        _get_candidate_or_404(candidate_id)
        require_candidate_lock_owner(candidate_id)
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
        "file_path": meta["objectKey"], "file_id": meta["id"],
        "file_type": "resume", "parse_status": "",
    })
    if candidate_id:
        from bson import ObjectId

        col("files").update_one(
            {"_id": ObjectId(meta["id"])},
            {"$set": {"candidate_id": candidate_id}},
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
        fields, status = parse_resume_file(local_path, att.get("file_name", ""))
    finally:
        if is_tmp:
            from common.file_service import get_storage

            get_storage(current_app).cleanup_local(local_path, att.get("file_path", ""))
    update_doc("attachments", att["_id"], {
        "parse_status": status,
        "parsed_fields": fields,
    })
    if status == "failed":
        return ok({
            "parse_status": status, "fields": fields,
            "message": "简历解析失败（图片简历暂不支持自动识别），请人工录入",
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
