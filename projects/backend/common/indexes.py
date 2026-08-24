"""招聘核心业务唯一约束。

查询前置校验只能优化用户提示，真正的并发保护必须落在 MongoDB 唯一索引上。
"""
from flask import current_app

from pymongo.errors import PyMongoError

from common.db import col


CORE_INDEXES = (
    (
        "applications",
        "uq_active_application_candidate_job",
        [("candidate_id", 1), ("job_id", 1)],
        {"unique": True, "partialFilterExpression": {
            "status": {"$in": ["in_progress", "pending_onboard"]},
        }},
    ),
    (
        "lock_records",
        "uq_active_candidate_lock",
        [("candidate_id", 1)],
        {"unique": True, "partialFilterExpression": {"released": False}},
    ),
    (
        "offers",
        "uq_active_offer_application",
        [("application_id", 1)],
        {"unique": True, "partialFilterExpression": {
            "status": {"$in": ["draft", "pending_send", "sent"]},
        }},
    ),
    (
        "offer_approvals",
        "uq_offer_approval_offer",
        [("offer_id", 1)],
        {"unique": True},
    ),
    (
        "onboarding_records",
        "uq_onboarding_application",
        [("application_id", 1)],
        {"unique": True},
    ),
    (
        "candidates",
        "uq_candidate_phone_key",
        [("phone_key", 1)],
        {"unique": True, "partialFilterExpression": {"phone_key": {"$exists": True}}},
    ),
    (
        "candidates",
        "uq_candidate_email_key",
        [("email_key", 1)],
        {"unique": True, "partialFilterExpression": {"email_key": {"$exists": True}}},
    ),
    (
        "interview_feedback",
        "uq_interview_feedback_interview",
        [("interview_id", 1)],
        {"unique": True},
    ),
    (
        "interviews",
        "ix_interview_candidate_time",
        [("candidate_id", 1), ("status", 1), ("start_at", 1), ("end_at", 1)],
        {},
    ),
)


def ensure_core_indexes() -> bool:
    """初始化核心唯一索引；生产环境索引失败必须阻止启动。"""
    success = True
    for collection_name, index_name, keys, options in CORE_INDEXES:
        try:
            col(collection_name).create_index(keys, name=index_name, **options)
        except PyMongoError:
            success = False
            current_app.logger.exception(
                "核心唯一索引初始化失败 collection=%s index=%s",
                collection_name, index_name,
            )
            if current_app.config.get("ENV_NAME") == "production" and not current_app.config.get("TESTING"):
                raise
    return success
