"""职位管理（MongoDB 版）：CRUD/状态机/复制/公开页/免登投递/导出。"""
import csv
import io
import json
import re
import uuid

from flask import Blueprint, Response, current_app, g, request
from pymongo.errors import DuplicateKeyError

from common.candidate_identity import ensure_candidate_indexes, identity_keys
from common.db import col, get_by_id, insert_doc, paginate, update_doc, dt
from common.decorators import login_required, role_required
from common.errors import BizError
from common.file_service import save_uploaded_file
from common.flow import create_application, application_to_dict
from common.logstore import write_log
from common.mongo import MongoUnavailable
from common.response import BizCode, ok, paged
from common.resume_service import auto_parse_attachment
from common.roles import HR
from common.stages import INTERVIEW_ROUNDS
from common.status import (
    JOB_CLOSED, JOB_DRAFT, JOB_FLOW, JOB_PAUSED, JOB_PENDING, JOB_RECRUITING,
)
from common.storage import StorageError

bp = Blueprint("job_api", __name__)

JOB_ACTION = {
    "submit": JOB_PENDING,
    "publish": JOB_RECRUITING,
    "pause": JOB_PAUSED,
    "resume": JOB_RECRUITING,
    "close": JOB_CLOSED,
}
RESUME_EXTS = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"}


def _get_or_404(job_id: int) -> dict:
    job = get_by_id("jobs", job_id)
    if job is None:
        raise BizError(BizCode.NOT_FOUND, "职位不存在")
    return job


def _job_view(job: dict) -> dict:
    return {
        "id": job["_id"], "code": job.get("code", ""), "name": job.get("name", ""),
        "dept_id": job.get("dept_id", ""), "dept_name": job.get("dept_name", ""),
        "location": job.get("location", ""), "job_type": job.get("job_type", ""),
        "level": job.get("level", ""), "report_to": job.get("report_to", ""),
        "headcount": job.get("headcount", 1), "salary_range": job.get("salary_range", ""),
        "description": job.get("description", ""), "qualification": job.get("qualification", ""),
        "skill_tags": job.get("skill_tags", ""), "template_id": job.get("template_id"),
        "channels": job.get("channels", ""), "status": job.get("status", JOB_DRAFT),
        "interview_rounds": list(job.get("interview_rounds") or ["一面"]),
        "requirement_id": job.get("requirement_id"),
        "owner_id": job.get("owner_id", ""), "owner_name": job.get("owner_name", ""),
        "public_token": job.get("public_token", ""),
        "public_url": f"/#/public/job/{job['public_token']}" if job.get("public_token") else "",
        "created_at": dt(job.get("created_at")), "updated_at": dt(job.get("updated_at")),
    }


def _job_with_configs(job: dict) -> dict:
    data = _job_view(job)
    data["stage_configs"] = list(job.get("stage_configs", []))
    data["application_count"] = col("applications").count_documents({"job_id": job["_id"]})
    return data


def _fill(job: dict, payload: dict) -> dict:
    fields = {}
    for field in ["name", "dept_id", "dept_name", "location", "job_type", "level",
                  "report_to", "salary_range", "description", "qualification",
                  "skill_tags", "channels", "owner_id", "owner_name"]:
        if field in payload:
            fields[field] = payload[field] or ""
    if "code" in payload and payload["code"]:
        code = payload["code"].strip()
        exists = col("jobs").find_one({"code": code, "_id": {"$ne": job.get("_id")}})
        if exists:
            raise BizError(BizCode.DUPLICATED, f"职位编码已存在: {code}")
        fields["code"] = code
    if "headcount" in payload:
        try:
            fields["headcount"] = max(int(payload["headcount"]), 1)
        except (TypeError, ValueError):
            raise BizError(BizCode.PARAM_INVALID, "招聘人数必须是整数")
    if "template_id" in payload:
        fields["template_id"] = int(payload["template_id"]) if payload["template_id"] else None
    if "requirement_id" in payload:
        rid = payload["requirement_id"]
        if rid:
            if get_by_id("requirements", int(rid)) is None:
                raise BizError(BizCode.NOT_FOUND, "关联招聘需求不存在")
            rid = int(rid)
        fields["requirement_id"] = rid or None
    if "interview_rounds" in payload:
        rounds = payload.get("interview_rounds") or []
        if not isinstance(rounds, list):
            raise BizError(BizCode.PARAM_INVALID, "面试轮次必须是数组")
        rounds = list(dict.fromkeys(str(item).strip() for item in rounds if str(item).strip()))
        if not rounds or any(item not in INTERVIEW_ROUNDS for item in rounds):
            raise BizError(BizCode.PARAM_INVALID, f"面试轮次必须从以下选项中选择: {'/'.join(INTERVIEW_ROUNDS)}")
        fields["interview_rounds"] = rounds
    configs = payload.get("stage_configs")
    if configs is not None:
        fields["stage_configs"] = [{
            "stage_key": cfg["stage_key"],
            "enabled": bool(cfg.get("enabled")),
            "required": bool(cfg.get("required")),
            "after_key": cfg.get("after_key", ""),
        } for cfg in configs if cfg.get("stage_key")]
    job.update(fields)
    return fields


@bp.get("/api/jobs")
@login_required
def list_jobs():
    args = request.args
    query = {}
    if args.get("status"):
        query["status"] = args["status"]
    if args.get("dept_id"):
        query["dept_id"] = args["dept_id"]
    if args.get("job_type"):
        query["job_type"] = args["job_type"]
    if args.get("owner_id"):
        query["owner_id"] = args["owner_id"]
    if args.get("keyword"):
        kw = args["keyword"]
        query["$or"] = [{"name": {"$regex": kw}}, {"code": {"$regex": kw}}]
    items = col("jobs").find(query).sort("_id", -1)
    page = max(int(args.get("page", 1)), 1)
    page_size = min(max(int(args.get("page_size", 10)), 1), 100)
    sliced, total, page, page_size = paginate(items, page, page_size)
    return paged([_job_view(j) for j in sliced], total, page, page_size)


@bp.get("/api/jobs/export")
@role_required(HR)
def export_jobs():
    items = list(col("jobs").find().sort("_id", 1))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["编码", "职位名称", "部门", "状态", "招聘人数", "负责人", "创建时间"])
    for j in items:
        writer.writerow([j.get("code", ""), j.get("name", ""), j.get("dept_name", ""),
                         j.get("status", ""), j.get("headcount", 0), j.get("owner_name", ""),
                         dt(j.get("created_at"))])
    col("export_logs").insert_one({
        "exporter_id": g.current_user.user_id, "exporter_name": g.current_user.name,
        "scene": "jobs", "conditions": json.dumps(dict(request.args), ensure_ascii=False),
        "row_count": len(items), "created_at": __import__("datetime").datetime.now(),
    })
    write_log("export", "jobs", g.current_user.user_id, g.current_user.name,
              detail=f"rows={len(items)}")
    return Response(
        "\ufeff" + buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobs.csv"},
    )


@bp.get("/api/jobs/<int:job_id>")
@login_required
def get_job(job_id: int):
    return ok(_job_with_configs(_get_or_404(job_id)))


@bp.get("/api/jobs/<int:job_id>/applications")
@login_required
def job_applications(job_id: int):
    _get_or_404(job_id)
    apps = col("applications").find({"job_id": job_id}).sort("_id", -1)
    return ok([application_to_dict(a) for a in apps])


@bp.post("/api/jobs")
@role_required(HR)
def create_job():
    payload = request.get_json(silent=True) or {}
    if not (payload.get("name") or "").strip():
        raise BizError(BizCode.PARAM_INVALID, "职位名称必填")
    job = {
        "code": (payload.get("code") or f"JOB-{uuid.uuid4().hex[:8].upper()}").strip(),
        "status": JOB_DRAFT,
        "owner_id": payload.get("owner_id") or g.current_user.user_id,
        "owner_name": payload.get("owner_name") or g.current_user.name,
        "public_token": uuid.uuid4().hex,
        "name": "", "dept_id": "", "dept_name": "", "location": "",
        "job_type": "full_time", "level": "", "report_to": "", "headcount": 1,
        "salary_range": "", "description": "", "qualification": "",
        "skill_tags": "", "template_id": None, "channels": "", "requirement_id": None,
        "stage_configs": [],
    }
    if col("jobs").find_one({"code": job["code"]}):
        raise BizError(BizCode.DUPLICATED, f"职位编码已存在: {job['code']}")
    _fill(job, payload)
    doc = insert_doc("jobs", job)
    write_log("job", "create", g.current_user.user_id, g.current_user.name,
              biz_id=str(doc["_id"]), detail=doc.get("name", ""))
    return ok(_job_with_configs(doc))


@bp.put("/api/jobs/<int:job_id>")
@role_required(HR)
def update_job(job_id: int):
    job = _get_or_404(job_id)
    if job["status"] == JOB_CLOSED:
        raise BizError(BizCode.STATE_INVALID, "已关闭职位不能编辑")
    fields = _fill(job, request.get_json(silent=True) or {})
    update_doc("jobs", job_id, fields)
    write_log("job", "update", g.current_user.user_id, g.current_user.name, biz_id=str(job_id))
    return ok(_job_with_configs(job))


@bp.post("/api/jobs/<int:job_id>/copy")
@role_required(HR)
def copy_job(job_id: int):
    src = _get_or_404(job_id)
    doc = {k: src.get(k) for k in
           ["name", "dept_id", "dept_name", "location", "job_type", "level", "report_to",
            "headcount", "salary_range", "description", "qualification", "skill_tags",
           "template_id", "channels", "requirement_id", "stage_configs", "interview_rounds"]}
    doc.update({
        "code": f"JOB-{uuid.uuid4().hex[:8].upper()}",
        "name": f"{src.get('name', '')}（副本）",
        "status": JOB_DRAFT,
        "owner_id": g.current_user.user_id,
        "owner_name": g.current_user.name,
        "public_token": uuid.uuid4().hex,
        "stage_configs": [dict(c) for c in src.get("stage_configs", [])],
    })
    new_job = insert_doc("jobs", doc)
    write_log("job", "copy", g.current_user.user_id, g.current_user.name,
              biz_id=str(new_job["_id"]), detail=f"from {job_id}")
    return ok(_job_with_configs(new_job))


@bp.post("/api/jobs/<int:job_id>/status")
@role_required(HR)
def change_job_status(job_id: int):
    job = _get_or_404(job_id)
    payload = request.get_json(silent=True) or {}
    action = payload.get("action", "")
    target = JOB_ACTION.get(action)
    if target is None:
        raise BizError(BizCode.PARAM_INVALID, f"未知操作: {action}")
    if target not in JOB_FLOW.get(job["status"], []):
        raise BizError(BizCode.STATE_INVALID, f"当前状态 {job['status']} 不允许执行 {action}")
    update_doc("jobs", job_id, {"status": target})
    job["status"] = target
    write_log("job", action, g.current_user.user_id, g.current_user.name,
              biz_id=str(job_id), detail=f"状态变更为 {target}")
    return ok(_job_view(job))


# ---------------- 公开页（免鉴权） ----------------

public_bp = Blueprint("job_public_api", __name__, url_prefix="/api/public/jobs")


@public_bp.get("/<token>")
def public_job(token: str):
    job = col("jobs").find_one({"public_token": token})
    if job is None:
        raise BizError(BizCode.NOT_FOUND, "职位不存在或链接已失效")
    data = {
        "name": job.get("name", ""), "location": job.get("location", ""),
        "job_type": job.get("job_type", ""), "level": job.get("level", ""),
        "headcount": job.get("headcount", 0), "salary_range": job.get("salary_range", ""),
        "description": job.get("description", ""), "qualification": job.get("qualification", ""),
        "skill_tags": job.get("skill_tags", ""), "dept_name": job.get("dept_name", ""),
        "status": job.get("status", ""),
        "accepting": job.get("status") == JOB_RECRUITING,
    }
    return ok(data)


@public_bp.post("/<token>/apply")
def public_apply(token: str):
    ensure_candidate_indexes()
    job = col("jobs").find_one({"public_token": token})
    if job is None:
        raise BizError(BizCode.NOT_FOUND, "职位不存在或链接已失效")
    form = request.form
    name = (form.get("name") or "").strip()
    phone = (form.get("phone") or "").strip()
    email = (form.get("email") or "").strip()
    privacy = form.get("privacy_agreed") in ("1", "true", "True")
    if not name:
        raise BizError(BizCode.PARAM_INVALID, "姓名必填")
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise BizError(BizCode.PARAM_INVALID, "手机号格式不正确")
    if email and not re.fullmatch(r"[\w.+-]+@[\w-]+\.[\w.]+", email):
        raise BizError(BizCode.PARAM_INVALID, "邮箱格式不正确")
    if not privacy:
        raise BizError(BizCode.PARAM_INVALID, "请先勾选隐私授权")

    # 查重：按手机号/邮箱匹配已有候选人，命中复用主档
    candidate = None
    if phone:
        phone_key = identity_keys(phone, {}).get("phone_key")
        candidate = col("candidates").find_one({
            "$or": [{"phone_key": phone_key}, {"phone": phone}],
        })
    if candidate is None and email:
        email_key = identity_keys({}, email).get("email_key")
        candidate = col("candidates").find_one({
            "$or": [{"email_key": email_key}, {"email": email}],
        })
    if candidate is None:
        candidate_doc = {
            "name": name, "gender": "", "phone": phone, "email": email,
            "city": (form.get("city") or "").strip(),
            "education": [], "work_experience": [], "tags": "",
            "remark": "公开页投递", "source": "website",
            "owner_id": "", "owner_name": "", "version": 1,
        }
        candidate_doc.update(identity_keys(phone, email))
        try:
            candidate = insert_doc("candidates", candidate_doc)
        except DuplicateKeyError:
            # Another public submission won the identity race; reuse it.
            candidate = None
            if phone:
                candidate = col("candidates").find_one({"phone_key": identity_keys(phone, {}).get("phone_key")})
            if candidate is None and email:
                candidate = col("candidates").find_one({"email_key": identity_keys({}, email).get("email_key")})
            if candidate is None:
                raise
    write_log("candidate", "public_apply", "", name, biz_id=str(candidate["_id"]),
              detail=f"投递职位 {job.get('name', '')}")

    app_doc = create_application(
        candidate, job, source="website", operator_id="", operator_name="公开投递",
        extra={
            "expected_salary": (form.get("expected_salary") or "").strip(),
            "onboard_time": (form.get("onboard_time") or "").strip(),
        },
    )

    # 简历附件（可选）：统一文件服务（OSS + MongoDB 元数据）
    file = request.files.get("resume")
    resume_parse_status = ""
    resume_fields = {}
    if file and file.filename:
        try:
            meta = save_uploaded_file(
                current_app, file, biz_type="resume",
                operator_id="", operator_name="公开投递",
                allowed_exts=RESUME_EXTS,
            )
        except MongoUnavailable:
            raise BizError(5001, "文件服务不可用：MongoDB 未连接")
        except StorageError as e:
            raise BizError(BizCode.PARAM_INVALID, str(e))
        attachment = insert_doc("attachments", {
            "candidate_id": candidate["_id"], "file_name": meta["originalName"],
            "file_path": meta["objectKey"], "file_id": meta["id"],
            "file_type": "resume", "parse_status": "pending",
        })
        from bson import ObjectId

        col("files").update_one(
            {"_id": ObjectId(meta["id"])},
            {"$set": {"candidate_id": candidate["_id"]}},
        )
        # 公开投递已落库后自动解析；解析失败不影响投递结果。
        resume_fields, resume_parse_status = auto_parse_attachment(
            current_app, attachment["_id"], candidate["_id"],
        )
    return ok({
        "candidate_id": candidate["_id"], "application_id": app_doc["_id"],
        "resume_parse_status": resume_parse_status,
        "resume_fields": resume_fields,
    })
