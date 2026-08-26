"""候选人与简历管理（MongoDB 版）：主档/应聘记录/查重/导入导出/简历上传解析。"""
import csv
import io
import json
import os
import tempfile
from datetime import datetime

from flask import Blueprint, Response, current_app, g, request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from werkzeug.utils import secure_filename

from common.access import CANDIDATE_READ_ROLES, RESUME_ACCESS_ROLES, can_view_pii, redact_candidate
from common.candidate_identity import ensure_candidate_indexes, identity_keys, identity_update
from common.db import col, get_by_id, insert_doc, paginate, update_doc, dt
from common.decorators import login_required, role_required
from common.errors import BizError
from common.file_service import (
    read_file_bytes,
    resolve_local,
    save_uploaded_file,
)
from common.flow import (
    active_lock_for_candidate,
    application_to_dict,
    create_application,
    lock_info_for_candidate,
)
from common.logstore import write_log
from common.mongo import MongoUnavailable
from common.privacy import purge_candidate
from common.resume_parser import parse_resume_file
from common.response import BizCode, ok, paged
from common.roles import HR
from common.status import APP_IN_PROGRESS
from common.status import APP_PENDING_ONBOARD
from common.consistency import reconcile_application_status
from common.storage import StorageError

bp = Blueprint("candidate_api", __name__)


def _get_candidate_or_404(cid: int) -> dict:
    c = get_by_id("candidates", cid)
    if c is None:
        raise BizError(BizCode.NOT_FOUND, "候选人不存在")
    return c


def _find_duplicates(phone: str, email: str, exclude_id: int = None):
    conds = []
    if phone:
        conds.extend([{"phone": phone}, {"phone_key": identity_keys(phone, {}).get("phone_key")}])
    if email:
        conds.extend([{"email": email}, {"email_key": identity_keys({}, email).get("email_key")}])
    if not conds:
        return []
    query = {"$or": conds}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    return list(col("candidates").find(query))


def _latest_application(candidate_id: int):
    app = col("applications").find_one({"candidate_id": candidate_id}, sort=[("_id", -1)])
    return reconcile_application_status(app) if app else None


def _candidate_view(c: dict, mask: bool = True) -> dict:
    # mask 参数仅保留兼容性，不能让普通角色通过 mask=0 关闭脱敏。
    data = redact_candidate(c, include_pii=can_view_pii() and not mask)
    data["version"] = int(c.get("version", 1))
    return data


def _candidate_row(c: dict, mask: bool) -> dict:
    data = _candidate_view(c, mask=mask)
    app = _latest_application(c["_id"])
    if app:
        job = get_by_id("jobs", app["job_id"]) or {}
        data["latest_application"] = {
            "id": app["_id"], "job_name": job.get("name", ""),
            "current_stage": app.get("current_stage", ""), "status": app.get("status", ""),
        }
    else:
        data["latest_application"] = None
    data["lock"] = lock_info_for_candidate(c["_id"])
    return data


@bp.get("/api/candidates")
@role_required(*CANDIDATE_READ_ROLES)
def list_candidates():
    args = request.args
    mask = True if not can_view_pii() else args.get("mask", "1") != "0"
    query = {}
    if args.get("keyword"):
        kw = args["keyword"]
        query["$or"] = [{"name": {"$regex": kw}}, {"phone": {"$regex": kw}},
                        {"email": {"$regex": kw}}]
    if args.get("source"):
        query["source"] = args["source"]
    if args.get("tag"):
        query["tags"] = {"$regex": args["tag"]}
    items = list(col("candidates").find(query).sort("_id", -1))
    # 应聘记录相关过滤（职位/阶段）
    if args.get("job_id") or args.get("stage"):
        filtered = []
        for c in items:
            app_query = {"candidate_id": c["_id"]}
            if args.get("job_id"):
                app_query["job_id"] = int(args["job_id"])
            if args.get("stage"):
                app_query["current_stage"] = args["stage"]
            if col("applications").find_one(app_query):
                filtered.append(c)
        items = filtered
    if args.get("locked") == "1":
        items = [c for c in items if active_lock_for_candidate(c["_id"])]
    page = max(int(args.get("page", 1)), 1)
    page_size = min(max(int(args.get("page_size", 10)), 1), 100)
    sliced, total, page, page_size = paginate(items, page, page_size)
    write_log("candidate", "list_view", g.current_user.user_id, g.current_user.name,
              detail=f"page={page}; page_size={page_size}; rows={len(sliced)}")
    return paged([_candidate_row(c, mask) for c in sliced], total, page, page_size)


@bp.get("/api/candidates/<int:cid>")
@role_required(*CANDIDATE_READ_ROLES)
def get_candidate(cid: int):
    c = _get_candidate_or_404(cid)
    mask = True if not can_view_pii() else request.args.get("mask", "1") != "0"
    data = _candidate_view(c, mask=mask)
    data["education"] = c.get("education") or []
    data["work_experience"] = c.get("work_experience") or []
    data["attachments"] = [{
        "id": a["_id"], "file_name": a.get("file_name", ""), "file_type": a.get("file_type", ""),
        "parse_status": a.get("parse_status", ""), "created_at": dt(a.get("created_at")),
    } for a in col("attachments").find({"candidate_id": cid}).sort("_id", 1)]
    data["lock"] = lock_info_for_candidate(cid)
    data["applications"] = []
    apps = list(col("applications").find({"candidate_id": cid}).sort("_id", -1))
    for app in apps:
        app = reconcile_application_status(app)
        d = application_to_dict(app)
        d["lock"] = lock_info_for_candidate(cid) if app.get("status") in (
            APP_IN_PROGRESS, APP_PENDING_ONBOARD,
        ) else None
        data["applications"].append(d)
    biz_ids = [str(cid)] + [str(a["_id"]) for a in apps]
    logs = list(col("operation_logs").find({
        "biz_type": {"$in": ["candidate", "application"]}, "biz_id": {"$in": biz_ids},
    }).sort("_id", -1).limit(50))
    data["operation_logs"] = [{
        "biz_type": l["biz_type"], "action": l["action"],
        "operator_name": l.get("operator_name", ""), "detail": l.get("detail", ""),
        "created_at": dt(l.get("created_at")),
    } for l in logs]
    write_log("candidate", "view", g.current_user.user_id, g.current_user.name, biz_id=str(cid))
    return ok(data)


def _fill_candidate(payload: dict) -> dict:
    fields = {}
    for field in ["name", "gender", "phone", "email", "city", "tags", "remark", "source"]:
        if field in payload:
            value = payload[field]
            fields[field] = (value or "").strip() if isinstance(value, str) else value
    for jfield in ["education", "work_experience"]:
        if jfield in payload:
            value = payload[jfield]
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except ValueError:
                    raise BizError(BizCode.PARAM_INVALID, f"{jfield} 必须是 JSON 数组")
            fields[jfield] = value or []
    return fields


@bp.post("/api/candidates")
@role_required(HR)
def create_candidate():
    ensure_candidate_indexes()
    payload = request.get_json(silent=True) or {}
    if not (payload.get("name") or "").strip():
        raise BizError(BizCode.PARAM_INVALID, "姓名必填")
    phone = (payload.get("phone") or "").strip()
    email = (payload.get("email") or "").strip()
    duplicates = _find_duplicates(phone, email)
    if duplicates and not payload.get("force"):
        return ok({
            "duplicated": True,
            "duplicates": [_candidate_view(c, mask=False) for c in duplicates],
        })
    doc = {
        "name": "", "gender": "", "phone": "", "email": "", "city": "",
        "education": [], "work_experience": [], "tags": "", "remark": "",
        "source": "manual",
        "owner_id": payload.get("owner_id") or g.current_user.user_id,
        "owner_name": payload.get("owner_name") or g.current_user.name,
    }
    doc.update(_fill_candidate(payload))
    set_identity, _ = identity_update(doc.get("phone"), doc.get("email"), exempt=bool(payload.get("force")))
    doc.update(set_identity)
    doc["version"] = 1
    try:
        c = insert_doc("candidates", doc)
    except DuplicateKeyError:
        # The pre-check can race with another request; the unique identity
        # index is authoritative and the response keeps the existing UX.
        duplicates = _find_duplicates(phone, email)
        return ok({
            "duplicated": True,
            "duplicates": [_candidate_view(d, mask=False) for d in duplicates],
        })
    write_log("candidate", "create", g.current_user.user_id, g.current_user.name,
              biz_id=str(c["_id"]), detail=c.get("name", ""))
    return ok({"duplicated": False, "candidate": _candidate_view(c, mask=False)})


@bp.put("/api/candidates/<int:cid>")
@role_required(HR)
def update_candidate(cid: int):
    ensure_candidate_indexes()
    c = _get_candidate_or_404(cid)
    payload = request.get_json(silent=True) or {}
    if "phone" in payload or "email" in payload:
        duplicates = _find_duplicates(
            payload.get("phone", c.get("phone", "")),
            payload.get("email", c.get("email", "")), exclude_id=cid)
        if duplicates and not payload.get("force"):
            return ok({"duplicated": True,
                       "duplicates": [_candidate_view(d, mask=False) for d in duplicates]})
    fields = _fill_candidate(payload)
    identity_changed = "phone" in payload or "email" in payload or bool(payload.get("force"))
    set_fields = dict(fields)
    unset_fields = {}
    if identity_changed:
        next_phone = fields.get("phone", c.get("phone", ""))
        next_email = fields.get("email", c.get("email", ""))
        identity_set, identity_unset = identity_update(
            next_phone, next_email, exempt=bool(payload.get("force")),
        )
        set_fields.update(identity_set)
        unset_fields.update(identity_unset)
    set_fields["updated_at"] = datetime.now()
    query = {"_id": cid}
    has_version = "version" in payload
    if has_version:
        try:
            query["version"] = int(payload["version"])
        except (TypeError, ValueError):
            raise BizError(BizCode.PARAM_INVALID, "version 必须是整数")
    update = {"$set": set_fields, "$inc": {"version": 1}}
    if unset_fields:
        update["$unset"] = unset_fields
    try:
        updated = col("candidates").find_one_and_update(
            query, update, return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        next_phone = fields.get("phone", c.get("phone", ""))
        next_email = fields.get("email", c.get("email", ""))
        duplicates = _find_duplicates(next_phone, next_email, exclude_id=cid)
        return ok({
            "duplicated": True,
            "duplicates": [_candidate_view(d, mask=False) for d in duplicates],
        })
    if updated is None:
        if get_by_id("candidates", cid) is None:
            raise BizError(BizCode.NOT_FOUND, "候选人不存在")
        if has_version:
            raise BizError(BizCode.CONFLICT, "候选人信息已被其他人修改，请刷新后重试")
        raise BizError(BizCode.CONFLICT, "候选人信息更新失败，请刷新后重试")
    c = updated
    write_log("candidate", "update", g.current_user.user_id, g.current_user.name, biz_id=str(cid))
    return ok({"duplicated": False, "candidate": _candidate_view(c, mask=False)})


@bp.delete("/api/candidates/<int:cid>")
@role_required(HR)
def delete_candidate(cid: int):
    """删除候选人（二次确认）：级联清理所有招聘数据和文件对象。"""
    _get_candidate_or_404(cid)
    if request.args.get("confirm") != "1":
        raise BizError(BizCode.PARAM_INVALID, "删除需要二次确认（confirm=1）")
    return ok(purge_candidate(current_app, cid, g.current_user.user_id, g.current_user.name))


@bp.post("/api/candidates/<int:cid>/applications")
@role_required(HR)
def assign_job(cid: int):
    c = _get_candidate_or_404(cid)
    payload = request.get_json(silent=True) or {}
    job = get_by_id("jobs", int(payload.get("job_id") or 0))
    if job is None:
        raise BizError(BizCode.PARAM_INVALID, "职位不存在")
    app_doc = create_application(c, job, source=payload.get("source", "manual"),
                                 operator_id=g.current_user.user_id,
                                 operator_name=g.current_user.name)
    return ok(application_to_dict(app_doc))


@bp.get("/api/candidates/<int:cid>/applications")
@role_required(*CANDIDATE_READ_ROLES)
def candidate_applications(cid: int):
    _get_candidate_or_404(cid)
    apps = col("applications").find({"candidate_id": cid}).sort("_id", -1)
    return ok([application_to_dict(a) for a in apps])


@bp.get("/api/applications/<int:app_id>/transitions")
@role_required(*CANDIDATE_READ_ROLES)
def application_transitions(app_id: int):
    rows = col("stage_transitions").find({"application_id": app_id}).sort("_id", 1)
    return ok([{
        "from_stage": t.get("from_stage", ""), "to_stage": t.get("to_stage", ""),
        "reason": t.get("reason", ""), "operator_name": t.get("operator_name", ""),
        "created_at": dt(t.get("created_at")),
    } for t in rows])


@bp.post("/api/applications/<int:app_id>/unlock")
@login_required
def unlock_application(app_id: int):
    user = g.current_user
    if "unlock" not in user.roles:
        raise BizError(BizCode.FORBIDDEN, "当前用户无强制解锁权限")
    payload = request.get_json(silent=True) or {}
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise BizError(BizCode.PARAM_INVALID, "强制解锁必须填写原因")
    app = get_by_id("applications", app_id)
    if app is None:
        raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
    locks = list(col("lock_records").find({"application_id": app_id, "released": False}))
    if not locks:
        raise BizError(BizCode.STATE_INVALID, "该应聘记录当前无生效锁定")
    col("lock_records").update_many({"application_id": app_id, "released": False}, {"$set": {
        "released": True, "force_unlocked": True, "unlock_reason": reason,
        "unlock_operator_id": user.user_id, "unlock_operator_name": user.name,
    }})
    write_log("application", "force_unlock", user.user_id, user.name,
              biz_id=str(app_id), detail=reason)
    return ok(None)


# ---------------- 导入导出 ----------------

@bp.get("/api/candidates/import-template")
@role_required(*CANDIDATE_READ_ROLES)
def import_template():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["姓名", "性别", "手机号", "邮箱", "城市", "来源"])
    writer.writerow(["张三", "男", "13800000000", "zhangsan@example.com", "上海", "manual"])
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=candidate_template.csv"})


@bp.post("/api/candidates/import")
@role_required(HR)
def import_candidates():
    ensure_candidate_indexes()
    file = request.files.get("file")
    if file is None or not file.filename:
        raise BizError(BizCode.PARAM_INVALID, "请上传导入文件")
    ext = os.path.splitext(file.filename)[1].lower()
    rows = []
    try:
        if ext == ".csv":
            content = io.TextIOWrapper(file.stream, encoding="utf-8-sig")
            reader = csv.reader(content)
            next(reader, None)
            rows = [r for r in reader if any(x.strip() for x in r)]
        elif ext == ".xlsx":
            import openpyxl

            wb = openpyxl.load_workbook(file.stream, read_only=True)
            sheet = wb.active
            data = list(sheet.iter_rows(values_only=True))
            rows = [[str(v or "") for v in r] for r in data[1:] if any(v for v in r)]
        else:
            raise BizError(BizCode.PARAM_INVALID, "仅支持 CSV/XLSX 导入")
    except BizError:
        raise
    except Exception as e:
        raise BizError(BizCode.PARAM_INVALID, f"文件解析失败: {e}")

    success, duplicates, errors = 0, [], []
    for idx, row in enumerate(rows, start=2):
        row = list(row) + [""] * (6 - len(row))
        name, gender, phone, email, city, source = [x.strip() for x in row[:6]]
        if not name:
            errors.append({"row": idx, "msg": "姓名缺失"})
            continue
        if _find_duplicates(phone, email):
            duplicates.append({"row": idx, "name": name, "phone": phone, "email": email})
            continue
        candidate_doc = {
            "name": name, "gender": gender, "phone": phone, "email": email, "city": city,
            "education": [], "work_experience": [], "tags": "", "remark": "",
            "source": source or "manual",
            "owner_id": g.current_user.user_id, "owner_name": g.current_user.name,
            "version": 1,
        }
        candidate_doc.update(identity_keys(phone, email))
        try:
            insert_doc("candidates", candidate_doc)
        except DuplicateKeyError:
            duplicates.append({"row": idx, "name": name, "phone": phone, "email": email})
            continue
        success += 1
    write_log("candidate", "import", g.current_user.user_id, g.current_user.name,
              detail=f"成功{success} 重复{len(duplicates)} 错误{len(errors)}")
    return ok({"success_count": success, "duplicates": duplicates, "errors": errors})


@bp.get("/api/candidates/export")
@role_required(HR)
def export_candidates():
    args = request.args
    query = {}
    if args.get("keyword"):
        kw = args["keyword"]
        query["$or"] = [{"name": {"$regex": kw}}, {"phone": {"$regex": kw}}]
    items = list(col("candidates").find(query).sort("_id", 1))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["姓名", "性别", "手机号", "邮箱", "城市", "来源", "创建时间"])
    for c in items:
        writer.writerow([c.get("name", ""), c.get("gender", ""), c.get("phone", ""),
                         c.get("email", ""), c.get("city", ""), c.get("source", ""),
                         dt(c.get("created_at"))])
    col("export_logs").insert_one({
        "exporter_id": g.current_user.user_id, "exporter_name": g.current_user.name,
        "scene": "candidates", "conditions": json.dumps(dict(args), ensure_ascii=False),
        "row_count": len(items), "created_at": __import__("datetime").datetime.now(),
    })
    write_log("export", "candidates", g.current_user.user_id, g.current_user.name,
              detail=f"rows={len(items)}")
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=candidates.csv"})


# ---------------- 简历上传与解析 ----------------

@bp.post("/api/resume/parse-upload")
@role_required(*RESUME_ACCESS_ROLES)
def resume_parse_upload():
    """解析尚未关联候选人的简历，供新增候选人表单预填基础信息。"""
    file = request.files.get("file")
    if file is None or not file.filename:
        raise BizError(BizCode.PARAM_INVALID, "请上传简历文件")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".pdf", ".docx"}:
        raise BizError(BizCode.PARAM_INVALID, "新增候选人自动解析目前仅支持 PDF/DOCX")

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="resume-parse-", suffix=ext, delete=False) as temp:
            temp_path = temp.name
        file.save(temp_path)
        if os.path.getsize(temp_path) > 10 * 1024 * 1024:
            raise BizError(BizCode.PARAM_INVALID, "简历文件不能超过 10MB")
        fields, status = parse_resume_file(temp_path, file.filename)
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass

    return ok({
        "file_name": secure_filename(file.filename) or "resume",
        "parse_status": status,
        "fields": fields,
        "message": "解析成功，请核对并修改" if status == "system" else "未能识别出基础信息，请人工填写",
    })

@bp.post("/api/resume/upload")
@role_required(*RESUME_ACCESS_ROLES)
def resume_upload():
    file = request.files.get("file")
    if file is None or not file.filename:
        raise BizError(BizCode.PARAM_INVALID, "请上传简历文件")
    candidate_id = int(request.form.get("candidate_id") or 0)
    if candidate_id:
        _get_candidate_or_404(candidate_id)
    try:
        meta = save_uploaded_file(
            current_app, file, biz_type="resume",
            operator_id=g.current_user.user_id, operator_name=g.current_user.name,
        )
    except MongoUnavailable:
        raise BizError(5001, "文件服务不可用：MongoDB 未连接", http_status=200)
    except StorageError as e:
        raise BizError(BizCode.PARAM_INVALID, str(e))
    att = insert_doc("attachments", {
        "candidate_id": candidate_id, "file_name": meta["originalName"],
        "file_path": meta["objectKey"], "file_id": meta["id"],
        "file_type": "resume", "parse_status": "",
    })
    if candidate_id:
        from bson import ObjectId

        col("files").update_one(
            {"_id": ObjectId(meta["id"])},
            {"$set": {"candidate_id": candidate_id}},
        )
    return ok({"attachment_id": att["_id"], "file_name": att["file_name"], "file_id": meta["id"]})


@bp.post("/api/resume/parse")
@role_required(*RESUME_ACCESS_ROLES)
def resume_parse():
    payload = request.get_json(silent=True) or {}
    att = get_by_id("attachments", int(payload.get("attachment_id") or 0))
    if att is None:
        raise BizError(BizCode.NOT_FOUND, "附件不存在")
    local_path, is_tmp = resolve_local(current_app, att.get("file_path", ""))
    try:
        fields, status = parse_resume_file(local_path, att.get("file_name", ""))
    finally:
        if is_tmp:
            from common.file_service import get_storage

            get_storage(current_app).cleanup_local(local_path, att.get("file_path", ""))
    update_doc("attachments", att["_id"], {"parse_status": status})
    if status == "failed":
        return ok({
            "parse_status": status, "fields": fields,
            "message": "简历解析失败（图片简历暂不支持自动识别），请人工录入",
        })
    return ok({"parse_status": status, "fields": fields, "message": "解析成功，请核对后保存"})


@bp.get("/api/attachments/<int:att_id>")
@role_required(*RESUME_ACCESS_ROLES)
def download_attachment(att_id: int):
    att = get_by_id("attachments", att_id)
    if att is None:
        raise BizError(BizCode.NOT_FOUND, "附件不存在")
    try:
        data = read_file_bytes(current_app, att.get("file_path", ""))
    except StorageError as e:
        raise BizError(BizCode.NOT_FOUND, str(e))
    write_log("attachment", "download", g.current_user.user_id, g.current_user.name,
              biz_id=str(att_id), detail=f"candidate={att.get('candidate_id', '')}; file={att.get('file_name', '')}")
    return Response(data.getvalue(), mimetype="application/octet-stream",
                    headers={"Content-Disposition":
                             f"inline; filename*=UTF-8''{att.get('file_name', '')}"})
