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
    pending_screen_query = {
        "current_stage": {"$in": ["new_resume", "pending_screen"]},
        "status": "in_progress",
    }
    application_candidate_ids = col("applications").distinct("candidate_id")
    unassigned_query = {"_id": {"$nin": application_candidate_ids}} if application_candidate_ids else {}
    active_interview_statuses = ["pending", "invited", "confirmed", "rescheduled"]
    active_interview_app_ids = set(col("interviews").distinct(
        "application_id", {"status": {"$in": active_interview_statuses}},
    ))
    interview_stage_keys = [
        "pending_interview", "interviewing", "interview_1", "interview_2",
        "interview_3", "hr_interview", "re_interview",
    ]
    waiting_schedule_ids = {
        item["_id"] for item in col("applications").find({
            "current_stage": {"$in": interview_stage_keys},
            "status": "in_progress",
        }, {"_id": 1})
    } - active_interview_app_ids
    recommendation_passed_ids = set(col("stage_transitions").distinct("application_id", {
        "from_stage": "business_screen",
        "to_stage": {"$in": interview_stage_keys + ["interview_passed", "hrbp_interview"]},
    }))
    recommendation_failed_ids = set(col("stage_transitions").distinct("application_id", {
        "from_stage": "business_screen",
        "to_stage": {"$in": ["eliminated", "abandoned", "talent_pool"]},
    }))
    pending_approval_offer_ids = set(col("offer_approvals").distinct(
        "offer_id", {"status": "pending"},
    ))
    pending_send_query = {"status": "pending_send"}
    if pending_approval_offer_ids:
        pending_send_query["_id"] = {"$nin": list(pending_approval_offer_ids)}

    todos = {
        "pending_screen": _count("applications", {
            "current_stage": {"$in": ["new_resume", "pending_screen"]}, "status": "in_progress",
        }),
        "interviews_pending": _count("interviews", {
            "status": {"$in": active_interview_statuses},
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
    workbench_metrics = [
        {
            "key": "screening", "title": "简历初筛", "items": [
                {"key": "unprocessed", "label": "未处理", "count": _count("applications", pending_screen_query), "route": "/candidates?stage=pending_screen"},
                {"key": "referral", "label": "内推简历", "count": _count("applications", {"source": "referral"}), "route": "/candidates?source=referral"},
                {"key": "recommended", "label": "人才推荐", "count": _count("applications", {"source": {"$in": ["headhunt", "talent_pool", "business_recommendation"]}}), "route": "/candidates"},
                {"key": "unassigned", "label": "待分配", "count": _count("candidates", unassigned_query), "route": "/candidates?stage=pending_screen"},
            ],
        },
        {
            "key": "recommendation", "title": "简历推荐", "items": [
                {"key": "pending_feedback", "label": "推荐待反馈", "count": _count("applications", {"current_stage": "business_screen", "status": "in_progress"}), "route": "/pipeline"},
                {"key": "passed", "label": "推荐通过", "count": len(recommendation_passed_ids), "route": "/pipeline"},
                {"key": "failed", "label": "推荐不通过", "count": len(recommendation_failed_ids), "route": "/pipeline"},
            ],
        },
        {
            "key": "interview", "title": "面试", "items": [
                {"key": "waiting_schedule", "label": "待约面", "count": len(waiting_schedule_ids), "route": "/interviews"},
                {"key": "feedback", "label": "面试待反馈", "count": todos["feedback_pending"], "route": "/interviews"},
            ],
        },
        {
            "key": "hiring", "title": "录用", "items": [
                {"key": "pending_onboard", "label": "待入职", "count": todos["onboarding"], "route": "/onboarding"},
                {"key": "pending_approval", "label": "待审批offer", "count": len(pending_approval_offer_ids), "route": "/approvals"},
                {"key": "pending_send", "label": "待发offer", "count": _count("offers", pending_send_query), "route": "/offers"},
            ],
        },
    ]
    return ok({
        "todos": todos,
        "todo_items": todo_items,
        "workbench_metrics": workbench_metrics,
        "overview": overview,
        "funnel": funnel,
        "notification_unread": unread,
        "recent_activities": activities,
        "generated_at": dt(now),
    })
