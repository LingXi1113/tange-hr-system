"""A job change closes one delivery and creates a fresh screening delivery."""
from datetime import datetime

from flask import g
from pymongo import ReturnDocument

from common.access import require_candidate_lock_owner
from common.atomic import business_transaction
from common.consistency import require_application_active
from common.db import col, get_by_id, next_id
from common.errors import BizError
from common.flow import create_application, job_stage_sequence, notify_application_created, release_stage_lock
from common.interview_guard import candidate_schedule_guard
from common.logstore import write_log
from common.response import BizCode


def change_application_job(candidate, application_id, job, version, reason):
    """Preserve history; never transfer an interview/approval to the new job.

    The candidate lease also serializes this with interview scheduling. Replica
    sets use a transaction; standalone development databases use compensation.
    """
    cid = candidate["_id"]
    with candidate_schedule_guard(cid):
        require_candidate_lock_owner(cid)
        before = get_by_id("applications", application_id)
        if not before or before.get("candidate_id") != cid:
            raise BizError(BizCode.NOT_FOUND, "投递记录不存在")
        before = require_application_active(before)
        if before.get("version", 1) != version:
            raise BizError(BizCode.CONFLICT, "投递记录已更新，请刷新后重试")
        if before.get("job_id") == job["_id"]:
            raise BizError(BizCode.PARAM_INVALID, "请选择与当前投递不同的职位")
        configured_stages = {stage.stage_key for stage in job_stage_sequence(job)}
        initial_stage = next((stage for stage in ("new_resume", "pending_screen") if stage in configured_stages), None)
        if initial_stage is None:
            raise BizError(BizCode.STATE_INVALID, "新职位的流程没有配置简历筛选阶段，请先完善流程模板")
        if g.current_user.role == "hr" and before.get("owner_id") not in (None, "", g.current_user.user_id):
            raise BizError(BizCode.FORBIDDEN, "只有负责该投递的 HR 可以更换职位")
        if col("applications").find_one({
            "candidate_id": cid, "job_id": job["_id"],
            "status": {"$in": ["in_progress", "pending_onboard"]},
        }):
            raise BizError(BizCode.DUPLICATED, "该职位已有进行中的投递，请先处理原记录")

        before_locks = list(col("lock_records").find({"application_id": application_id, "released": False}))
        now = datetime.now()
        transition_id = next_id("stage_transitions")
        new_app = None
        changed = []
        archived = None
        session = None
        try:
            with business_transaction() as session:
                archived = col("applications").find_one_and_update(
                    {"_id": application_id, "version": version, "status": before["status"]},
                    {"$set": {
                        "current_stage": "job_changed", "status": "closed",
                        "archived_from_stage": before.get("current_stage", ""),
                        "closed_reason": reason, "closed_at": now, "updated_at": now,
                        "next_action": "", "next_action_role": "", "awaiting_hr_action": False,
                    }, "$inc": {"version": 1}},
                    return_document=ReturnDocument.AFTER, session=session,
                )
                if archived is None:
                    raise BizError(BizCode.CONFLICT, "投递记录已更新，请刷新后重试")
                release_stage_lock(archived, session=session)
                new_app = create_application(
                    candidate, job, source="job_change", operator_id=g.current_user.user_id,
                    operator_name=g.current_user.name, initial_stage=initial_stage,
                    initial_lock_days=7, initial_reason=f"更换投递职位，重新开始简历筛选；{reason}",
                    hr_assignment=True, extra={"previous_application_id": application_id}, session=session,
                    send_notification=False,
                )
                col("applications").update_one(
                    {"_id": application_id}, {"$set": {"replacement_application_id": new_app["_id"]}}, session=session,
                )
                # Retain completed records and all feedback/approval steps. Only
                # outstanding tasks are stopped, otherwise stale tasks remain on
                # the dashboard and may be mistaken for the new delivery.
                offers = list(col("offers").find({"application_id": application_id}, session=session))
                tasks = [
                    ("interviews", {"application_id": application_id, "status": {"$in": ["pending", "invited", "confirmed", "rescheduled"]}}, "cancelled"),
                    ("offer_approvals", {"offer_id": {"$in": [offer["_id"] for offer in offers]}, "status": "pending"}, "cancelled"),
                    ("offers", {"application_id": application_id, "status": {"$in": ["draft", "pending_send", "sent"]}}, "withdrawn"),
                    ("onboarding_records", {"application_id": application_id, "status": {"$nin": ["completed", "cancelled"]}}, "cancelled"),
                ]
                for collection, query, status in tasks:
                    for record in col(collection).find(query, session=session):
                        updated = col(collection).find_one_and_update(
                            {"_id": record["_id"], "version": record.get("version", {"$exists": False}), "status": record.get("status")},
                            {"$set": {"status": status, "previous_status": record.get("status"),
                                      "closed_reason": "更换投递职位", "updated_at": now}, "$inc": {"version": 1}},
                            return_document=ReturnDocument.AFTER, session=session,
                        )
                        if updated is None:
                            raise BizError(BizCode.CONFLICT, "原投递的关联记录已更新，请刷新后重试")
                        changed.append((collection, record, updated["version"]))
                col("stage_transitions").insert_one({
                    "_id": transition_id, "application_id": application_id,
                    "from_stage": before.get("current_stage", ""), "to_stage": "job_changed",
                    "reason": f"更换为{job.get('name', '')}，新投递 #{new_app['_id']} 从简历筛选开始；{reason}",
                    "operator_id": g.current_user.user_id, "operator_name": g.current_user.name, "created_at": now,
                }, session=session)
                write_log("application", "change_job", g.current_user.user_id, g.current_user.name,
                          biz_id=str(application_id), detail=f"new_application={new_app['_id']}; {reason}", session=session)
        except Exception:
            if session is None and archived is not None:
                for collection, record, updated_version in reversed(changed):
                    col(collection).replace_one({"_id": record["_id"], "version": updated_version}, record)
                if new_app:
                    for collection in ("lock_records", "stage_transitions"):
                        col(collection).delete_many({"application_id": new_app["_id"]})
                    col("operation_logs").delete_many({"biz_type": "application", "biz_id": str(new_app["_id"])})
                    col("notifications").delete_many({"dedupe_key": {"$regex": f"^new_candidate:application:{new_app['_id']}::"}})
                    col("applications").delete_one({"_id": new_app["_id"]})
                col("stage_transitions").delete_one({"_id": transition_id})
                col("applications").replace_one({"_id": application_id, "version": version + 1}, before)
                for lock in before_locks:
                    col("lock_records").replace_one({"_id": lock["_id"]}, lock, upsert=True)
            raise
        notify_application_created(new_app)
        return new_app
