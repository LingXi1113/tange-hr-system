"""Short-lived distributed guards for candidate interview scheduling."""
from contextlib import contextmanager
from datetime import datetime, timedelta
from time import monotonic, sleep
from uuid import uuid4

from flask import current_app
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from common.db import col
from common.errors import BizError
from common.response import BizCode


@contextmanager
def candidate_schedule_guard(candidate_id: int, timeout_seconds: float = 2.0):
    """Serialize conflict-check + write for one candidate across processes.

    A normal interval-overlap query cannot be made unique with a MongoDB
    index. This short lease closes that check-then-insert/update race while
    still expiring automatically if a worker dies.
    """
    owner = uuid4().hex
    deadline = monotonic() + timeout_seconds
    acquired = False
    while monotonic() < deadline:
        now = datetime.now()
        try:
            guard = col("interview_guards").find_one_and_update(
                {
                    "_id": int(candidate_id),
                    "$or": [
                        {"lease_until": {"$lte": now}},
                        {"lease_until": {"$exists": False}},
                        {"owner": owner},
                    ],
                },
                {"$set": {
                    "owner": owner,
                    "lease_until": now + timedelta(seconds=30),
                    "updated_at": now,
                }},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            if guard and guard.get("owner") == owner:
                acquired = True
                break
        except DuplicateKeyError:
            # Two processes may create the guard document simultaneously;
            # retry and let the winning process finish its short operation.
            pass
        sleep(0.01)

    if not acquired:
        raise BizError(BizCode.CONFLICT, "该候选人的面试排期正在被其他请求修改，请稍后重试")
    try:
        yield
    finally:
        try:
            col("interview_guards").update_one(
                {"_id": int(candidate_id), "owner": owner},
                {"$set": {"lease_until": datetime.now(), "updated_at": datetime.now()}},
            )
        except Exception:
            current_app.logger.exception(
                "释放面试排期保护失败 candidate_id=%s", candidate_id,
            )
