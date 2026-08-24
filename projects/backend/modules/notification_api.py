"""站内通知 API：列表/未读数/标记已读/全部已读（访问时惰性触发规则扫描）。"""
from datetime import datetime

from flask import Blueprint, current_app, g, request

from common.background_failures import record_background_failure, resolve_background_failure
from common.db import col
from common.decorators import login_required
from common.errors import BizError
from common.notifier import generate_due_notifications
from common.response import BizCode, ok, paged

bp = Blueprint("notification_api", __name__, url_prefix="/api/notifications")


def _safe_generate():
    """规则扫描失败不影响通知读取。"""
    try:
        generate_due_notifications()
    except Exception as exc:
        current_app.logger.exception("站内通知规则扫描失败")
        record_background_failure("notification_scan", "all", exc)
        return False
    resolve_background_failure("notification_scan", "all")
    return True


def _view(doc: dict) -> dict:
    from common.db import dt

    return {
        "id": doc["_id"],
        "scene": doc.get("scene", ""),
        "title": doc.get("title", ""),
        "content": doc.get("content", ""),
        "biz_type": doc.get("biz_type", ""),
        "biz_id": doc.get("biz_id", ""),
        "route": doc.get("route", ""),
        "read_at": dt(doc.get("read_at")),
        "unread": doc.get("read_at") is None,
        "created_at": dt(doc.get("created_at")),
    }


@bp.get("")
@login_required
def list_notifications():
    _safe_generate()
    args = request.args
    query = {"receiver_id": g.current_user.user_id}
    if args.get("status") == "unread":
        query["read_at"] = None
    page = max(int(args.get("page", 1)), 1)
    page_size = min(max(int(args.get("page_size", 10)), 1), 100)
    rows = list(col("notifications").find(query).sort("created_at", -1))
    total = len(rows)
    sliced = rows[(page - 1) * page_size: page * page_size]
    return paged([_view(d) for d in sliced], total, page, page_size)


@bp.get("/unread-count")
@login_required
def unread_count():
    _safe_generate()
    count = col("notifications").count_documents(
        {"receiver_id": g.current_user.user_id, "read_at": None})
    return ok({"count": count})


@bp.post("/<int:notification_id>/read")
@login_required
def mark_read(notification_id: int):
    doc = col("notifications").find_one({"_id": notification_id})
    if doc is None:
        raise BizError(BizCode.NOT_FOUND, "通知不存在")
    if doc.get("receiver_id") != g.current_user.user_id:
        raise BizError(BizCode.FORBIDDEN, "不能操作他人的通知")
    col("notifications").update_one(
        {"_id": notification_id, "read_at": None},
        {"$set": {"read_at": datetime.now()}})
    return ok(None)


@bp.post("/read-all")
@login_required
def mark_all_read():
    result = col("notifications").update_many(
        {"receiver_id": g.current_user.user_id, "read_at": None},
        {"$set": {"read_at": datetime.now()}})
    return ok({"marked": result.modified_count})
