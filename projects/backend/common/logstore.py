"""操作日志写入（MongoDB operation_logs 集合）。"""
from datetime import datetime

from .db import col, next_id


def write_log(biz_type: str, action: str, operator_id: str = "", operator_name: str = "",
              biz_id: str = "", detail: str = "", session=None) -> None:
    if session is None:
        from common.atomic import current_session

        session = current_session()
    col("operation_logs").insert_one({
        "_id": next_id("operation_logs", session=session),
        "biz_type": biz_type,
        "biz_id": biz_id,
        "action": action,
        "operator_id": operator_id,
        "operator_name": operator_name,
        "detail": detail,
        "created_at": datetime.now(),
    }, session=session)
