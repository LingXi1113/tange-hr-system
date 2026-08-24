"""登录态与角色校验装饰器。"""
from functools import wraps

from flask import current_app, g, request, session

from platform_identity import get_identity  # noqa: A004  (项目内 platform 包)
from common.auth_token import parse_token
from common.errors import BizError
from common.response import BizCode


def _load_current_user():
    # 优先使用 X-Auth-Token（内嵌 iframe 场景第三方 Cookie 不可靠），其次 session
    token = request.headers.get("X-Auth-Token", "").strip()
    user_id = parse_token(token) if token else None
    if not user_id:
        user_id = session.get("user_id")
    if not user_id:
        return None
    identity = get_identity(current_app)
    return identity.get_user(user_id)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _load_current_user()
        if user is None:
            raise BizError(401, "未登录", http_status=401)
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def role_required(*roles):
    """要求当前用户主角色在 roles 中。"""

    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if g.current_user.role not in roles:
                raise BizError(BizCode.FORBIDDEN, "当前角色无权限执行该操作")
            return fn(*args, **kwargs)

        return wrapper

    return decorator
