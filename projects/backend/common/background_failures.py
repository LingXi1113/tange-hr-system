"""后台任务失败记录。

后台提醒、客保到期处理等辅助任务不能阻断主业务，但也不能用 ``pass`` 丢失异常。
本模块只保存业务 ID、操作类型和截断后的错误信息，不保存候选人隐私字段。
"""
from datetime import datetime

from flask import current_app

from common.db import col, next_id


def _failure_key(operation: str, biz_id) -> str:
    return f"{operation}:{biz_id}"


def record_background_failure(operation: str, biz_id, error: Exception,
                              details: dict | None = None) -> bool:
    """记录待重试后台失败；记录失败本身只写日志，不覆盖原始异常。"""
    now = datetime.now()
    key = _failure_key(operation, biz_id)
    doc = {
        "_id": next_id("background_failures"),
        "failure_key": key,
        "operation": operation,
        "biz_id": str(biz_id),
        "status": "pending",
        "retry_count": 1,
        "last_error": str(error)[:500],
        "details": details or {},
        "created_at": now,
        "updated_at": now,
        "last_failed_at": now,
    }
    try:
        collection = col("background_failures")
        existing = collection.find_one({"failure_key": key, "status": "pending"})
        if existing:
            collection.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {
                        "last_error": str(error)[:500],
                        "details": details or {},
                        "updated_at": now,
                        "last_failed_at": now,
                    },
                    "$inc": {"retry_count": 1},
                },
            )
        else:
            collection.insert_one(doc)
        return True
    except Exception:
        current_app.logger.exception(
            "记录后台失败任务失败 operation=%s biz_id=%s", operation, biz_id,
        )
        return False


def resolve_background_failure(operation: str, biz_id) -> None:
    """业务后续重试成功后关闭同一失败任务。"""
    try:
        col("background_failures").update_many(
            {"failure_key": _failure_key(operation, biz_id), "status": "pending"},
            {"$set": {"status": "resolved", "resolved_at": datetime.now(),
                       "updated_at": datetime.now()}},
        )
    except Exception:
        current_app.logger.exception(
            "关闭后台失败任务失败 operation=%s biz_id=%s", operation, biz_id,
        )
