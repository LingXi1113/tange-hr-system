import {
  AuditOutlined,
  BarChartOutlined,
  BellOutlined,
  CarryOutOutlined,
  CheckSquareOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  FormOutlined,
  IdcardOutlined,
  LogoutOutlined,
  ProjectOutlined,
  ScheduleOutlined,
  SettingOutlined,
  SolutionOutlined,
  TeamOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { Avatar, Layout, Menu } from 'antd';
import type { MenuProps } from 'antd';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';

import { NotificationBell } from '@/components/NotificationBell';
import { RoleSwitcher } from '@/components/RoleSwitcher';
import { logout, useCurrentUser } from '@/services/user';

const { Content, Header, Sider } = Layout;

const menuItems: MenuProps['items'] = [
  { key: '/workbench', icon: <DashboardOutlined />, label: '工作台' },
  { key: '/requirements', icon: <AuditOutlined />, label: '招聘需求' },
  { key: '/jobs', icon: <IdcardOutlined />, label: '职位管理' },
  { key: '/candidates', icon: <TeamOutlined />, label: '候选人' },
  { key: '/pipeline', icon: <ProjectOutlined />, label: '招聘流程看板' },
  { key: '/interviews', icon: <ScheduleOutlined />, label: '面试管理' },
  { key: '/approvals', icon: <CheckSquareOutlined />, label: '录用审批' },
  { key: '/offers', icon: <FileTextOutlined />, label: 'Offer管理' },
  { key: '/onboarding', icon: <SolutionOutlined />, label: '入职资料' },
  { key: '/talent-pool', icon: <DatabaseOutlined />, label: '人才库' },
  { key: '/reports', icon: <BarChartOutlined />, label: '招聘报表' },
  {
    key: 'group-settings',
    icon: <ToolOutlined />,
    label: '系统设置',
    children: [
      { key: '/pipeline-template', icon: <ToolOutlined />, label: '流程模板配置' },
      { key: '/eval-template', icon: <FormOutlined />, label: '面试评价模板' },
      { key: '/settings', icon: <SettingOutlined />, label: '系统参数与审批人' },
      { key: '/audit-logs', icon: <FileTextOutlined />, label: '操作日志' },
    ],
  },
  { key: '/notifications', icon: <BellOutlined />, label: '站内通知' },
  { key: '/tasks', icon: <CarryOutOutlined />, label: '我的任务' },
];

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const selectedKey = `/${location.pathname.split('/').filter(Boolean)[0] ?? 'workbench'}`;

  const onMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key.startsWith('/')) navigate(key);
  };

  return (
    <Layout className="app-shell">
      <Header className="app-topbar">
        <div className="brand">
          <span className="logo-dot" />
          <span>HR招聘管理系统</span>
        </div>
        <div className="topbar-right">
          <NotificationBell />
          <RoleSwitcher />
          {user && (
            <span className="user-chip">
              <Avatar size={24} style={{ background: '#CD9324' }}>
                {user.name.slice(0, 1)}
              </Avatar>
              <span>{user.name}</span>
              <span>· {user.role_name}</span>
              <LogoutOutlined
                style={{ cursor: 'pointer' }}
                title="退出"
                onClick={() => {
                  void logout().then(() => navigate('/login', { replace: true }));
                }}
              />
            </span>
          )}
        </div>
      </Header>
      <Layout>
        <Sider breakpoint="lg" collapsedWidth={0} className="app-sider" width={208} theme="light">
          <Menu
            className="sider-menu"
            mode="inline"
            theme="light"
            items={menuItems}
            selectedKeys={[selectedKey]}
            defaultOpenKeys={['group-settings']}
            onClick={onMenuClick}
          />
        </Sider>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
