"""操作日志查询（仅 HR 可查看）。"""
from datetime import datetime, time

from flask import Blueprint, request

from common.db import col, dt
from common.decorators import role_required
from common.errors import BizError
from common.response import BizCode, ok, paged
from common.roles import HR

bp = Blueprint("audit_api", __name__, url_prefix="/api/audit-logs")


@bp.get("")
@role_required(HR)
def list_audit_logs():
    args = request.args
    query = {}
    for key in ("biz_type", "action", "operator_id"):
        if args.get(key):
            query[key] = args[key]
    if args.get("date_from") or args.get("date_to"):
        try:
            created = {}
            if args.get("date_from"):
                created["$gte"] = datetime.strptime(args["date_from"], "%Y-%m-%d")
            if args.get("date_to"):
                created["$lte"] = datetime.combine(datetime.strptime(args["date_to"], "%Y-%m-%d").date(), time(23, 59, 59))
            query["created_at"] = created
        except ValueError as exc:
            raise BizError(BizCode.PARAM_INVALID, "日期格式应为 YYYY-MM-DD") from exc
    if args.get("keyword"):
        query["$or"] = [{"detail": {"$regex": args["keyword"]}},
                         {"biz_id": {"$regex": args["keyword"]}}]
    page = max(int(args.get("page", 1)), 1)
    page_size = min(max(int(args.get("page_size", 20)), 1), 100)
    total = col("operation_logs").count_documents(query)
    rows = list(col("operation_logs").find(query).sort("created_at", -1)
                .skip((page - 1) * page_size).limit(page_size))
    view = [{
        "id": row.get("_id"), "biz_type": row.get("biz_type", ""), "biz_id": row.get("biz_id", ""),
        "action": row.get("action", ""), "operator_id": row.get("operator_id", ""),
        "operator_name": row.get("operator_name", ""), "detail": row.get("detail", ""),
        "created_at": dt(row.get("created_at")),
    } for row in rows]
    return paged(view, total, page, page_size)
