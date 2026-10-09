"""工作台与我的任务数据接口。"""
from datetime import datetime

from flask import Blueprint, g

from common.db import col, dt
from common.decorators import login_required
from common.flow import application_process_state, interview_process_state
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
    pending_screen_query = {
        "current_stage": {"$in": ["new_resume", "pending_screen"]},
        "status": "in_progress",
    }
    unprocessed_candidate_ids = set(col("applications").distinct(
        "candidate_id", pending_screen_query,
    ))
    referral_candidate_ids = set(col("candidates").distinct("_id", {"source": "referral"}))
    referral_candidate_ids.update(col("applications").distinct(
        "candidate_id", {"source": "referral"},
    ))
    recommendation_sources = ["headhunt", "talent_pool", "business_recommendation"]
    recommended_candidate_ids = set(col("candidates").distinct(
        "_id", {"source": {"$in": recommendation_sources}},
    ))
    recommended_candidate_ids.update(col("applications").distinct(
        "candidate_id", {"source": {"$in": recommendation_sources}},
    ))
    application_candidate_ids = col("applications").distinct("candidate_id")
    unassigned_query = {"_id": {"$nin": application_candidate_ids}} if application_candidate_ids else {}
    active_interview_statuses = ["pending", "invited", "confirmed", "rescheduled"]
    active_interview_app_ids = set(col("interviews").distinct(
        "application_id", {"status": {"$in": active_interview_statuses}},
    ))
    feedback_pending_interview_ids = {
        item["_id"] for item in col("interviews").find({
            "status": {"$in": active_interview_statuses + ["completed"]},
        })
        if interview_process_state(item).get("key") == "awaiting_interviewer_feedback"
    }
    interview_stage_keys = [
        "pending_interview", "interviewing", "interview_1", "interview_2",
        "interview_3", "hr_interview", "re_interview",
    ]
    candidate_ids = set(col("candidates").distinct("_id"))
    waiting_schedule_ids = {
        item["_id"] for item in col("applications").find({
            "current_stage": {"$in": interview_stage_keys},
            "status": "in_progress",
        })
        if item.get("candidate_id") in candidate_ids
        and application_process_state(item).get("key") == "awaiting_interview_schedule"
    }
    recommendation_passed_ids = set(col("stage_transitions").distinct("application_id", {
        "from_stage": "business_screen",
        "to_stage": {"$in": interview_stage_keys + ["interview_passed", "hrbp_interview"]},
    }))
    recommendation_failed_ids = set(col("stage_transitions").distinct("application_id", {
        "from_stage": "business_screen",
        "to_stage": {"$in": ["eliminated", "abandoned", "talent_pool"]},
    }))
    recommendation_passed_candidate_ids = set(col("applications").distinct(
        "candidate_id", {"_id": {"$in": list(recommendation_passed_ids)}},
    ))
    recommendation_failed_candidate_ids = set(col("applications").distinct(
        "candidate_id", {"_id": {"$in": list(recommendation_failed_ids)}},
    ))
    waiting_schedule_candidate_ids = set(col("applications").distinct(
        "candidate_id", {"_id": {"$in": list(waiting_schedule_ids)}},
    ))
    recommendation_pending_candidate_ids = set(col("applications").distinct(
        "candidate_id", {"current_stage": "business_screen", "status": "in_progress"},
    ))
    pending_approval_offer_ids = set(col("offer_approvals").distinct(
        "offer_id", {"status": "pending"},
    ))
    approved_offer_ids = set(col("offer_approvals").distinct(
        "offer_id", {"status": "approved"},
    ))
    pending_send_query = {
        "status": "pending_send",
        "_id": {"$in": list(approved_offer_ids)},
    }

    todos = {
        "pending_screen": _count("applications", {
            "current_stage": {"$in": ["new_resume", "pending_screen"]}, "status": "in_progress",
        }),
        "interviews_pending": _count("interviews", {
            "status": {"$in": active_interview_statuses},
        }),
        "feedback_pending": len(feedback_pending_interview_ids),
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
        {"key": "feedback_pending", "title": "待面试评价", "count": todos["feedback_pending"], "route": "/interviews?action_state=awaiting_interviewer_feedback"},
        {"key": "pending_offers", "title": "待处理 Offer", "count": todos["pending_offers"], "route": "/offers"},
        {"key": "onboarding", "title": "待入职候选人", "count": todos["onboarding"], "route": "/candidates?stage=pending_onboard"},
    ]
    workbench_metrics = [
        {
            "key": "screening", "title": "简历初筛", "items": [
                {"key": "unprocessed", "label": "未处理", "count": len(unprocessed_candidate_ids), "route": "/candidates?unprocessed=1"},
                {"key": "referral", "label": "内推简历", "count": len(referral_candidate_ids), "route": "/candidates?source=referral"},
                {"key": "recommended", "label": "人才推荐", "count": len(recommended_candidate_ids), "route": "/candidates?source_group=talent_recommendation"},
                {"key": "unassigned", "label": "待分配", "count": _count("candidates", unassigned_query), "route": "/candidates?unassigned=1"},
            ],
        },
        {
            "key": "recommendation", "title": "简历推荐", "items": [
                {"key": "pending_feedback", "label": "推荐待反馈", "count": len(recommendation_pending_candidate_ids), "route": "/candidates?recommendation_status=pending"},
                {"key": "passed", "label": "推荐通过", "count": len(recommendation_passed_candidate_ids), "route": "/candidates?recommendation_status=passed"},
                {"key": "failed", "label": "推荐不通过", "count": len(recommendation_failed_candidate_ids), "route": "/candidates?recommendation_status=failed"},
            ],
        },
        {
            "key": "interview", "title": "面试", "items": [
                {"key": "waiting_schedule", "label": "待约面", "count": len(waiting_schedule_candidate_ids), "route": "/candidates?action_state=awaiting_interview_schedule"},
                {"key": "feedback", "label": "面试待评价", "count": todos["feedback_pending"], "route": "/interviews?action_state=awaiting_interviewer_feedback"},
            ],
        },
        {
            "key": "hiring", "title": "录用", "items": [
                {"key": "pending_onboard", "label": "待入职", "count": todos["onboarding"], "route": "/onboarding?application_stage=pending_onboard"},
                {"key": "pending_approval", "label": "待审批offer", "count": len(pending_approval_offer_ids), "route": "/approvals?status=pending"},
                {"key": "pending_send", "label": "待发offer", "count": _count("offers", pending_send_query), "route": "/offers?status=pending_send&ready_to_send=1"},
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
