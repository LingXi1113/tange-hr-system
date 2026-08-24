"""Mock 平台身份提供方。

模拟即先平台的用户与部门数据，覆盖 8 类流程参与角色，用于当前环境的
开发与演示。生产环境切换为 OpenPlatformIdentityProvider 后本模块不再加载。
"""
from __future__ import annotations

from typing import Optional

from .identity import PlatformIdentity, PlatformUser

_COMPANY = "company-demo"

_DEPARTMENTS = [
    {"dept_id": "dept-tech", "name": "技术中心", "parent_id": ""},
    {"dept_id": "dept-hr", "name": "人力资源部", "parent_id": ""},
    {"dept_id": "dept-backend", "name": "后端研发组", "parent_id": "dept-tech"},
    {"dept_id": "dept-frontend", "name": "前端研发组", "parent_id": "dept-tech"},
]

_USERS: list[PlatformUser] = [
    PlatformUser("hr-001", "张薇", "hr", ["hr"], "dept-hr", "人力资源部", _COMPANY),
    PlatformUser("hr-002", "李娜", "hr", ["hr", "unlock"], "dept-hr", "人力资源部", _COMPANY),
    PlatformUser("screen-001", "王强", "business_screener", ["business_screener"], "dept-backend", "后端研发组", _COMPANY),
    PlatformUser("interviewer-001", "刘洋", "interviewer", ["interviewer"], "dept-tech", "技术中心", _COMPANY),
    PlatformUser("org-001", "陈静", "org_approver", ["org_approver"], "dept-hr", "人力资源部", _COMPANY),
    PlatformUser("gm-001", "赵敏", "gm", ["gm"], "dept-hr", "人力资源部", _COMPANY),
    PlatformUser("chairman-001", "孙浩", "chairman", ["chairman"], "dept-hr", "人力资源部", _COMPANY),
    PlatformUser("offer-001", "周婷", "offer_sender", ["offer_sender"], "dept-hr", "人力资源部", _COMPANY),
    PlatformUser("ssc-001", "吴迪", "ssc", ["ssc"], "dept-hr", "人力资源部", _COMPANY),
]


class MockPlatformProvider(PlatformIdentity):
    provider_name = "mock"

    def __init__(self) -> None:
        self._users = {u.user_id: u for u in _USERS}

    def get_user(self, user_id: str) -> Optional[PlatformUser]:
        return self._users.get(user_id)

    def list_users(self, keyword: str = "") -> list[PlatformUser]:
        users = list(self._users.values())
        if keyword:
            kw = keyword.strip()
            users = [u for u in users if kw in u.name or kw in u.user_id]
        return users

    def get_department_tree(self) -> list[dict]:
        return [dict(d) for d in _DEPARTMENTS]
