"""平台身份抽象层。

业务代码只依赖 PlatformIdentity 接口；当前环境使用 MockPlatformProvider。
生产环境接入即先平台时，实现 OpenPlatformIdentityProvider（基于
jahead-open-platform SDK 免登 code 换身份）并在 get_identity() 中切换即可，
业务代码无需改动。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PlatformUser:
    """平台用户（身份由即先平台提供，本地仅存 ID 与名称快照）。"""

    user_id: str
    name: str
    role: str  # 主角色，见 common/roles.py
    roles: list[str] = field(default_factory=list)
    dept_id: str = ""
    dept_name: str = ""
    company_id: str = "company-demo"

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "role": self.role,
            "roles": list(self.roles),
            "dept_id": self.dept_id,
            "dept_name": self.dept_name,
            "company_id": self.company_id,
        }


class PlatformIdentity(ABC):
    """平台身份提供方接口（用户/部门来自即先平台）。"""

    provider_name: str = "abstract"

    @abstractmethod
    def get_user(self, user_id: str) -> Optional[PlatformUser]:
        """按 ID 获取用户，不存在返回 None。"""

    @abstractmethod
    def list_users(self, keyword: str = "") -> list[PlatformUser]:
        """成员搜索（审批人配置、负责人选择用）。"""

    @abstractmethod
    def get_department_tree(self) -> list[dict]:
        """部门树。"""


def get_identity(app) -> PlatformIdentity:
    """根据配置返回平台身份提供方实例（每个 app 单例）。"""
    provider = app.config.get("PLATFORM_PROVIDER", "mock")
    if provider == "mock":
        from .mock_provider import MockPlatformProvider

        return MockPlatformProvider()
    if provider == "open_platform":
        # 生产切换点：实现 OpenPlatformIdentityProvider 后在此返回。
        raise NotImplementedError(
            "open_platform provider 尚未接入（缺少 SDK 安装包与 app_id/app_secret 凭据），"
            "请使用 HRATS_PLATFORM_PROVIDER=mock"
        )
    raise ValueError(f"未知平台身份提供方: {provider}")
