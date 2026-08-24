"""登录态与会话（P0：Mock 平台登录/角色切换）。"""
from flask import Blueprint, current_app, g, request, session

from common.auth_token import generate_token
from common.decorators import login_required
from common.errors import BizError
from common.response import BizCode, ok
from common.roles import ROLE_NAMES
from common.logstore import write_log
from platform_identity import get_identity

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _mock_auth_enabled() -> bool:
    return bool(current_app.config.get("ENABLE_MOCK_AUTH"))


def _user_payload(identity, user) -> dict:
    data = user.to_dict()
    data["role_name"] = ROLE_NAMES.get(user.role, user.role)
    data["mock_mode"] = identity.provider_name == "mock"
    if _mock_auth_enabled():
        data["switchable_users"] = [
            {"user_id": u.user_id, "name": u.name, "role": u.role,
             "role_name": ROLE_NAMES.get(u.role, u.role)}
            for u in identity.list_users()
        ]
    return data


@bp.get("/me")
@login_required
def me():
    identity = get_identity(current_app)
    return ok(_user_payload(identity, g.current_user))


@bp.get("/mock-users")
def mock_users():
    """登录页可选用户列表（仅 Mock 环境提供）。"""
    if not _mock_auth_enabled():
        return ok({"enabled": False, "users": []})
    identity = get_identity(current_app)
    return ok({
        "enabled": True,
        "users": [
            {"user_id": u.user_id, "name": u.name, "role": u.role,
             "role_name": ROLE_NAMES.get(u.role, u.role), "dept_name": u.dept_name}
            for u in identity.list_users()
        ],
    })


@bp.post("/mock-login")
def mock_login():
    """演示环境登录：选择 Mock 平台用户建立会话。"""
    if not _mock_auth_enabled():
        raise BizError(BizCode.FORBIDDEN, "当前环境未启用 Mock 登录")
    payload = request.get_json(silent=True) or {}
    user_id = (payload.get("user_id") or "").strip()
    identity = get_identity(current_app)
    user = identity.get_user(user_id) if user_id else None
    if user is None:
        raise BizError(BizCode.PARAM_INVALID, "用户不存在")
    session["user_id"] = user.user_id
    write_log("auth", "mock_login", user.user_id, user.name, detail="Mock 登录")
    data = _user_payload(identity, user)
    data["token"] = generate_token(user.user_id)
    return ok(data)


@bp.post("/switch-user")
@login_required
def switch_user():
    """演示环境角色切换（生产关闭 ENABLE_MOCK_AUTH 后不可用）。"""
    if not _mock_auth_enabled():
        raise BizError(BizCode.FORBIDDEN, "当前环境未启用角色切换")
    payload = request.get_json(silent=True) or {}
    user_id = (payload.get("user_id") or "").strip()
    identity = get_identity(current_app)
    user = identity.get_user(user_id) if user_id else None
    if user is None:
        raise BizError(BizCode.PARAM_INVALID, "用户不存在")
    session["user_id"] = user.user_id
    write_log("auth", "switch_user", user.user_id, user.name, detail="切换角色")
    data = _user_payload(identity, user)
    data["token"] = generate_token(user.user_id)
    return ok(data)


@bp.post("/logout")
def logout():
    session.clear()
    return ok(None)
