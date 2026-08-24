import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { useCurrentUser } from '@/services/user';

/**
 * 登录态路由守卫：后台路由必须登录后访问。
 * 未登录重定向到 /login；公开页（/public/*）不经过此守卫。
 */
export function RequireAuth() {
  const { user, initialized } = useCurrentUser();
  const location = useLocation();

  if (!initialized) {
    return <PageLoading tip="正在确认登录状态…" />;
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
