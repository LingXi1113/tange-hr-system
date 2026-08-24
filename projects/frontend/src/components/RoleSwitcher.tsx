import { Select, Tag } from 'antd';

import { isRoleSwitcherEnabled } from '@/config/app';
import { switchUser, useCurrentUser } from '@/services/user';

/**
 * 开发环境角色切换器：在 Mock 平台用户之间切换，便于验证角色相关逻辑。
 * 生产构建（import.meta.env.DEV=false）自动不渲染。
 */
export function RoleSwitcher() {
  const { user } = useCurrentUser();

  if (!isRoleSwitcherEnabled || !user?.mock_mode || !user.switchable_users?.length) {
    return null;
  }

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span>角色</span>
      <Select
        size="small"
        style={{ width: 180 }}
        value={user.user_id}
        popupMatchSelectWidth={240}
        onChange={(value) => void switchUser(value)}
        options={user.switchable_users.map((u) => ({
          value: u.user_id,
          label: `${u.name}（${u.role_name}）`,
        }))}
      />
      <Tag color="gold" style={{ marginInlineEnd: 0 }}>
        演示
      </Tag>
    </span>
  );
}
