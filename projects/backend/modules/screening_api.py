"""Explainable intelligent resume screening APIs."""
from datetime import datetime

from flask import Blueprint, current_app, g, request

from common.access import CANDIDATE_READ_ROLES
from common.db import col, dt, get_by_id, insert_doc, update_doc
from common.decorators import role_required
from common.errors import BizError
from common.file_service import get_storage, resolve_local
from common.logstore import write_log
from common.response import BizCode, ok
from common.resume_parser import parse_resume_file_with_text
from common.roles import HR, SUPER_ADMIN
from common.screening import (
    MATCH_SCOPE_NAMES,
    PROFILE_NAMES,
    detect_match_scope,
    match_scope_base_profile,
    normalize_screening_rules,
    screen_candidate,
)
from common.screening_config import list_match_items, match_item_view


bp = Blueprint("screening_api", __name__)

def _result_view(result: dict | None):
    if not result:
        return None
    return {
        "id": result["_id"],
        "application_id": result.get("application_id"),
        "candidate_id": result.get("candidate_id"),
        "job_id": result.get("job_id"),
        "job_name": result.get("job_name", ""),
        "match_mode": result.get("match_mode", "application"),
        "profile": result.get("profile", ""),
        "profile_name": result.get("profile_name", ""),
        "match_template": result.get("match_template", result.get("profile", "")),
        "match_template_name": result.get("match_template_name", result.get("profile_name", "")),
        "score": result.get("score", 0),
        "decision": result.get("decision", ""),
        "decision_label": result.get("decision_label", ""),
        "assessed_weight": result.get("assessed_weight", 0),
        "dimensions": result.get("dimensions", []),
        "matched_items": result.get("matched_items", []),
        "missing_items": result.get("missing_items", []),
        "risk_items": result.get("risk_items", []),
        "summary": result.get("summary", ""),
        "rules": result.get("rules", {}),
        "review_status": result.get("review_status", "pending"),
        "review_decision": result.get("review_decision", ""),
        "review_note": result.get("review_note", ""),
        "reviewer_id": result.get("reviewer_id", ""),
        "reviewer_name": result.get("reviewer_name", ""),
        "reviewed_at": dt(result.get("reviewed_at")),
        "route_action": result.get("route_action", ""),
        "route_label": result.get("route_label", ""),
        "routed_at": dt(result.get("routed_at")),
        "created_at": dt(result.get("created_at")),
    }


def _get_application(app_id: int):
    application = get_by_id("applications", app_id)
    if application is None:
        raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
    candidate = get_by_id("candidates", application.get("candidate_id"))
    job = get_by_id("jobs", application.get("job_id"))
    if candidate is None or job is None:
        raise BizError(BizCode.NOT_FOUND, "候选人或职位不存在")
    return application, candidate, job


def _resume_text(candidate_id: int) -> str:
    attachment = col("attachments").find_one(
        {"candidate_id": candidate_id, "file_type": "resume"}, sort=[("_id", -1)],
    )
    if not attachment:
        return ""
    if attachment.get("parsed_text"):
        return attachment["parsed_text"]
    local_path = None
    is_tmp = False
    try:
        local_path, is_tmp = resolve_local(current_app, attachment.get("file_path", ""))
        fields, status, source_text = parse_resume_file_with_text(
            local_path, attachment.get("file_name", ""),
        )
        update_doc("attachments", attachment["_id"], {
            "parse_status": status, "parsed_fields": fields, "parsed_text": source_text,
        })
        return source_text
    except Exception:
        current_app.logger.exception("筛选前读取简历失败 attachment_id=%s", attachment.get("_id"))
        return ""
    finally:
        if is_tmp and local_path:
            try:
                get_storage(current_app).cleanup_local(local_path, attachment.get("file_path", ""))
            except Exception:
                current_app.logger.exception("清理筛选简历临时文件失败 attachment_id=%s", attachment.get("_id"))


def _screen_for_job(
    candidate: dict,
    job: dict,
    application_id: int | None = None,
    match_scope_override: str = "",
):
    """生成指定候选人与职位的匹配结果；预览模式不触碰招聘流程。"""
    configured_profile = normalize_screening_rules(job.get("screening_rules"), job)["profile"]
    match_scope = (
        match_scope_override
        if match_scope_override in MATCH_SCOPE_NAMES
        else detect_match_scope(job, configured_profile)
    )
    profile = match_scope_base_profile(match_scope)
    screening_rules = {**(job.get("screening_rules") or {}), "profile": profile}
    result = screen_candidate(
        candidate, job, screening_rules, _resume_text(candidate["_id"]),
        list_match_items(match_scope, enabled_only=True),
    )
    result.update({
        "application_id": application_id,
        "candidate_id": candidate["_id"],
        "job_id": job.get("_id"),
        "job_name": job.get("name", ""),
        "match_mode": "application" if application_id else "job_preview",
        "match_template": match_scope,
        "match_template_name": MATCH_SCOPE_NAMES.get(match_scope, PROFILE_NAMES[profile]),
        "engine_version": "ai-commerce-v2-configurable",
        "review_status": "pending",
        "review_decision": "",
        "review_note": "",
        "route_action": "",
        "route_label": "",
        "created_by": g.current_user.user_id,
        "created_by_name": g.current_user.name,
    })
    return result


@bp.get("/api/screening/profiles")
@role_required(*CANDIDATE_READ_ROLES)
def profiles():
    return ok([
        {
            "key": key,
            "name": name,
            "base_profile": match_scope_base_profile(key),
            "group": "通用模板" if key in PROFILE_NAMES else "具体岗位",
            "weights": {
                item.get("name", ""): item.get("weight", 0)
                for item in list_match_items(key, enabled_only=True)
            },
            "items": [match_item_view(item) for item in list_match_items(key)],
        }
        for key, name in MATCH_SCOPE_NAMES.items()
    ])


@bp.get("/api/applications/<int:app_id>/screening-result")
@role_required(*CANDIDATE_READ_ROLES)
def get_screening_result(app_id: int):
    _get_application(app_id)
    result = col("screening_results").find_one(
        {"application_id": app_id}, sort=[("_id", -1)],
    )
    return ok(_result_view(result))


@bp.post("/api/applications/<int:app_id>/screen")
@role_required(HR, SUPER_ADMIN)
def run_screening(app_id: int):
    application, candidate, job = _get_application(app_id)
    result = _screen_for_job(candidate, job, application["_id"])
    saved = insert_doc("screening_results", result)
    update_doc("applications", application["_id"], {
        "screening_result_id": saved["_id"],
        "screening_score": saved["score"],
        "screening_decision": saved["decision"],
        "screening_review_status": "pending",
    })
    write_log(
        "application", "intelligent_screening", g.current_user.user_id, g.current_user.name,
        biz_id=str(application["_id"]), detail=f"score={saved['score']}; decision={saved['decision']}",
    )
    return ok(_result_view(saved))


@bp.post("/api/candidates/<int:candidate_id>/job-match")
@role_required(HR, SUPER_ADMIN)
def preview_job_match(candidate_id: int):
    """HR 自选职位进行简历匹配；不创建应聘记录，也不改变任何流程阶段。"""
    candidate = get_by_id("candidates", candidate_id)
    if candidate is None:
        raise BizError(BizCode.NOT_FOUND, "候选人不存在")
    payload = request.get_json(silent=True) or {}
    match_template = str(payload.get("match_template") or "").strip()
    if match_template:
        if match_template not in MATCH_SCOPE_NAMES:
            raise BizError(BizCode.PARAM_INVALID, "请选择有效岗位类型")
        job = {
            "_id": None,
            "name": MATCH_SCOPE_NAMES[match_template],
            "description": "",
            "qualification": "",
            "skill_tags": "",
            "screening_rules": {"profile": match_scope_base_profile(match_template)},
        }
        result = _screen_for_job(candidate, job, match_scope_override=match_template)
    else:
        job = get_by_id("jobs", payload.get("job_id"))
        if job is None:
            raise BizError(BizCode.PARAM_INVALID, "请选择有效职位或岗位类型")
        result = _screen_for_job(candidate, job)
    saved = insert_doc("screening_results", result)
    write_log(
        "candidate", "job_match_preview", g.current_user.user_id, g.current_user.name,
        biz_id=str(candidate_id), detail=f"匹配职位：{job.get('name', '')}; score={saved['score']}",
    )
    return ok(_result_view(saved))


@bp.post("/api/applications/<int:app_id>/screening-review")
@role_required(HR, SUPER_ADMIN)
def review_screening(app_id: int):
    application, _, _ = _get_application(app_id)
    payload = request.get_json(silent=True) or {}
    decision = payload.get("decision", "")
    if decision not in {"pass", "pending", "reject"}:
        raise BizError(BizCode.PARAM_INVALID, "人工结论必须为通过、待定或不通过")
    result = col("screening_results").find_one(
        {"application_id": app_id}, sort=[("_id", -1)],
    )
    if result is None:
        raise BizError(BizCode.STATE_INVALID, "请先执行智能匹配")
    now = datetime.now()
    fields = {
        "review_status": "reviewed",
        "review_decision": decision,
        "review_note": str(payload.get("note") or "").strip(),
        "reviewer_id": g.current_user.user_id,
        "reviewer_name": g.current_user.name,
        "reviewed_at": now,
    }
    update_doc("screening_results", result["_id"], fields)
    result.update(fields)
    update_doc("applications", application["_id"], {
        "screening_review_status": "reviewed",
        "screening_review_decision": decision,
    })
    write_log(
        "application", "screening_review", g.current_user.user_id, g.current_user.name,
        biz_id=str(application["_id"]), detail=f"decision={decision}; note={fields['review_note']}",
    )
    return ok(_result_view(result))
