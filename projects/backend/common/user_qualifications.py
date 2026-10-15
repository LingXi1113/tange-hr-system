"""平台账号的本地附加业务资格。主角色仍由身份平台提供。"""
from dataclasses import replace

from common.db import col
from common.roles import INTERVIEWER


def with_local_qualifications(user):
    """返回叠加本地资格后的用户副本，不修改身份提供方的原始对象。"""
    if user is None:
        return None
    roles = list(dict.fromkeys([user.role, *(user.roles or [])]))
    qualification = col("user_qualifications").find_one({"_id": user.user_id}) or {}
    if qualification.get("interviewer_enabled") and INTERVIEWER not in roles:
        roles.append(INTERVIEWER)
    return replace(user, roles=roles)


def has_effective_role(user, *roles: str) -> bool:
    if user is None:
        return False
    effective = {user.role, *(user.roles or [])}
    return bool(effective.intersection(roles))
