import { Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { RequireAuth } from '@/components/RequireAuth';
import { RequireRole } from '@/components/RequireRole';
import { AppLayout } from '@/layouts/AppLayout';
import { CandidateDetailPage } from '@/pages/CandidateDetailPage';
import { CandidatesPage } from '@/pages/CandidatesPage';
import { EvalTemplatePage } from '@/pages/EvalTemplatePage';
import { JobDetailPage } from '@/pages/JobDetailPage';
import { InterviewsPage } from '@/pages/InterviewsPage';
import { ApprovalsPage } from '@/pages/ApprovalsPage';
import { AuditLogsPage } from '@/pages/AuditLogsPage';
import { JobsPage } from '@/pages/JobsPage';
import { NotificationsPage } from '@/pages/NotificationsPage';
import { OnboardingPage } from '@/pages/OnboardingPage';
import { OffersPage } from '@/pages/OffersPage';
import { PipelinePage } from '@/pages/PipelinePage';
import { RequirementDetailPage } from '@/pages/RequirementDetailPage';
import { ReportsPage } from '@/pages/ReportsPage';
import { RequirementsPage } from '@/pages/RequirementsPage';
import { TalentPoolPage } from '@/pages/TalentPoolPage';
import { LoginPage } from '@/pages/LoginPage';
import { PipelineTemplatePage } from '@/pages/PipelineTemplatePage';
import { PublicJobPage } from '@/pages/PublicJobPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { TasksPage } from '@/pages/TasksPage';
import { WorkbenchPage } from '@/pages/WorkbenchPage';
import { useCurrentUser } from '@/services/user';

/** 登录后默认首页：HR 进工作台，其他角色进我的任务。 */
function HomeRedirect() {
  const { user } = useCurrentUser();
  const target = user?.role === 'hr' ? '/workbench' : '/tasks';
  return <Navigate to={target} replace />;
}

/** 未匹配路由：已登录回首页，未登录由守卫引导到登录页。 */
function FallbackRoute() {
  const location = useLocation();
  return <Navigate to={location.pathname.startsWith('/public/') ? '/login' : '/'} replace />;
}

export function RouterView() {
  return (
    <Routes>
      {/* 免登录路由 */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/public/job/:token" element={<PublicJobPage />} />

      {/* 后台路由：统一登录态校验 */}
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<HomeRedirect />} />
          <Route path="/workbench" element={<WorkbenchPage />} />
          <Route path="/requirements" element={<RequirementsPage />} />
          <Route path="/requirements/:id" element={<RequirementDetailPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/jobs/:id" element={<JobDetailPage />} />
          <Route path="/candidates" element={<CandidatesPage />} />
          <Route path="/candidates/:id" element={<CandidateDetailPage />} />
          <Route path="/pipeline" element={<PipelinePage />} />
          <Route path="/interviews" element={<InterviewsPage />} />
          <Route path="/offers" element={<OffersPage />} />
          <Route path="/talent-pool" element={<TalentPoolPage />} />
          <Route element={<RequireRole roles={['hr']} />}>
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/pipeline-template" element={<PipelineTemplatePage />} />
            <Route path="/eval-template" element={<EvalTemplatePage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/audit-logs" element={<AuditLogsPage />} />
          </Route>
          <Route element={<RequireRole roles={['hr', 'org_approver', 'gm', 'chairman', 'offer_sender']} />}>
            <Route path="/approvals" element={<ApprovalsPage />} />
          </Route>
          <Route element={<RequireRole roles={['hr', 'ssc']} />}>
            <Route path="/onboarding" element={<OnboardingPage />} />
          </Route>
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/tasks" element={<TasksPage />} />
        </Route>
      </Route>

      <Route path="*" element={<FallbackRoute />} />
    </Routes>
  );
}
