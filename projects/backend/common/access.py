"""统一的业务权限与敏感数据访问策略。

权限判断集中在这里，避免各模块通过 ``mask=0`` 或仅登录态绕过个人信息保护。
第一版仍以 HR 为候选人主数据的完整访问者；其他流程角色只能访问脱敏数据，
并按职责访问简历或 Offer 文件。
"""
from flask import g

from common.db import col
from common.errors import BizError
from common.response import BizCode
from common.roles import (
    ALL_ROLES,
    BUSINESS_SCREENER,
    CHAIRMAN,
    GM,
    HR,
    INTERVIEWER,
    OFFER_SENDER,
    ORG_APPROVER,
    SSC,
)


CANDIDATE_READ_ROLES = tuple(ALL_ROLES)
PII_ROLES = (HR,)
RESUME_ACCESS_ROLES = (HR, BUSINESS_SCREENER, INTERVIEWER)
OFFER_FILE_ACCESS_ROLES = (HR, OFFER_SENDER, SSC, ORG_APPROVER, GM, CHAIRMAN)
REPORT_ACCESS_ROLES = (HR,)
APPROVAL_ACCESS_ROLES = (HR, ORG_APPROVER, GM, CHAIRMAN, OFFER_SENDER)
# Offer 列表用于跨角色协作，保持历史行为允许所有业务角色读取；
# Offer 文件的预览/下载仍由 OFFER_FILE_ACCESS_ROLES 严格控制。
OFFER_READ_ROLES = tuple(ALL_ROLES)


def current_role() -> str:
    user = getattr(g, "current_user", None)
    return getattr(user, "role", "")


def has_role(*roles: str) -> bool:
    return current_role() in roles


def require_roles(*roles: str) -> None:
    if not has_role(*roles):
        raise BizError(BizCode.FORBIDDEN, "当前角色无权访问该数据")


def can_view_pii() -> bool:
    """只有明确授权的角色才返回手机号、邮箱原文。"""
    return has_role(*PII_ROLES)


def candidate_lock_owner(candidate_id: int):
    """Return the current lock and its owning HR, if the candidate is locked."""
    from common.flow import active_lock_for_candidate, active_lock_for_candidate_identity

    candidate = col("candidates").find_one({"_id": candidate_id}) or {}
    lock = active_lock_for_candidate(candidate_id)
    if not lock:
        if candidate:
            lock = active_lock_for_candidate_identity(candidate)
    if lock:
        application = col("applications").find_one(
            {"_id": lock.get("application_id")},
            {"owner_id": 1, "owner_name": 1},
        ) or {}
        owner_id = (
            lock.get("owner_id", "")
            or application.get("owner_id", "")
            or candidate.get("owner_id", "")
        )
        owner_name = (
            lock.get("owner_name", "")
            or application.get("owner_name", "")
            or candidate.get("owner_name", "")
        )
        return {**lock, "owner_id": owner_id, "owner_name": owner_name}

    # A newly uploaded candidate may not have an application or stage lock yet.
    # The HR who created the candidate still owns the record, so another HR
    # must not be able to edit, assign, or advance it through a direct request.
    if candidate.get("owner_id"):
        return {
            "candidate_id": candidate_id,
            "stage_key": "candidate_owner",
            "owner_id": candidate.get("owner_id", ""),
            "owner_name": candidate.get("owner_name", ""),
        }
    if not lock:
        return None


def require_candidate_lock_owner(candidate_id: int) -> None:
    """Prevent another HR from operating a candidate during the lock period.

    Business interviewers and designated business screeners still need to work
    on the application, so this ownership rule applies only to HR actions.
    Super admins remain able to operate across owners.
    """
    user = getattr(g, "current_user", None)
    if user is None or user.role != HR:
        return
    lock = candidate_lock_owner(candidate_id)
    if lock and lock.get("owner_id") and lock["owner_id"] != user.user_id:
        owner = lock.get("owner_name") or lock.get("owner_id")
        raise BizError(BizCode.FORBIDDEN, f"候选人当前由 {owner} 锁定，只有锁定该候选人的 HR 可以操作")


def mask_phone(value: str) -> str:
    value = value or ""
    return value[:3] + "****" + value[-4:] if len(value) >= 7 else value


def mask_email(value: str) -> str:
    value = value or ""
    if "@" not in value or len(value) < 6:
        return value
    head, tail = value.split("@", 1)
    return head[:2] + "***@" + tail


def redact_candidate(candidate: dict, include_pii: bool = False) -> dict:
    """返回候选人基础信息视图，默认强制脱敏。"""
    from common.db import dt

    show_pii = include_pii and can_view_pii()
    return {
        "id": candidate["_id"],
        "name": candidate.get("name", ""),
        "gender": candidate.get("gender", ""),
        "age": candidate.get("age"),
        "highest_education": candidate.get("highest_education", ""),
        "major": candidate.get("major", ""),
        "phone": candidate.get("phone", "") if show_pii else mask_phone(candidate.get("phone", "")),
        "email": candidate.get("email", "") if show_pii else mask_email(candidate.get("email", "")),
        "city": candidate.get("city", ""),
        "tags": candidate.get("tags", ""),
        "remark": candidate.get("remark", ""),
        "source": candidate.get("source", ""),
        "owner_id": candidate.get("owner_id", ""),
        "owner_name": candidate.get("owner_name", ""),
        "created_at": dt(candidate.get("created_at")),
    }


def file_access_allowed(file_doc: dict, action: str = "read") -> bool:
    """判断通用文件接口是否可访问某类文件。

    文件接口不能只依赖上传者判断：上传者可能是公开投递或已离职账号，
    也不能让任意登录角色通过文件 ID 读取简历/Offer。
    """
    role = current_role()
    biz_type = file_doc.get("bizType", file_doc.get("biz_type", "general"))
    if action == "delete":
        return role == HR
    if role == HR:
        return True
    if biz_type == "resume":
        # 通用文件 ID 接口没有候选人上下文，非 HR 只能通过候选人附件接口访问，
        # 避免枚举文件 ID 读取其他候选人的简历。
        return role == HR
    if biz_type == "offer":
        return role in OFFER_FILE_ACCESS_ROLES
    return False
