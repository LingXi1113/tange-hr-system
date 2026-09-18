"""人才库（PRD v1.1 Sprint 5）。

- 集合 talent_pool：候选人关联结构（只存 candidate_id 引用，不复制主数据）；
- candidate_id 唯一索引：同一候选人不能重复进入人才库；
- 加入/移出/重新激活/批量操作/导出全部写 operation_logs，导出写 export_logs；
- 重新激活 = 为候选人新建目标职位的应聘记录（复用 flow.create_application 的
  锁定期与重复投递校验），库内记录状态置为 activated。
"""
import csv
import io
import json
from datetime import datetime

from flask import Blueprint, Response, current_app, g, request

from common.background_failures import record_background_failure
from common.db import col, get_by_id, insert_doc, next_id, update_doc
from common.access import CANDIDATE_READ_ROLES, can_view_pii
from common.decorators import login_required, role_required
from common.errors import BizError
from common.flow import create_application
from common.logstore import write_log
from common.response import BizCode, ok, paged
from common.roles import HR, SUPER_ADMIN

bp = Blueprint("talent_pool_api", __name__, url_prefix="/api/talent-pool")

POOL_SOURCES = (
    "elimination_added", "offer_rejected", "business_rejected",
    "interview_rejected", "abandoned_added", "manual", "batch_import", "archived",
)
POOL_STATUSES = ("active", "activated")

SOURCE_TEXT = {
    "elimination_added": "淘汰加入", "offer_rejected": "Offer拒绝加入",
    "business_rejected": "业务复筛不通过", "interview_rejected": "面试不通过",
    "abandoned_added": "流程放弃加入", "manual": "手动加入",
    "batch_import": "批量导入", "archived": "客保到期归档",
}

ELIMINATED_SOURCES = {
    "elimination_added", "offer_rejected", "business_rejected", "interview_rejected",
}


def ensure_indexes():
    try:
        col("talent_pool").create_index("candidate_id", unique=True)
        col("talent_pool_folders").create_index("name", unique=True)
        return True
    except Exception as exc:
        current_app.logger.exception("人才库唯一索引初始化失败")
        record_background_failure("talent_pool_index", "talent_pool", exc)
        if current_app.config.get("ENV_NAME") == "production" and not current_app.config.get("TESTING"):
            raise
        return False


def _ensure_indexes():
    """兼容业务调用：索引失败时保留可观测性，不再静默忽略。"""
    return ensure_indexes()


def _mask_phone(v):
    return v[:3] + "****" + v[-4:] if len(v) >= 7 else v


def _mask_email(v):
    if "@" not in v or len(v) < 6:
        return v
    head, tail = v.split("@", 1)
    return head[:2] + "***@" + tail


def _is_eliminated_entry(doc: dict) -> bool:
    # 历史客保到期记录曾使用 elimination_added，按原因兼容回职位归档。
    return doc.get("source") in ELIMINATED_SOURCES \
        and not str(doc.get("reason") or "").startswith("阶段规则到期")


def _folder_key(doc: dict) -> str:
    if _is_eliminated_entry(doc):
        return "system:eliminated"
    if doc.get("folder_id") and get_by_id("talent_pool_folders", doc.get("folder_id")):
        return f"custom:{int(doc['folder_id'])}"
    if doc.get("recommended_job_id"):
        return f"job:{int(doc['recommended_job_id'])}"
    return "system:pending_archive"


def _folder_name(doc: dict) -> str:
    key = _folder_key(doc)
    if key == "system:eliminated":
        return "已淘汰"
    if key == "system:pending_archive":
        return "待 HR 归档"
    kind, raw_id = key.split(":", 1)
    collection = "jobs" if kind == "job" else "talent_pool_folders"
    target = get_by_id(collection, int(raw_id)) or {}
    return target.get("name", "未命名文件夹")


def _pool_view(doc: dict, mask: bool = True) -> dict:
    from common.db import dt

    candidate = get_by_id("candidates", doc["candidate_id"]) or {}
    job_name = ""
    if doc.get("recommended_job_id"):
        job = get_by_id("jobs", doc["recommended_job_id"]) or {}
        job_name = job.get("name", "")
    return {
        "id": doc["_id"],
        "candidate_id": doc["candidate_id"],
        "candidate_name": candidate.get("name", ""),
        "phone": _mask_phone(candidate.get("phone", "")) if mask else candidate.get("phone", ""),
        "email": _mask_email(candidate.get("email", "")) if mask else candidate.get("email", ""),
        "category": doc.get("category", ""),
        "tags": doc.get("tags", []),
        "source": doc.get("source", ""),
        "source_text": SOURCE_TEXT.get(doc.get("source", ""), doc.get("source", "")),
        "reason": doc.get("reason", ""),
        "recommended_job_id": doc.get("recommended_job_id"),
        "recommended_job_name": job_name,
        "folder_id": doc.get("folder_id"),
        "folder_key": _folder_key(doc),
        "folder_name": _folder_name(doc),
        "last_contact_at": dt(doc.get("last_contact_at")),
        "status": doc.get("status", "active"),
        "created_at": dt(doc.get("created_at")),
        "updated_at": dt(doc.get("updated_at")),
    }


def _add_one(candidate_id: int, payload: dict) -> dict:
    _ensure_indexes()
    candidate = get_by_id("candidates", candidate_id)
    if candidate is None:
        raise BizError(BizCode.NOT_FOUND, f"候选人不存在: {candidate_id}")
    if col("talent_pool").find_one({"candidate_id": candidate_id}):
        raise BizError(BizCode.DUPLICATED, f"候选人「{candidate.get('name', '')}」已在人才库中")
    source = payload.get("source", "manual")
    if source not in POOL_SOURCES:
        raise BizError(BizCode.PARAM_INVALID, f"未知入库来源: {source}")
    folder_id = int(payload["folder_id"]) if payload.get("folder_id") else None
    if folder_id and get_by_id("talent_pool_folders", folder_id) is None:
        raise BizError(BizCode.NOT_FOUND, "归档文件夹不存在")
    doc = insert_doc("talent_pool", {
        "candidate_id": candidate_id,
        "category": (payload.get("category") or "").strip(),
        "tags": [t.strip() for t in (payload.get("tags") or []) if str(t).strip()],
        "source": source,
        "reason": (payload.get("reason") or "").strip(),
        "recommended_job_id": int(payload["recommended_job_id"]) if payload.get("recommended_job_id") else None,
        "folder_id": folder_id,
        "last_contact_at": None,
        "status": "active",
        "added_by": g.current_user.user_id,
    })
    write_log("talent_pool", "add", g.current_user.user_id, g.current_user.name,
              biz_id=str(doc["_id"]),
              detail=f"candidate={candidate_id} source={source}")
    return doc


@bp.get("")
@role_required(*CANDIDATE_READ_ROLES)
def list_pool():
    args = request.args
    # 兼容旧参数但不允许普通角色通过 mask=0 获取原文。
    mask = True if not can_view_pii() else args.get("mask", "1") != "0"
    query = {}
    if args.get("status"):
        query["status"] = args["status"]
    else:
        query["status"] = {"$ne": "removed"}
    if args.get("category"):
        query["category"] = args["category"]
    if args.get("source"):
        query["source"] = args["source"]
    if args.get("tag"):
        query["tags"] = args["tag"]
    if args.get("job_id"):
        query["recommended_job_id"] = int(args["job_id"])
    if args.get("candidate_id"):
        query["candidate_id"] = int(args["candidate_id"])

    rows = list(col("talent_pool").find(query).sort("_id", -1))
    if args.get("folder_key") and args["folder_key"] != "all":
        rows = [row for row in rows if _folder_key(row) == args["folder_key"]]
    # 姓名搜索（候选人主档字段，不复制数据，仅过滤）
    if args.get("keyword"):
        kw = args["keyword"]
        matched_ids = {c["_id"] for c in col("candidates").find(
            {"$or": [{"name": {"$regex": kw}}, {"phone": {"$regex": kw}},
                     {"email": {"$regex": kw}}]}, {"_id": 1})}
        rows = [r for r in rows if r["candidate_id"] in matched_ids]

    page = max(int(args.get("page", 1)), 1)
    page_size = min(max(int(args.get("page_size", 10)), 1), 100)
    total = len(rows)
    sliced = rows[(page - 1) * page_size: page * page_size]
    return paged([_pool_view(r, mask=mask) for r in sliced], total, page, page_size)


@bp.get("/folders")
@role_required(*CANDIDATE_READ_ROLES)
def list_folders():
    """人才库左侧目录树：系统目录、职位目录和超级管理员自定义目录。"""
    rows = list(col("talent_pool").find({"status": {"$ne": "removed"}}))
    counts = {}
    for row in rows:
        key = _folder_key(row)
        counts[key] = counts.get(key, 0) + 1

    job_nodes = [{
        "key": f"job:{job['_id']}", "name": job.get("name", "未命名职位"),
        "type": "job", "count": counts.get(f"job:{job['_id']}", 0),
        "system": True,
    } for job in col("jobs").find({}, {"name": 1}).sort("name", 1)]
    custom_nodes = [{
        "key": f"custom:{folder['_id']}", "id": folder["_id"],
        "name": folder.get("name", "未命名文件夹"), "type": "custom",
        "count": counts.get(f"custom:{folder['_id']}", 0), "system": False,
    } for folder in col("talent_pool_folders").find({}).sort([("sort_order", 1), ("_id", 1)])]
    tree = [{
        "key": "all", "name": "全部归档", "type": "root", "count": len(rows),
        "system": True, "children": [
            {"key": "system:eliminated", "name": "已淘汰", "type": "system",
             "count": counts.get("system:eliminated", 0), "system": True},
            {"key": "system:pending_archive", "name": "待 HR 归档", "type": "system",
             "count": counts.get("system:pending_archive", 0), "system": True},
            {"key": "group:jobs", "name": "职位人才库", "type": "group",
             "count": sum(item["count"] for item in job_nodes), "system": True,
             "selectable": False, "children": job_nodes},
            {"key": "group:custom", "name": "自定义文件夹", "type": "group",
             "count": sum(item["count"] for item in custom_nodes), "system": True,
             "selectable": False, "children": custom_nodes},
        ],
    }]
    return ok({"tree": tree, "custom_folders": custom_nodes, "total": len(rows)})


@bp.post("/folders")
@role_required(SUPER_ADMIN)
def create_folder():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        raise BizError(BizCode.PARAM_INVALID, "文件夹名称必填")
    if col("talent_pool_folders").find_one({"name": name}):
        raise BizError(BizCode.DUPLICATED, "人才库中已存在同名文件夹")
    doc = insert_doc("talent_pool_folders", {
        "name": name, "sort_order": int(payload.get("sort_order") or 0),
        "created_by": g.current_user.user_id,
    })
    write_log("talent_pool_folder", "create", g.current_user.user_id, g.current_user.name,
              biz_id=str(doc["_id"]), detail=name)
    return ok({"id": doc["_id"], "name": name})


@bp.put("/folders/<int:folder_id>")
@role_required(SUPER_ADMIN)
def rename_folder(folder_id: int):
    folder = get_by_id("talent_pool_folders", folder_id)
    if folder is None:
        raise BizError(BizCode.NOT_FOUND, "文件夹不存在")
    name = ((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name:
        raise BizError(BizCode.PARAM_INVALID, "文件夹名称必填")
    duplicate = col("talent_pool_folders").find_one({"name": name, "_id": {"$ne": folder_id}})
    if duplicate:
        raise BizError(BizCode.DUPLICATED, "人才库中已存在同名文件夹")
    update_doc("talent_pool_folders", folder_id, {"name": name})
    write_log("talent_pool_folder", "rename", g.current_user.user_id, g.current_user.name,
              biz_id=str(folder_id), detail=f"{folder.get('name', '')} -> {name}")
    return ok({"id": folder_id, "name": name})


@bp.delete("/folders/<int:folder_id>")
@role_required(SUPER_ADMIN)
def delete_folder(folder_id: int):
    if request.args.get("confirm") != "1":
        raise BizError(BizCode.PARAM_INVALID, "删除文件夹需要二次确认（confirm=1）")
    folder = get_by_id("talent_pool_folders", folder_id)
    if folder is None:
        raise BizError(BizCode.NOT_FOUND, "文件夹不存在")
    moved = col("talent_pool").update_many(
        {"folder_id": folder_id}, {"$set": {"folder_id": None, "updated_at": datetime.now()}},
    ).modified_count
    col("talent_pool_folders").delete_one({"_id": folder_id})
    write_log("talent_pool_folder", "delete", g.current_user.user_id, g.current_user.name,
              biz_id=str(folder_id), detail=f"{folder.get('name', '')}; moved={moved}")
    return ok({"moved_to_pending_archive": moved})


@bp.post("")
@role_required(HR)
def add_to_pool():
    """单个或批量加入（candidate_id 或 candidate_ids）。"""
    payload = request.get_json(silent=True) or {}
    single_mode = not payload.get("candidate_ids")
    ids = payload.get("candidate_ids") or (
        [payload["candidate_id"]] if payload.get("candidate_id") else [])
    if not ids:
        raise BizError(BizCode.PARAM_INVALID, "缺少 candidate_id 或 candidate_ids")
    added, duplicates, missing = [], [], []
    for cid in ids:
        try:
            doc = _add_one(int(cid), payload)
            added.append(_pool_view(doc))
        except BizError as e:
            if single_mode:
                raise  # 单条加入：重复/不存在直接报错
            if e.code == BizCode.DUPLICATED:
                duplicates.append({"candidate_id": int(cid), "msg": e.msg})
            elif e.code == BizCode.NOT_FOUND:
                missing.append({"candidate_id": int(cid), "msg": e.msg})
            else:
                raise
    if not added and not duplicates:
        raise BizError(BizCode.PARAM_INVALID, "没有可加入的候选人")
    return ok({"added": added, "duplicates": duplicates, "missing": missing})


@bp.put("/<int:entry_id>")
@role_required(HR)
def update_entry(entry_id: int):
    doc = get_by_id("talent_pool", entry_id)
    if doc is None:
        raise BizError(BizCode.NOT_FOUND, "人才库记录不存在")
    payload = request.get_json(silent=True) or {}
    fields = {}
    if "category" in payload:
        fields["category"] = (payload["category"] or "").strip()
    if "tags" in payload:
        fields["tags"] = [t.strip() for t in (payload["tags"] or []) if str(t).strip()]
    if "reason" in payload:
        fields["reason"] = (payload["reason"] or "").strip()
    if "recommended_job_id" in payload:
        rid = payload["recommended_job_id"]
        if rid and get_by_id("jobs", int(rid)) is None:
            raise BizError(BizCode.NOT_FOUND, "可推荐职位不存在")
        fields["recommended_job_id"] = int(rid) if rid else None
    if "folder_id" in payload:
        folder_id = payload["folder_id"]
        if folder_id and get_by_id("talent_pool_folders", int(folder_id)) is None:
            raise BizError(BizCode.NOT_FOUND, "归档文件夹不存在")
        fields["folder_id"] = int(folder_id) if folder_id else None
    if "last_contact_at" in payload:
        raw = (payload["last_contact_at"] or "").strip()
        if raw:
            try:
                fields["last_contact_at"] = datetime.strptime(raw, "%Y-%m-%d")
            except ValueError:
                raise BizError(BizCode.PARAM_INVALID, "最近联系时间格式应为 YYYY-MM-DD")
        else:
            fields["last_contact_at"] = None
    update_doc("talent_pool", entry_id, fields)
    doc.update(fields)
    write_log("talent_pool", "update", g.current_user.user_id, g.current_user.name,
              biz_id=str(entry_id))
    return ok(_pool_view(doc))


@bp.post("/batch-tags")
@role_required(HR)
def batch_tags():
    """批量修改标签：mode=replace 覆盖 / append 追加去重。"""
    payload = request.get_json(silent=True) or {}
    entry_ids = payload.get("entry_ids") or []
    tags = [t.strip() for t in (payload.get("tags") or []) if str(t).strip()]
    mode = payload.get("mode", "replace")
    if not entry_ids:
        raise BizError(BizCode.PARAM_INVALID, "缺少 entry_ids")
    if mode not in ("replace", "append"):
        raise BizError(BizCode.PARAM_INVALID, "mode 必须是 replace/append")
    updated = 0
    for eid in entry_ids:
        doc = get_by_id("talent_pool", int(eid))
        if doc is None:
            continue
        new_tags = tags if mode == "replace" else list(dict.fromkeys(
            list(doc.get("tags", [])) + tags))
        update_doc("talent_pool", doc["_id"], {"tags": new_tags})
        updated += 1
    write_log("talent_pool", "batch_tags", g.current_user.user_id, g.current_user.name,
              detail=f"entries={len(entry_ids)} mode={mode} tags={','.join(tags)}")
    return ok({"updated": updated})


@bp.delete("/<int:entry_id>")
@role_required(HR)
def remove_entry(entry_id: int):
    if request.args.get("confirm") != "1":
        raise BizError(BizCode.PARAM_INVALID, "移出需要二次确认（confirm=1）")
    doc = get_by_id("talent_pool", entry_id)
    if doc is None:
        raise BizError(BizCode.NOT_FOUND, "人才库记录不存在")
    col("talent_pool").delete_one({"_id": entry_id})
    write_log("talent_pool", "remove", g.current_user.user_id, g.current_user.name,
              biz_id=str(entry_id), detail=f"candidate={doc['candidate_id']}")
    return ok(None)


@bp.post("/batch-remove")
@role_required(HR)
def batch_remove():
    payload = request.get_json(silent=True) or {}
    entry_ids = payload.get("entry_ids") or []
    if not entry_ids:
        raise BizError(BizCode.PARAM_INVALID, "缺少 entry_ids")
    result = col("talent_pool").delete_many({"_id": {"$in": [int(i) for i in entry_ids]}})
    write_log("talent_pool", "batch_remove", g.current_user.user_id, g.current_user.name,
              detail=f"removed={result.deleted_count}")
    return ok({"removed": result.deleted_count})


@bp.post("/<int:entry_id>/activate")
@role_required(HR)
def activate(entry_id: int):
    """重新激活：为候选人在目标职位新建应聘记录（走现有锁定/重复校验）。"""
    doc = get_by_id("talent_pool", entry_id)
    if doc is None:
        raise BizError(BizCode.NOT_FOUND, "人才库记录不存在")
    if doc.get("status") != "active":
        raise BizError(BizCode.STATE_INVALID, "仅待激活状态可重新激活")
    payload = request.get_json(silent=True) or {}
    job = get_by_id("jobs", int(payload.get("job_id") or 0))
    if job is None:
        raise BizError(BizCode.PARAM_INVALID, "请选择激活的目标职位")
    candidate = get_by_id("candidates", doc["candidate_id"])
    app_doc = create_application(
        candidate, job, source="talent_pool",
        operator_id=g.current_user.user_id, operator_name=g.current_user.name,
    )
    update_doc("talent_pool", entry_id, {
        "status": "activated",
        "activated_at": datetime.now(),
        "activated_job_id": job["_id"],
        "activated_application_id": app_doc["_id"],
    })
    write_log("talent_pool", "activate", g.current_user.user_id, g.current_user.name,
              biz_id=str(entry_id),
              detail=f"candidate={doc['candidate_id']} job={job['_id']} app={app_doc['_id']}")
    return ok({"application_id": app_doc["_id"], "entry": _pool_view(get_by_id("talent_pool", entry_id))})


@bp.get("/export")
@role_required(HR)
def export_pool():
    args = request.args
    query = {"status": {"$ne": "removed"}}
    if args.get("category"):
        query["category"] = args["category"]
    if args.get("source"):
        query["source"] = args["source"]
    rows = list(col("talent_pool").find(query).sort("_id", -1))
    if args.get("folder_key") and args["folder_key"] != "all":
        rows = [row for row in rows if _folder_key(row) == args["folder_key"]]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["姓名", "手机号", "邮箱", "归档目录", "分类", "标签", "来源", "加入原因",
                     "可推荐职位", "最近联系时间", "状态", "加入时间"])
    for r in rows:
        v = _pool_view(r, mask=False)
        writer.writerow([v["candidate_name"], v["phone"], v["email"], v["folder_name"], v["category"],
                         ",".join(v["tags"]), v["source_text"], v["reason"],
                         v["recommended_job_name"], v["last_contact_at"], v["status"],
                         v["created_at"]])
    col("export_logs").insert_one({
        "exporter_id": g.current_user.user_id, "exporter_name": g.current_user.name,
        "scene": "talent_pool", "conditions": json.dumps(dict(args), ensure_ascii=False),
        "row_count": len(rows), "created_at": datetime.now(),
    })
    write_log("talent_pool", "export", g.current_user.user_id, g.current_user.name,
              detail=f"rows={len(rows)}")
    write_log("export", "talent_pool", g.current_user.user_id, g.current_user.name,
              detail=f"rows={len(rows)}")
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=talent_pool.csv"})
