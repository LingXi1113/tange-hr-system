"""平台数据接口：部门树、成员搜索（数据来自平台身份提供方）。"""
from flask import Blueprint, current_app, request

from common.decorators import login_required
from common.response import ok
from common.roles import ROLE_NAMES
from platform_identity import get_identity

bp = Blueprint("platform_api", __name__, url_prefix="/api/platform")


@bp.get("/departments")
@login_required
def departments():
    identity = get_identity(current_app)
    return ok(identity.get_department_tree())


@bp.get("/users")
@login_required
def users():
    identity = get_identity(current_app)
    keyword = request.args.get("keyword", "")
    data = [
        {**u.to_dict(), "role_name": ROLE_NAMES.get(u.role, u.role)}
        for u in identity.list_users(keyword)
    ]
    return ok(data)
