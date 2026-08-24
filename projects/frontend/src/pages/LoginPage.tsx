import { Button, List, Tag, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { fetchMockUsers } from '@/services/mockAuth';
import { msg } from '@/utils/message';
import type { SwitchableUser } from '@/services/user';
import { mockLogin, useCurrentUser } from '@/services/user';

/**
 * 登录页（P0：Mock 平台用户选择登录）。
 * 生产接入即先平台后，本页由平台免登替代（embedded 模式 SSO）。
 */
export function LoginPage() {
  const { user, initialized } = useCurrentUser();
  const navigate = useNavigate();
  const location = useLocation();
  const [users, setUsers] = useState<SwitchableUser[]>([]);
  const [mockEnabled, setMockEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [loggingIn, setLoggingIn] = useState<string | null>(null);

  useEffect(() => {
    fetchMockUsers()
      .then((data) => {
        setMockEnabled(data.enabled);
        setUsers(data.users);
      })
      .catch(() => setMockEnabled(false))
      .finally(() => setLoading(false));
  }, []);

  if (initialized && user) {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from ?? homePathOf(user.role)} replace />;
  }

  function homePathOf(role: string) {
    return role === 'hr' ? '/workbench' : '/tasks';
  }

  async function handleLogin(target: SwitchableUser) {
    setLoggingIn(target.user_id);
    try {
      const loggedIn = await mockLogin(target.user_id);
      msg.success(`已以 ${loggedIn.name}（${loggedIn.role_name}）登录`);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from ?? homePathOf(loggedIn.role), { replace: true });
    } finally {
      setLoggingIn(null);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-title">
          <span className="logo-dot" />
          HR招聘管理系统
        </div>
        <div className="login-sub">演示环境：选择平台用户登录（生产环境由即先平台免登进入）</div>
        {loading ? (
          <PageLoading tip="加载用户列表…" />
        ) : !mockEnabled ? (
          <Typography.Text type="secondary">
            当前环境未启用 Mock 登录，请通过即先平台免登进入系统。
          </Typography.Text>
        ) : (
          <List
            dataSource={users}
            renderItem={(item) => (
              <List.Item
                style={{ cursor: 'pointer', paddingInline: 8 }}
                onClick={() => void handleLogin(item)}
                actions={[
                  <Button
                    key="login"
                    size="small"
                    type="link"
                    loading={loggingIn === item.user_id}
                  >
                    登录
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <span>
                      {item.name} <Tag color="gold">{item.role_name}</Tag>
                    </span>
                  }
                  description={item.dept_name}
                />
              </List.Item>
            )}
          />
        )}
      </div>
    </div>
  );
}
