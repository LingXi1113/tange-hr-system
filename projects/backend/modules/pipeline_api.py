"""招聘流程看板（MongoDB 版）：应聘记录粒度卡片、阶段流转、锁定期展示。"""
from datetime import datetime

from flask import Blueprint, g, request

from common.db import col, get_by_id, dt
from common.decorators import login_required, role_required
from common.errors import BizError
from common.flow import (
    application_to_dict,
    eliminate_application,
    job_stage_sequence,
    lock_info_for_candidate,
    move_application,
    release_expired_locks,
)
from common.response import BizCode, ok
from common.roles import HR
from common.status import APP_ELIMINATED, APP_IN_PROGRESS, APP_ONBOARDED, APP_PENDING_ONBOARD

bp = Blueprint("pipeline_api", __name__)

from common.stages import STAGE_NAMES


def _stage_display(stage_key: str, sequence) -> str:
    for s in sequence:
        if s.stage_key == stage_key:
            return s.name
    # 兼容映射：终态与 v1.0 旧阶段仍可正确显示名称
    return STAGE_NAMES.get(stage_key, stage_key)


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
@role_required(HR)
def move(app_id: int):
    app = get_by_id("applications", app_id)
    if app is None:
        raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
    payload = request.get_json(silent=True) or {}
    try:
        version = int(payload.get("version", -1))
    except (TypeError, ValueError):
        raise BizError(BizCode.PARAM_INVALID, "version 必填")
    updated = move_application(
        app, to_stage=(payload.get("to_stage") or "").strip(),
        reason=payload.get("reason", ""),
        operator_id=g.current_user.user_id, operator_name=g.current_user.name,
        version=version,
    )
    return ok(application_to_dict(updated))


@bp.post("/api/applications/<int:app_id>/eliminate")
@role_required(HR)
def eliminate(app_id: int):
    app = get_by_id("applications", app_id)
    if app is None:
        raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
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
