"""招聘流程看板（MongoDB 版）：应聘记录粒度卡片、阶段流转、锁定期展示。"""
from datetime import datetime

from flask import Blueprint, current_app, g, request

from common.db import col, get_by_id, dt
from common.access import require_candidate_lock_owner
from common.decorators import login_required, role_required
from common.errors import BizError
from common.flow import (
    application_to_dict,
    configured_interview_rounds,
    eliminate_application,
    effective_interview_round,
    job_stage_sequence,
    lock_info_for_candidate,
    move_application,
    release_expired_locks,
    restore_abandoned_application,
)
from common.logstore import write_log
from common.response import BizCode, ok
from common.roles import BUSINESS_SCREENER, HR, SUPER_ADMIN
from common.status import APP_ELIMINATED, APP_IN_PROGRESS, APP_ONBOARDED, APP_PENDING_ONBOARD
from common.stage_rules import add_application_to_talent_pool
from platform_identity import get_identity

bp = Blueprint("pipeline_api", __name__)

from common.stages import STAGE_NAMES

HR_FLOW_ENTRY_STAGES = {
    "new_resume", "pending_screen", "hr_screen_passed", "business_screen", "hrbp_interview",
}


def _stage_display(stage_key: str, sequence) -> str:
    for s in sequence:
        if s.stage_key == stage_key:
            return s.name
    # 兼容映射：终态与 v1.0 旧阶段仍可正确显示名称
    return STAGE_NAMES.get(stage_key, stage_key)


def _workflow_stage(job: dict, kind: str, after_stage: str = ""):
    sequence = job_stage_sequence(job)
    if kind == "business":
        for stage in sequence:
            if stage.stage_key == "business_screen" or stage.name in {"业务复筛", "业务筛选"}:
                return stage
        raise BizError(BizCode.STATE_INVALID, "当前招聘流程模板未配置业务复筛阶段")
    explicit_interview_keys = {"interview_1", "interview_2", "interview_3", "hr_interview", "re_interview"}
    if after_stage:
        current_index = next(
            (index for index, item in enumerate(sequence) if item.stage_key == after_stage),
            -1,
        )
        for item in sequence[current_index + 1:]:
            if item.stage_key in explicit_interview_keys or item.stage_key in {"pending_interview", "interviewing"}:
                return item
    for stage in sequence:
        if stage.stage_key in explicit_interview_keys:
            return stage
    interview_keys = {"pending_interview", "interviewing"}
    for stage in sequence:
        if stage.stage_key in interview_keys:
            return stage
    raise BizError(BizCode.STATE_INVALID, "当前招聘流程模板未配置面试阶段")


def _business_screener(user_id: str):
    identity = get_identity(current_app)
    user = identity.get_user((user_id or "").strip())
    if user is None or user.role != BUSINESS_SCREENER:
        raise BizError(BizCode.PARAM_INVALID, "请选择有效的业务复筛人员")
    return user


def _ensure_hr_can_arrange(app: dict):
    if app.get("current_stage") not in HR_FLOW_ENTRY_STAGES:
        raise BizError(BizCode.STATE_INVALID, "当前阶段不能由 HR 重新安排流程")


@bp.get("/api/pipeline/board")
@login_required
def board():
    job_id = request.args.get("job_id", type=int)
    requirement_id = request.args.get("requirement_id", type=int)
    jobs = []
    if job_id:
        job = get_by_id("jobs", job_id)
        if job is None:
            raise BizError(BizCode.NOT_FOUND, "职位不存在")
        jobs = [job]
    elif requirement_id:
        if get_by_id("requirements", requirement_id) is None:
            raise BizError(BizCode.NOT_FOUND, "招聘需求不存在")
        jobs = list(col("jobs").find({"requirement_id": requirement_id}).sort("_id", 1))
    else:
        raise BizError(BizCode.PARAM_INVALID, "job_id 或 requirement_id 必填")

    release_expired_locks()
    columns = []
    for job in jobs:
        sequence = job_stage_sequence(job)
        for s in sequence:
            columns.append({"stage_key": s.stage_key, "name": s.name,
                            "category": s.category, "job_id": job["_id"],
                            "job_name": job.get("name", "")})
        if len(jobs) > 1:
            continue
        for key, name in (("eliminated", "淘汰"), ("abandoned", "放弃"), ("talent_pool", "人才库")):
            columns.append({"stage_key": key, "name": name, "category": "终态",
                            "job_id": job["_id"], "job_name": job.get("name", "")})

    job_ids = [j["_id"] for j in jobs]
    apps = list(col("applications").find({"job_id": {"$in": job_ids}}))
    now = datetime.now()
    cards = []
    for app in apps:
        # 看板展示：进行中 + 已淘汰（淘汰列）；待入职/已入职等属于后续阶段视图
        if app.get("status") not in (APP_IN_PROGRESS, APP_PENDING_ONBOARD,
                                      APP_ONBOARDED, APP_ELIMINATED):
            continue
        stay = ""
        if app.get("stage_entered_at"):
            days = (now - app["stage_entered_at"]).days
            stay = f"{days}天" if days > 0 else "当天"
        card = application_to_dict(app)
        sequence = job_stage_sequence(get_by_id("jobs", app["job_id"]) or {})
        card.update({
            "stage_name": _stage_display(app.get("current_stage", ""), sequence),
            "stay": stay,
            "lock": lock_info_for_candidate(app["candidate_id"])
            if app.get("status") in (APP_IN_PROGRESS, APP_PENDING_ONBOARD) else None,
        })
        cards.append(card)
    return ok({"columns": columns, "cards": cards})


@bp.post("/api/applications/<int:app_id>/move")
@role_required(HR, SUPER_ADMIN, BUSINESS_SCREENER)
def move(app_id: int):
    app = get_by_id("applications", app_id)
    if app is None:
        raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
    require_candidate_lock_owner(app["candidate_id"])
    payload = request.get_json(silent=True) or {}
    try:
        version = int(payload.get("version", -1))
    except (TypeError, ValueError):
        raise BizError(BizCode.PARAM_INVALID, "version 必填")
    requested_stage = (payload.get("to_stage") or "").strip()
    job = get_by_id("jobs", app["job_id"]) or {}
    available_stage_keys = {stage.stage_key for stage in job_stage_sequence(job)}
    # 默认 v1.1 模板使用 offer_pending；兼容旧前端提交的 offer_approval。
    if requested_stage == "offer_approval" and requested_stage not in available_stage_keys \
            and "offer_pending" in available_stage_keys:
        requested_stage = "offer_pending"
    current_roles = set(getattr(g.current_user, "roles", []) or [])
    current_roles.add(getattr(g.current_user, "role", ""))
    business_advance = False
    direct_offer_advance = bool(
        current_roles.intersection({HR, SUPER_ADMIN})
        and requested_stage in {"offer_pending", "offer_approval"}
        and app.get("status") == APP_IN_PROGRESS
        and app.get("current_stage") not in {
            "offer_pending", "offer_approval", "offer", "pending_onboard", "onboarded",
            "eliminated", "abandoned", "talent_pool",
        }
    )
    if BUSINESS_SCREENER in current_roles:
        if app.get("current_stage") != "business_screen":
            raise BizError(BizCode.STATE_INVALID, "当前阶段不是业务复筛，不能通过业务复筛")
        if app.get("business_screener_id") != g.current_user.user_id:
            raise BizError(BizCode.FORBIDDEN, "只有被指定的业务复筛人员可以通过该候选人")
        next_interview = _workflow_stage(job, "interview", after_stage="business_screen")
        if requested_stage != next_interview.stage_key:
            raise BizError(BizCode.STATE_INVALID, "业务复筛只能进入下一面试阶段")
        business_advance = True
    elif app.get("current_stage") == "business_screen":
        next_interview = _workflow_stage(job, "interview", after_stage="business_screen")
        business_advance = requested_stage == next_interview.stage_key
    updated = move_application(
        app, to_stage=requested_stage,
        reason=payload.get("reason", ""),
        operator_id=g.current_user.user_id, operator_name=g.current_user.name,
        version=version,
        bypass_rules=business_advance or direct_offer_advance,
    )
    return ok(application_to_dict(updated))


@bp.post("/api/applications/<int:app_id>/assign-business")
@role_required(HR, SUPER_ADMIN)
def assign_business(app_id: int):
    """HR 将候选人推给指定业务复筛人员。"""
    app = get_by_id("applications", app_id)
    if app is None:
        raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
    require_candidate_lock_owner(app["candidate_id"])
    _ensure_hr_can_arrange(app)
    payload = request.get_json(silent=True) or {}
    try:
        version = int(payload.get("version", -1))
    except (TypeError, ValueError):
        raise BizError(BizCode.PARAM_INVALID, "version 必填")
    job = get_by_id("jobs", app["job_id"]) or {}
    stage = _workflow_stage(job, "business")
    screener = _business_screener(payload.get("business_screener_id", ""))
    updated = move_application(
        app, to_stage=stage.stage_key,
        reason=(payload.get("reason") or "HR推送业务复筛").strip(),
        operator_id=g.current_user.user_id, operator_name=g.current_user.name,
        version=version, bypass_rules=True,
        set_fields={
            "business_screener_id": screener.user_id,
            "business_screener_name": screener.name,
        },
    )
    write_log("application", "assign_business_screener",
              g.current_user.user_id, g.current_user.name,
              biz_id=str(app_id), detail=f"指派给{screener.name}")
    return ok(application_to_dict(updated))


@bp.post("/api/applications/<int:app_id>/direct-interview")
@role_required(HR, SUPER_ADMIN, BUSINESS_SCREENER)
def direct_interview(app_id: int):
    """HR 跳过业务复筛，直接把候选人推进到模板的首个面试阶段。"""
    app = get_by_id("applications", app_id)
    if app is None:
        raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
    require_candidate_lock_owner(app["candidate_id"])
    current_roles = set(getattr(g.current_user, "roles", []) or [])
    current_roles.add(getattr(g.current_user, "role", ""))
    if BUSINESS_SCREENER in current_roles:
        if app.get("current_stage") != "business_screen":
            raise BizError(BizCode.STATE_INVALID, "当前阶段不是业务复筛，不能通过业务复筛")
        if app.get("business_screener_id") != g.current_user.user_id:
            raise BizError(BizCode.FORBIDDEN, "只有被指定的业务复筛人员可以通过该候选人")
    else:
        _ensure_hr_can_arrange(app)
    payload = request.get_json(silent=True) or {}
    try:
        version = int(payload.get("version", -1))
    except (TypeError, ValueError):
        raise BizError(BizCode.PARAM_INVALID, "version 必填")
    job = get_by_id("jobs", app["job_id"]) or {}
    is_business_screener = BUSINESS_SCREENER in current_roles
    stage = _workflow_stage(
        job, "interview",
        after_stage=app.get("current_stage", "") if is_business_screener else "",
    )
    updated = move_application(
        app, to_stage=stage.stage_key,
        reason=(payload.get("reason") or (
            "业务复筛通过，进入一面" if BUSINESS_SCREENER in current_roles
            else "HR安排直接面试"
        )).strip(),
        operator_id=g.current_user.user_id, operator_name=g.current_user.name,
        # 业务复筛按钮代表“通过业务复筛并进入下一面试”，允许跳过岗位模板中
        # 插入在筛选与面试之间的可选环节；前面的当前阶段和人员归属校验仍保留。
        version=version, bypass_rules=True,
    )
    write_log("application", "direct_interview",
              g.current_user.user_id, g.current_user.name,
              biz_id=str(app_id), detail=f"进入{stage.name}")
    return ok(application_to_dict(updated))


@bp.post("/api/applications/<int:app_id>/next-interview")
@role_required(HR, SUPER_ADMIN)
def next_interview(app_id: int):
    """面试通过后由 HR 明确推进到下一轮面试。"""
    app = get_by_id("applications", app_id)
    if app is None:
        raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
    require_candidate_lock_owner(app["candidate_id"])
    if app.get("status") != APP_IN_PROGRESS or app.get("current_stage") not in {
        "interview_passed", "interviewing", "interview_1", "interview_2",
    }:
        raise BizError(BizCode.STATE_INVALID, "只有上一轮面试通过后才能进入二面")
    payload = request.get_json(silent=True) or {}
    try:
        version = int(payload.get("version", -1))
    except (TypeError, ValueError):
        raise BizError(BizCode.PARAM_INVALID, "version 必须为数字")

    passed_interviews = []
    for interview in col("interviews").find({
        "application_id": app_id,
        "status": "completed",
    }):
        feedback = col("interview_feedback").find_one({
            "interview_id": interview.get("_id"),
            "conclusion": "pass",
        })
        if feedback and not feedback.get("skip_eval"):
            passed_interviews.append(interview)
    job = get_by_id("jobs", app["job_id"]) or {}
    valid_stage_keys = {stage.stage_key for stage in job_stage_sequence(job)}
    rounds = configured_interview_rounds(job)
    # v1.1 默认模板使用一个通用 interviewing 阶段承载多轮面试，
    # 兼容该模板时按系统默认顺序推进到一面、二面、三面。
    if not rounds and "interviewing" in valid_stage_keys:
        rounds = ["一面", "二面", "三面"]
    passed_rounds = {item.get("round", "") for item in passed_interviews}
    passed_interviews.sort(key=lambda item: item.get("_id", 0))
    stage_rounds = {
        "interview_1": "一面", "interview_2": "二面", "interview_3": "三面",
        "hr_interview": "HR面试", "re_interview": "复试",
    }
    current_round = effective_interview_round(app, job) or stage_rounds.get(app.get("current_stage", ""), "")
    if not current_round and passed_interviews:
        current_round = passed_interviews[-1].get("round", "")
    if not rounds or current_round not in rounds or current_round not in passed_rounds:
        raise BizError(BizCode.STATE_INVALID, "请先完成并通过上一轮面试评价")
    current_index = rounds.index(current_round)
    if current_index >= len(rounds) - 1:
        raise BizError(BizCode.STATE_INVALID, "当前面试已经是最后一轮")
    next_round = rounds[current_index + 1]
    round_stage_keys = {
        "一面": "interview_1", "二面": "interview_2", "三面": "interview_3",
        "HR面试": "hr_interview", "复试": "re_interview",
    }
    target_stage = round_stage_keys.get(next_round, "")
    if target_stage not in valid_stage_keys:
        target_stage = "interviewing" if "interviewing" in valid_stage_keys else target_stage
    if target_stage not in valid_stage_keys:
        raise BizError(BizCode.STATE_INVALID, "当前招聘流程未配置下一轮面试阶段")
    if target_stage not in valid_stage_keys:
        raise BizError(BizCode.STATE_INVALID, "当前招聘流程未配置二面阶段")

    updated = move_application(
        app,
        to_stage=target_stage,
        reason=(payload.get("reason") or f"HR安排进入{next_round}").strip(),
        operator_id=g.current_user.user_id,
        operator_name=g.current_user.name,
        version=version,
        bypass_rules=True,
        set_fields={"interview_round": next_round},
    )
    write_log("application", "enter_second_interview",
              g.current_user.user_id, g.current_user.name,
              biz_id=str(app_id), detail=f"进入{next_round}")
    return ok(application_to_dict(updated))


@bp.post("/api/applications/<int:app_id>/eliminate")
@role_required(HR)
def eliminate(app_id: int):
    app = get_by_id("applications", app_id)
    if app is None:
        raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
    require_candidate_lock_owner(app["candidate_id"])
    payload = request.get_json(silent=True) or {}
    try:
        version = int(payload.get("version", app.get("version", 1)))
    except (TypeError, ValueError):
        raise BizError(BizCode.PARAM_INVALID, "version 必须为数字")
    updated = eliminate_application(
        app, reason=payload.get("reason", ""),
        operator_id=g.current_user.user_id, operator_name=g.current_user.name,
        version=version,
    )
    return ok(application_to_dict(updated))


@bp.post("/api/applications/<int:app_id>/abandon")
@role_required(HR, SUPER_ADMIN)
def abandon(app_id: int):
    """HR 可在任意未结束阶段放弃候选人，并可同步保留到人才库。"""
    app = get_by_id("applications", app_id)
    if app is None:
        raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
    require_candidate_lock_owner(app["candidate_id"])
    payload = request.get_json(silent=True) or {}
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise BizError(BizCode.PARAM_INVALID, "放弃必须选择原因")
    try:
        version = int(payload.get("version", app.get("version", 1)))
    except (TypeError, ValueError):
        raise BizError(BizCode.PARAM_INVALID, "version 必须为数字")

    updated = move_application(
        app, to_stage="abandoned", reason=reason,
        operator_id=g.current_user.user_id, operator_name=g.current_user.name,
        version=version, bypass_rules=True,
    )
    if bool(payload.get("to_pool")):
        add_application_to_talent_pool(
            updated, reason, source="abandoned_added",
            operator_id=g.current_user.user_id, operator_name=g.current_user.name,
            category="放弃", tags=[reason],
        )
    return ok(application_to_dict(updated))


@bp.post("/api/applications/<int:app_id>/restore")
@role_required(HR, SUPER_ADMIN)
def restore(app_id: int):
    """Any HR may restart an interrupted application and take ownership."""
    app = get_by_id("applications", app_id)
    if app is None:
        raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
    payload = request.get_json(silent=True) or {}
    try:
        version = int(payload.get("version", app.get("version", 1)))
    except (TypeError, ValueError):
        raise BizError(BizCode.PARAM_INVALID, "version 必须为数字")
    updated = restore_abandoned_application(
        app,
        operator_id=g.current_user.user_id,
        operator_name=g.current_user.name,
        version=version,
        reason=(payload.get("reason") or "HR恢复流程").strip(),
    )
    return ok(application_to_dict(updated))
