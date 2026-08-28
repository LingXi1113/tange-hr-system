"""面试管理（PRD v1.1 Sprint 4）。

- 集合：interviews（面试安排）+ interview_feedback（面试反馈）；
- 面试必须绑定现有候选人、职位与应聘记录；
- 同一候选人同一时间不能有两场有效面试；时间不能早于当前时间；
- 状态：待安排→已邀请→已确认→已完成 / 已取消；改期保留原记录与原因；
- 完成后必须有反馈或显式"暂不评价"；
- 反馈通过→应聘记录推进"面试通过"；不通过→淘汰（必填原因）；
- 全部动作写入 operation_logs。
"""
from datetime import datetime, timedelta
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from flask import Blueprint, current_app, g, request

from common.background_failures import record_background_failure, resolve_background_failure
from common.db import col, get_by_id, insert_doc, update_doc, dt
from common.decorators import login_required, role_required
from common.errors import BizError
from common.flow import (
    advance_interview_round, application_to_dict, configured_interview_rounds,
    expected_interview_round, move_application,
)
from common.interview_guard import candidate_schedule_guard
from common.logstore import write_log
from common.response import BizCode, ok
from common.roles import HR
from common.stages import INTERVIEW_ROUNDS
from common.status import APP_IN_PROGRESS
from common.consistency import require_interview_application
from common.stage_rules import add_application_to_talent_pool

bp = Blueprint("interview_api", __name__, url_prefix="/api/interviews")

INTERVIEW_TYPES = ("onsite", "video", "phone")

# 面试记录必须挂在当前面试阶段；旧版阶段名继续兼容，并与面试轮次一一对应。
INTERVIEW_STAGE_ROUNDS = {
    "interview_1": "一面", "interview_2": "二面", "interview_3": "三面",
    "hr_interview": "HR面试", "re_interview": "复试",
}

# 状态：待安排 / 已邀请 / 已确认 / 已完成 / 已取消 / 已改期
IV_PENDING, IV_INVITED, IV_CONFIRMED, IV_COMPLETED, IV_CANCELLED, IV_RESCHEDULED = (
    "pending", "invited", "confirmed", "completed", "cancelled", "rescheduled",
)
INTERVIEW_FLOW = {
    IV_PENDING: [IV_INVITED, IV_RESCHEDULED, IV_CANCELLED],
    IV_INVITED: [IV_CONFIRMED, IV_RESCHEDULED, IV_CANCELLED],
    IV_CONFIRMED: [IV_COMPLETED, IV_RESCHEDULED, IV_CANCELLED],
    IV_RESCHEDULED: [IV_INVITED, IV_CONFIRMED, IV_CANCELLED],
    IV_COMPLETED: [],
    IV_CANCELLED: [],
}
# 有效面试（参与时间冲突校验的状态）
VALID_STATUSES = [IV_PENDING, IV_INVITED, IV_CONFIRMED, IV_RESCHEDULED]

CONCLUSIONS = ("pass", "hold", "fail")


def _parse_time(value, field: str) -> datetime:
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime((value or "").strip(), fmt)
        except (TypeError, ValueError):
            continue
    raise BizError(BizCode.PARAM_INVALID, f"{field} 格式应为 YYYY-MM-DD HH:MM")


def _get_or_404(interview_id: int) -> dict:
    doc = get_by_id("interviews", interview_id)
    if doc is None:
        raise BizError(BizCode.NOT_FOUND, "面试不存在")
    return doc


def _validate_time_window(start_at: datetime, end_at: datetime):
    if start_at < datetime.now():
        raise BizError(BizCode.PARAM_INVALID, "面试时间不能早于当前时间")
    if end_at <= start_at:
        raise BizError(BizCode.PARAM_INVALID, "结束时间必须晚于开始时间")


def _check_conflict(candidate_id: int, start_at: datetime, end_at: datetime,
                    exclude_id: int = None):
    """同一候选人同一时间不能存在两场有效面试。"""
    query = {
        "candidate_id": candidate_id,
        "status": {"$in": VALID_STATUSES},
        "start_at": {"$lt": end_at},
        "end_at": {"$gt": start_at},
    }
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    conflict = col("interviews").find_one(query)
    if conflict:
        raise BizError(BizCode.DUPLICATED,
                       f"该候选人在此时间段已有面试（{conflict['_id']}），请调整时间")


def _resolve_bindings(payload: dict):
    """校验候选人/职位/应聘记录绑定，返回 (candidate, job, application)。"""
    application_id = payload.get("application_id")
    app_doc = get_by_id("applications", int(application_id or 0))
    if app_doc is None:
        raise BizError(BizCode.PARAM_INVALID, "必须绑定有效的应聘记录")
    candidate = get_by_id("candidates", app_doc["candidate_id"])
    job = get_by_id("jobs", app_doc["job_id"])
    if candidate is None or job is None:
        raise BizError(BizCode.PARAM_INVALID, "应聘记录关联的候选人或职位不存在")
    # 显式传入的 candidate_id/job_id 必须与应聘记录一致
    if payload.get("candidate_id") and int(payload["candidate_id"]) != candidate["_id"]:
        raise BizError(BizCode.PARAM_INVALID, "候选人与应聘记录不匹配")
    if payload.get("job_id") and int(payload["job_id"]) != job["_id"]:
        raise BizError(BizCode.PARAM_INVALID, "职位与应聘记录不匹配")
    app_doc = require_interview_application(app_doc)
    return candidate, job, app_doc


def _interview_view(doc: dict) -> dict:
    candidate = get_by_id("candidates", doc["candidate_id"]) or {}
    job = get_by_id("jobs", doc["job_id"]) or {}
    return {
        "id": doc["_id"],
        "candidate_id": doc["candidate_id"],
        "candidate_name": candidate.get("name", ""),
        "job_id": doc["job_id"],
        "job_name": job.get("name", ""),
        "application_id": doc.get("application_id"),
        "round": doc.get("round", ""),
        "type": doc.get("type", ""),
        "start_at": dt(doc.get("start_at"))[:16],
        "end_at": dt(doc.get("end_at"))[:16],
        "location": doc.get("location", ""),
        "meeting_link": doc.get("meeting_link", ""),
        "interviewer_name": doc.get("interviewer_name", ""),
        "interviewer_contact": doc.get("interviewer_contact", ""),
        "template_id": doc.get("template_id"),
        # summary 为面试内容摘要；旧数据没有该字段时兼容展示原备注。
        "summary": doc.get("summary", doc.get("remark", "")),
        "remark": doc.get("remark", ""),
        "status": doc.get("status", IV_PENDING),
        "conclusion_applied": bool(doc.get("conclusion_applied")),
        "conclusion_action": doc.get("conclusion_action", ""),
        "version": doc.get("version", 1),
        "reschedule_history": doc.get("reschedule_history", []),
        "created_at": dt(doc.get("created_at")),
        "updated_at": dt(doc.get("updated_at")),
    }


def _notify_interview(doc: dict, candidate_name: str):
    """面试提醒：按面试时间幂等（改期后时间变化会再次提醒）。"""
    try:
        from common.notifier import notify_hr

        notify_hr(
            "interview_remind", "面试安排提醒",
            f"「{candidate_name}」的{doc.get('round', '')}面试已安排在 "
            f"{doc['start_at']:%Y-%m-%d %H:%M}",
            "interview", doc["_id"], "/interviews",
            f"interview_remind:{doc['_id']}:{doc['start_at']:%Y%m%d%H%M}",
        )
    except Exception as exc:
        current_app.logger.exception("面试通知发送失败 interview_id=%s", doc.get("_id"))
        record_background_failure("interview_notification", doc.get("_id"), exc)
    else:
        resolve_background_failure("interview_notification", doc.get("_id"))


def _feedback_view(doc: dict) -> dict:
    return {
        "id": doc["_id"],
        "interview_id": doc["interview_id"],
        "dimension_scores": doc.get("dimension_scores", []),
        "conclusion": doc.get("conclusion", ""),
        "comment": doc.get("comment", ""),
        "risk_note": doc.get("risk_note", ""),
        "suggested_salary": doc.get("suggested_salary", ""),
        "evaluator_name": doc.get("evaluator_name", ""),
        "skip_eval": doc.get("skip_eval", False),
        "version": doc.get("version", 1),
        "created_at": dt(doc.get("created_at")),
        "updated_at": dt(doc.get("updated_at")),
    }


def _get_feedback(interview_id: int):
    return col("interview_feedback").find_one({"interview_id": interview_id})


def _expected_round_for_stage(app_doc: dict, job_doc: dict):
    """按应聘记录当前阶段计算允许安排的唯一面试轮次。"""
    current_stage = app_doc.get("current_stage", "")
    if current_stage in INTERVIEW_STAGE_ROUNDS:
        return INTERVIEW_STAGE_ROUNDS[current_stage]
    if current_stage not in {"pending_interview", "interviewing"}:
        return None
    configured_rounds = configured_interview_rounds(job_doc)
    if configured_rounds:
        return expected_interview_round(app_doc, job_doc)
    # 历史职位未配置面试轮次时，首个面试阶段默认只能安排一面。
    current_round = app_doc.get("interview_round", "")
    return current_round if current_round in INTERVIEW_ROUNDS else "一面"


@bp.get("")
@login_required
def list_interviews():
    args = request.args
    query = {}
    if args.get("status"):
        query["status"] = args["status"]
    if args.get("job_id"):
        query["job_id"] = int(args["job_id"])
    if args.get("candidate_id"):
        query["candidate_id"] = int(args["candidate_id"])
    if args.get("application_id"):
        query["application_id"] = int(args["application_id"])
    if args.get("round"):
        query["round"] = args["round"]
    if args.get("interviewer"):
        query["interviewer_name"] = {"$regex": args["interviewer"]}
    if args.get("date_from"):
        query.setdefault("start_at", {})["$gte"] = _parse_time(args["date_from"] + " 00:00", "date_from")
    if args.get("date_to"):
        query.setdefault("start_at", {})["$lte"] = _parse_time(args["date_to"] + " 23:59", "date_to")
    items = col("interviews").find(query).sort("start_at", -1)
    page = max(int(args.get("page", 1)), 1)
    page_size = min(max(int(args.get("page_size", 10)), 1), 100)
    rows = list(items)
    total = len(rows)
    sliced = rows[(page - 1) * page_size: page * page_size]
    data = [_interview_view(d) for d in sliced]
    for row, doc in zip(data, sliced):
        fb = _get_feedback(doc["_id"])
        row["has_feedback"] = fb is not None
        row["feedback_conclusion"] = fb.get("conclusion", "") if fb else ""
        row["feedback_skip_eval"] = bool(fb.get("skip_eval")) if fb else False
    from common.response import paged

    return paged(data, total, page, page_size)


@bp.get("/<int:interview_id>")
@login_required
def get_interview(interview_id: int):
    doc = _get_or_404(interview_id)
    data = _interview_view(doc)
    fb = _get_feedback(interview_id)
    data["feedback"] = _feedback_view(fb) if fb else None
    return ok(data)


@bp.post("")
@role_required(HR)
def create_interview():
    payload = request.get_json(silent=True) or {}
    candidate, job, app_doc = _resolve_bindings(payload)

    round_ = (payload.get("round") or "").strip()
    if round_ not in INTERVIEW_ROUNDS:
        raise BizError(BizCode.PARAM_INVALID, f"面试轮次必须是: {'/'.join(INTERVIEW_ROUNDS)}")
    expected_round = _expected_round_for_stage(app_doc, job)
    if expected_round is None:
        raise BizError(BizCode.STATE_INVALID, "当前招聘阶段不是面试阶段，不能安排面试")
    if round_ != expected_round:
        raise BizError(BizCode.STATE_INVALID, f"当前阶段只能安排{expected_round}，不能安排{round_}")
    iv_type = (payload.get("type") or "").strip()
    if iv_type not in INTERVIEW_TYPES:
        raise BizError(BizCode.PARAM_INVALID, "面试类型必须是 onsite/video/phone")
    start_at = _parse_time(payload.get("start_at"), "开始时间")
    end_at = _parse_time(payload["end_at"], "结束时间") \
        if payload.get("end_at") else start_at + timedelta(hours=1)
    _validate_time_window(start_at, end_at)
    template_id = payload.get("template_id")
    if template_id:
        if get_by_id("eval_templates", int(template_id)) is None:
            raise BizError(BizCode.NOT_FOUND, "评价模板不存在")
        template_id = int(template_id)

    with candidate_schedule_guard(candidate["_id"]):
        existing = col("interviews").find_one({
            "application_id": app_doc["_id"], "round": round_,
            "status": {"$ne": IV_CANCELLED},
        })
        if existing:
            raise BizError(BizCode.DUPLICATED, "当前阶段已有对应面试，请使用编辑修改面试安排")
        _check_conflict(candidate["_id"], start_at, end_at)
        doc = insert_doc("interviews", {
            "candidate_id": candidate["_id"],
            "job_id": job["_id"],
            "application_id": app_doc["_id"],
            "round": round_,
            "type": iv_type,
            "start_at": start_at,
            "end_at": end_at,
            "location": (payload.get("location") or "").strip(),
            "meeting_link": (payload.get("meeting_link") or "").strip(),
            "interviewer_name": (payload.get("interviewer_name") or "").strip(),
            "interviewer_contact": (payload.get("interviewer_contact") or "").strip(),
            "template_id": template_id,
            "summary": (payload.get("summary") or "").strip(),
            "remark": (payload.get("remark") or "").strip(),
            "status": IV_PENDING,
            "version": 1,
            "reschedule_history": [],
            "created_by": g.current_user.user_id,
        })
    write_log("interview", "create", g.current_user.user_id, g.current_user.name,
              biz_id=str(doc["_id"]),
              detail=f"候选人{candidate['_id']} 职位{job['_id']} {round_} {iv_type}")
    _notify_interview(doc, candidate.get("name", ""))
    return ok(_interview_view(doc))


@bp.put("/<int:interview_id>")
@role_required(HR)
def update_interview(interview_id: int):
    doc = _get_or_404(interview_id)
    if doc["status"] in (IV_COMPLETED, IV_CANCELLED):
        raise BizError(BizCode.STATE_INVALID, "已完成/已取消的面试不能编辑")
    payload = request.get_json(silent=True) or {}
    app_doc = require_interview_application(get_by_id("applications", doc.get("application_id")))
    job_doc = get_by_id("jobs", doc.get("job_id")) or {}
    expected_round = _expected_round_for_stage(app_doc, job_doc)
    if expected_round is None:
        raise BizError(BizCode.STATE_INVALID, "当前招聘阶段不是面试阶段，不能编辑面试")
    requested_round = payload.get("round", doc.get("round", ""))
    if requested_round != expected_round:
        raise BizError(BizCode.STATE_INVALID, f"当前阶段只能保留{expected_round}面试")
    fields = {}
    for field in ["location", "meeting_link", "interviewer_name",
                  "interviewer_contact", "summary", "remark"]:
        if field in payload:
            fields[field] = (payload[field] or "").strip()
    if "round" in payload:
        if payload["round"] not in INTERVIEW_ROUNDS:
            raise BizError(BizCode.PARAM_INVALID, "面试轮次不合法")
        fields["round"] = payload["round"]
    if "type" in payload:
        if payload["type"] not in INTERVIEW_TYPES:
            raise BizError(BizCode.PARAM_INVALID, "面试类型不合法")
        fields["type"] = payload["type"]
    if "template_id" in payload:
        tid = payload["template_id"]
        if tid and get_by_id("eval_templates", int(tid)) is None:
            raise BizError(BizCode.NOT_FOUND, "评价模板不存在")
        fields["template_id"] = int(tid) if tid else None
    start_at, end_at = doc["start_at"], doc["end_at"]
    if "start_at" in payload:
        start_at = _parse_time(payload["start_at"], "开始时间")
        fields["start_at"] = start_at
    if "end_at" in payload:
        end_at = _parse_time(payload["end_at"], "结束时间")
        fields["end_at"] = end_at
    if "start_at" in payload or "end_at" in payload:
        _validate_time_window(start_at, end_at)
    try:
        expected_version = int(payload.get("version", doc.get("version", 1)))
    except (TypeError, ValueError) as exc:
        raise BizError(BizCode.PARAM_INVALID, "version 必须为数字") from exc
    fields["updated_at"] = datetime.now()
    with candidate_schedule_guard(doc["candidate_id"]):
        if "start_at" in payload or "end_at" in payload:
            _check_conflict(doc["candidate_id"], start_at, end_at, exclude_id=interview_id)
        updated = col("interviews").find_one_and_update(
            {"_id": interview_id, "version": expected_version,
             "status": {"$nin": [IV_COMPLETED, IV_CANCELLED]}},
            {"$set": fields, "$inc": {"version": 1}},
            return_document=ReturnDocument.AFTER,
        )
    if updated is None:
        raise BizError(BizCode.CONFLICT, "面试信息已被其他人修改，请刷新后重试")
    doc = updated
    write_log("interview", "update", g.current_user.user_id, g.current_user.name,
              biz_id=str(interview_id))
    return ok(_interview_view(doc))


def _change_status(doc: dict, action: str, target: str):
    if target not in INTERVIEW_FLOW.get(doc["status"], []):
        raise BizError(BizCode.STATE_INVALID,
                       f"当前状态 {doc['status']} 不允许执行 {action}")
    update_doc("interviews", doc["_id"], {"status": target})
    doc["status"] = target
    write_log("interview", action, g.current_user.user_id, g.current_user.name,
              biz_id=str(doc["_id"]), detail=f"状态变更为 {target}")


STATUS_ACTION = {"invite": IV_INVITED, "confirm": IV_CONFIRMED, "cancel": IV_CANCELLED}


@bp.post("/<int:interview_id>/status")
@role_required(HR)
def change_status(interview_id: int):
    doc = _get_or_404(interview_id)
    payload = request.get_json(silent=True) or {}
    action = payload.get("action", "")
    target = STATUS_ACTION.get(action)
    if target is None:
        raise BizError(BizCode.PARAM_INVALID, f"未知操作: {action}")
    try:
        version = int(payload.get("version", doc.get("version", 1)))
    except (TypeError, ValueError) as exc:
        raise BizError(BizCode.PARAM_INVALID, "version 必须为数字") from exc
    updated = _change_status(doc, action, target, version=version)
    return ok(_interview_view(updated))


@bp.post("/<int:interview_id>/reschedule")
@role_required(HR)
def reschedule(interview_id: int):
    """改期：保留原记录与修改原因，状态置为已改期。"""
    doc = _get_or_404(interview_id)
    if doc["status"] in (IV_COMPLETED, IV_CANCELLED):
        raise BizError(BizCode.STATE_INVALID, "已完成/已取消的面试不能改期")
    payload = request.get_json(silent=True) or {}
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise BizError(BizCode.PARAM_INVALID, "改期必须填写原因")
    start_at = _parse_time(payload.get("start_at"), "开始时间")
    end_at = _parse_time(payload.get("end_at"), "结束时间")
    _validate_time_window(start_at, end_at)
    try:
        expected_version = int(payload.get("version", doc.get("version", 1)))
    except (TypeError, ValueError) as exc:
        raise BizError(BizCode.PARAM_INVALID, "version 必须为数字") from exc
    with candidate_schedule_guard(doc["candidate_id"]):
        latest = _get_or_404(interview_id)
        if latest["status"] in (IV_COMPLETED, IV_CANCELLED):
            raise BizError(BizCode.STATE_INVALID, "面试已完成或已取消，不能改期")
        _check_conflict(latest["candidate_id"], start_at, end_at, exclude_id=interview_id)
        history = list(latest.get("reschedule_history", []))
        history.append({
            "from_start": dt(latest["start_at"])[:16],
            "from_end": dt(latest["end_at"])[:16],
            "to_start": start_at.strftime("%Y-%m-%d %H:%M"),
            "to_end": end_at.strftime("%Y-%m-%d %H:%M"),
            "reason": reason,
            "operator_id": g.current_user.user_id,
            "operator_name": g.current_user.name,
            "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        updated = col("interviews").find_one_and_update(
            {"_id": interview_id, "version": expected_version,
             "status": {"$nin": [IV_COMPLETED, IV_CANCELLED]}},
            {"$set": {
                "start_at": start_at, "end_at": end_at,
                "status": IV_RESCHEDULED, "reschedule_history": history,
                "updated_at": datetime.now(),
            }, "$inc": {"version": 1}},
            return_document=ReturnDocument.AFTER,
        )
    if updated is None:
        raise BizError(BizCode.CONFLICT, "面试信息已被其他人修改，请刷新后重试")
    doc = updated
    write_log("interview", "reschedule", g.current_user.user_id, g.current_user.name,
              biz_id=str(interview_id), detail=reason)
    candidate = get_by_id("candidates", doc["candidate_id"]) or {}
    _notify_interview(doc, candidate.get("name", ""))
    return ok(_interview_view(doc))


@bp.post("/<int:interview_id>/complete")
@role_required(HR)
def complete_interview(interview_id: int):
    """完成面试：必须已有反馈，或显式标记暂不评价。"""
    doc = _get_or_404(interview_id)
    payload = request.get_json(silent=True) or {}
    if IV_COMPLETED not in INTERVIEW_FLOW.get(doc["status"], []):
        raise BizError(BizCode.STATE_INVALID,
                       f"当前状态 {doc['status']} 不允许完成（需先确认）")
    feedback = _get_feedback(interview_id)
    if feedback is None:
        if not payload.get("skip_eval"):
            raise BizError(BizCode.PARAM_INVALID, "请先填写面试反馈，或选择\"暂不评价\"")
        try:
            fb_doc = insert_doc("interview_feedback", {
                "interview_id": interview_id,
                "dimension_scores": [], "conclusion": "", "comment": "",
                "risk_note": "", "suggested_salary": "",
                "evaluator_name": "", "skip_eval": True,
                "created_by": g.current_user.user_id,
                "version": 1,
            })
        except DuplicateKeyError:
            fb_doc = _get_feedback(interview_id)
        write_log("interview", "feedback_skip", g.current_user.user_id, g.current_user.name,
                  biz_id=str(interview_id), detail="暂不评价")
        feedback = fb_doc
    _change_status(doc, "complete", IV_COMPLETED)
    return ok(_interview_view(doc))


@bp.post("/<int:interview_id>/feedback")
@role_required(HR)
def save_feedback(interview_id: int):
    """填写/更新面试反馈（HR 可代录）。"""
    doc = _get_or_404(interview_id)
    require_interview_application(get_by_id("applications", doc.get("application_id")))
    if doc["status"] == IV_CANCELLED:
        raise BizError(BizCode.STATE_INVALID, "已取消的面试不能填写反馈")
    payload = request.get_json(silent=True) or {}
    conclusion = (payload.get("conclusion") or "").strip()
    if conclusion not in CONCLUSIONS:
        raise BizError(BizCode.PARAM_INVALID, "综合结论必须是 pass/hold/fail")
    scores = []
    for item in payload.get("dimension_scores") or []:
        name = (item.get("name") or "").strip()
        try:
            score = int(item.get("score"))
        except (TypeError, ValueError):
            raise BizError(BizCode.PARAM_INVALID, f"维度 {name} 分数必须是整数")
        if not name or not 1 <= score <= 5:
            raise BizError(BizCode.PARAM_INVALID, "评分维度需为名称 + 1~5 分")
        scores.append({"name": name, "score": score})

    fb_fields = {
        "interview_id": interview_id,
        "dimension_scores": scores,
        "conclusion": conclusion,
        "comment": (payload.get("comment") or "").strip(),
        "risk_note": (payload.get("risk_note") or "").strip(),
        "suggested_salary": (payload.get("suggested_salary") or "").strip(),
        "evaluator_name": (payload.get("evaluator_name") or "").strip(),
        "skip_eval": False,
    }
    existing = _get_feedback(interview_id)
    if existing:
        try:
            expected_version = int(payload.get("version", existing.get("version", 1)))
        except (TypeError, ValueError) as exc:
            raise BizError(BizCode.PARAM_INVALID, "version 必须为数字") from exc
        updated = col("interview_feedback").find_one_and_update(
            {"_id": existing["_id"], "version": expected_version},
            {"$set": {**fb_fields, "updated_at": datetime.now()}, "$inc": {"version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            raise BizError(BizCode.CONFLICT, "面试反馈已被其他人修改，请刷新后重试")
    else:
        fb_fields["version"] = 1
        try:
            updated = insert_doc("interview_feedback", fb_fields)
        except DuplicateKeyError as exc:
            raise BizError(BizCode.CONFLICT, "面试反馈已被其他人提交，请刷新后重试") from exc
    write_log("interview", "feedback", g.current_user.user_id, g.current_user.name,
              biz_id=str(interview_id), detail=f"结论={conclusion}")
    return ok(_feedback_view(updated))


@bp.post("/<int:interview_id>/apply-conclusion")
@role_required(HR)
def apply_conclusion(interview_id: int):
    """反馈联动阶段：通过→面试通过；不通过→淘汰（必填原因）；待定不流转。"""
    doc = _get_or_404(interview_id)
    if doc.get("conclusion_applied"):
        raise BizError(BizCode.STATE_INVALID, "该面试结论已经应用，不能重复推进")
    if doc["status"] != IV_COMPLETED:
        raise BizError(BizCode.STATE_INVALID, "仅已完成的面试可应用结论")
    feedback = _get_feedback(interview_id)
    if feedback is None or feedback.get("skip_eval"):
        raise BizError(BizCode.STATE_INVALID, "该面试无有效反馈，不能应用结论")
    conclusion = feedback.get("conclusion")
    if conclusion == "hold":
        raise BizError(BizCode.STATE_INVALID, "结论为待定，不触发阶段变化")

    payload = request.get_json(silent=True) or {}
    app_doc = get_by_id("applications", doc["application_id"])
    if app_doc is None:
        raise BizError(BizCode.NOT_FOUND, "关联应聘记录不存在")
    if app_doc.get("status") != APP_IN_PROGRESS:
        raise BizError(BizCode.STATE_INVALID, "应聘记录已结束，不能流转阶段")

    if conclusion == "pass":
        try:
            version = int(payload.get("version", -1))
        except (TypeError, ValueError):
            raise BizError(BizCode.PARAM_INVALID, "version 必填")
        job_doc = get_by_id("jobs", app_doc["job_id"]) or {}
        configured_rounds = configured_interview_rounds(job_doc)
        if configured_rounds:
            expected_round = expected_interview_round(app_doc, job_doc)
            if doc.get("round") != expected_round:
                raise BizError(BizCode.STATE_INVALID, f"当前应应用{expected_round}的面试结论")
            round_index = configured_rounds.index(expected_round)
            if round_index < len(configured_rounds) - 1:
                updated = advance_interview_round(
                    app_doc, configured_rounds[round_index + 1],
                    (payload.get("reason") or "").strip() or f"面试{doc['round']}通过",
                    g.current_user.user_id, g.current_user.name, version,
                )
            else:
                updated = move_application(
                    app_doc, to_stage="interview_passed",
                    reason=(payload.get("reason") or "").strip() or f"面试{doc['round']}通过",
                    operator_id=g.current_user.user_id, operator_name=g.current_user.name,
                    version=version,
                )
        else:
            updated = move_application(
                app_doc, to_stage="interview_passed",
                reason=(payload.get("reason") or "").strip() or f"面试{doc['round']}通过",
                operator_id=g.current_user.user_id, operator_name=g.current_user.name,
                version=version,
            )
        write_log("interview", "apply_conclusion_pass", g.current_user.user_id,
                  g.current_user.name, biz_id=str(interview_id))
        col("interviews").update_one({"_id": interview_id}, {"$set": {
            "conclusion_applied": True, "conclusion_action": "pass",
            "conclusion_applied_at": datetime.now(),
            "conclusion_applied_by": g.current_user.user_id,
        }})
        return ok({"action": "pass", "application": application_to_dict(updated)})

    # fail：淘汰必填原因
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise BizError(BizCode.PARAM_INVALID, "面试不通过淘汰候选人必须填写原因")
    # 面试不通过不是普通的“淘汰”分支：候选人仍需保留在人才库，
    # 以便后续岗位重新激活。因此阶段和人才库记录必须同时更新。
    updated = move_application(
        app_doc, to_stage="talent_pool", reason=reason,
        operator_id=g.current_user.user_id, operator_name=g.current_user.name,
        version=app_doc.get("version", 1), bypass_rules=True,
    )
    add_application_to_talent_pool(
        updated, reason, source="elimination_added",
        operator_id=g.current_user.user_id, operator_name=g.current_user.name,
    )
    write_log("interview", "apply_conclusion_fail", g.current_user.user_id,
              g.current_user.name, biz_id=str(interview_id), detail=reason)
    col("interviews").update_one({"_id": interview_id}, {"$set": {
        "conclusion_applied": True, "conclusion_action": "fail",
        "conclusion_applied_at": datetime.now(),
        "conclusion_applied_by": g.current_user.user_id,
    }})
    return ok({"action": "fail", "application": application_to_dict(updated)})


# Use an optimistic lock for interview state changes.  This prevents two HR
# users from confirming/completing/cancelling the same interview concurrently.
def _change_status(doc: dict, action: str, target: str, version: int = None):
    if target not in INTERVIEW_FLOW.get(doc["status"], []):
        raise BizError(BizCode.STATE_INVALID,
                       f"当前状态 {doc['status']} 不允许执行 {action}")
    app = get_by_id("applications", doc.get("application_id"))
    if app is None:
        raise BizError(BizCode.STATE_INVALID, "面试关联的应聘记录不存在")
    require_interview_application(app)
    expected_version = doc.get("version", 1) if version is None else version
    updated = col("interviews").find_one_and_update(
        {"_id": doc["_id"], "status": doc["status"],
         "$or": [{"version": expected_version}, {"version": {"$exists": False}}]},
        {"$set": {"status": target, "updated_at": datetime.now()},
         "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise BizError(BizCode.CONFLICT, "面试状态已被其他人更新，请刷新后重试")
    doc.update(updated)
    write_log("interview", action, g.current_user.user_id, g.current_user.name,
              biz_id=str(doc["_id"]), detail=f"状态变更为 {target}")
    return updated
