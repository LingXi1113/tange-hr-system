import { Result } from 'antd';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { useCurrentUser } from '@/services/user';

interface RequireRoleProps {
  roles: string[];
}

/** 页面级权限守卫；后端接口仍会再次校验，前端只负责避免无权页面误入。 */
export function RequireRole({ roles }: RequireRoleProps) {
  const { user, initialized } = useCurrentUser();
  const location = useLocation();

  if (!initialized) return null;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (!roles.includes(user.role)) {
    return <Result status="403" title="无权访问" subTitle="当前角色没有访问该页面的权限。" />;
  }
  return <Outlet />;
}
