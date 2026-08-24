"""MongoDB 轻量后台任务租约，避免多进程重复扫描。"""
from datetime import datetime, timedelta
from uuid import uuid4

from flask import current_app
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from common.db import col


def new_worker_id(name: str) -> str:
    return f"{name}:{uuid4().hex}"


def acquire_lease(name: str, owner: str, ttl_seconds: int = 180) -> bool:
    now = datetime.now()
    try:
        doc = col("worker_leases").find_one_and_update(
            {
                "_id": name,
                "$or": [
                    {"lease_until": {"$lte": now}},
                    {"lease_until": {"$exists": False}},
                    {"owner": owner},
                ],
            },
            {"$set": {
                "owner": owner,
                "lease_until": now + timedelta(seconds=max(ttl_seconds, 30)),
                "updated_at": now,
            }},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return bool(doc and doc.get("owner") == owner)
    except DuplicateKeyError:
        # 多进程首次抢占同一租约时，只有一个进程应继续执行。
        return False
    except Exception:
        current_app.logger.exception("后台任务租约获取失败 worker=%s", name)
        return False


def release_lease(name: str, owner: str) -> None:
    try:
        col("worker_leases").update_one(
            {"_id": name, "owner": owner},
            {"$set": {"lease_until": datetime.now(), "updated_at": datetime.now()}},
        )
    except Exception:
        current_app.logger.exception("后台任务租约释放失败 worker=%s", name)
