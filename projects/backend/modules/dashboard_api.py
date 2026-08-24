"""工作台与我的任务数据接口。"""
from datetime import datetime

from flask import Blueprint, g

from common.db import col, dt
from common.decorators import login_required
from common.response import ok
from common.stages import DEFAULT_STAGES, STAGE_NAMES

bp = Blueprint("dashboard_api", __name__)


def _count(collection, query):
    return col(collection).count_documents(query)


@bp.get("/api/dashboard/summary")
@login_required
def summary():
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    completed_interviews = [item["_id"] for item in col("interviews").find({"status": "completed"}, {"_id": 1})]
    feedback_ids = {item.get("interview_id") for item in col("interview_feedback").find(
        {"interview_id": {"$in": completed_interviews}}, {"interview_id": 1})}
    todos = {
        "pending_screen": _count("applications", {
            "current_stage": "pending_screen", "status": "in_progress",
        }),
        "interviews_pending": _count("interviews", {
            "status": {"$in": ["pending", "invited", "rescheduled"]},
        }),
        "feedback_pending": len(set(completed_interviews) - feedback_ids),
        "pending_offers": _count("offers", {
            "status": {"$in": ["draft", "pending_send", "sent"]},
        }),
        "onboarding": _count("applications", {
            "$or": [{"status": "pending_onboard"}, {"current_stage": "pending_onboard"}],
        }),
    }
    overview = {
        "ongoing_requirements": _count("requirements", {"status": {"$in": ["recruiting", "paused"]}}),
        "open_jobs": _count("jobs", {"status": "recruiting"}),
        "candidate_total": _count("candidates", {}),
        "month_interviews": _count("interviews", {"start_at": {"$gte": month_start}}),
        "month_offers": _count("offers", {"created_at": {"$gte": month_start}}),
        "month_onboarded": _count("applications", {
            "status": "onboarded", "updated_at": {"$gte": month_start},
        }),
    }
    funnel = []
    for stage_key, stage_name, *_ in DEFAULT_STAGES:
        funnel.append({
            "stage_key": stage_key,
            "name": stage_name,
            "count": _count("applications", {"current_stage": stage_key}),
        })
    for stage_key in ("eliminated", "talent_pool"):
        funnel.append({
            "stage_key": stage_key,
            "name": STAGE_NAMES.get(stage_key, stage_key),
            "count": _count("applications", {"current_stage": stage_key}),
        })
    activities = [{
        "id": log.get("_id"),
        "biz_type": log.get("biz_type", ""),
        "biz_id": log.get("biz_id", ""),
        "action": log.get("action", ""),
        "operator_name": log.get("operator_name", ""),
        "detail": log.get("detail", ""),
        "created_at": dt(log.get("created_at")),
    } for log in col("operation_logs").find({}).sort("created_at", -1).limit(12)]
    unread = _count("notifications", {"receiver_id": g.current_user.user_id, "read_at": None})
    todo_items = [
        {"key": "pending_screen", "title": "待筛选候选人", "count": todos["pending_screen"], "route": "/candidates?stage=pending_screen"},
        {"key": "interviews_pending", "title": "待处理面试", "count": todos["interviews_pending"], "route": "/interviews"},
        {"key": "feedback_pending", "title": "待填写面试反馈", "count": todos["feedback_pending"], "route": "/interviews"},
        {"key": "pending_offers", "title": "待处理 Offer", "count": todos["pending_offers"], "route": "/offers"},
        {"key": "onboarding", "title": "待入职候选人", "count": todos["onboarding"], "route": "/candidates?stage=pending_onboard"},
    ]
    return ok({
        "todos": todos,
        "todo_items": todo_items,
        "overview": overview,
        "funnel": funnel,
        "notification_unread": unread,
        "recent_activities": activities,
        "generated_at": dt(now),
    })
