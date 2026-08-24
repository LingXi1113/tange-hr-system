import { ArrowRightOutlined, BellOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { Card, Col, Empty, List, Progress, Row, Space, Statistic, Tag, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { fetchDashboardSummary } from '@/services/dashboard';
import type { DashboardSummary } from '@/services/dashboard';
import { http, unwrap } from '@/services/http';
import { useCurrentUser } from '@/services/user';

interface HealthInfo { status: string; service: string; time: string; platform_provider: string; }

const overviewItems = [
  ['ongoing_requirements', '进行中需求'], ['open_jobs', '招聘中职位'], ['candidate_total', '候选人总数'],
  ['month_interviews', '本月面试'], ['month_offers', '本月 Offer'], ['month_onboarded', '本月入职'],
] as const;

export function WorkbenchPage() {
  const { user } = useCurrentUser();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    Promise.all([fetchDashboardSummary(), http.get('/api/health').then((resp) => unwrap<HealthInfo>(resp))])
      .then(([dashboard, serviceHealth]) => {
        if (mounted) { setSummary(dashboard); setHealth(serviceHealth); }
      })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, []);

  if (loading) return <PageLoading tip="正在加载工作台…" />;
  return (
    <div>
      <div className="page-head">
        <div>
          <h2 className="page-title">工作台</h2>
          <Typography.Text type="secondary">{user ? `${user.name} · ${user.role_name} · ${user.dept_name}` : ''}</Typography.Text>
        </div>
        {health && <Tag color="success"><CheckCircleOutlined /> 服务正常 · {health.time}</Tag>}
      </div>
      {!summary ? <Empty description="工作台数据暂不可用" /> : (
        <>
          <Card title="我的待办" extra={<a onClick={() => navigate('/tasks')}>查看全部 <ArrowRightOutlined /></a>} style={{ marginBottom: 16 }}>
            <Row gutter={[16, 16]}>
              {summary.todo_items.map((item) => (
                <Col xs={24} sm={12} lg={8} xl={4} key={item.key}>
                  <Card hoverable size="small" onClick={() => navigate(item.route)}><Statistic title={item.title} value={item.count} suffix="项" /></Card>
                </Col>
              ))}
            </Row>
          </Card>
          <Row gutter={16}>
            <Col xs={24} xl={15}>
              <Card title="招聘概览" style={{ marginBottom: 16 }}>
                <Row gutter={[16, 24]}>{overviewItems.map(([key, label]) => <Col xs={12} sm={8} key={key}><Statistic title={label} value={summary.overview[key] ?? 0} /></Col>)}</Row>
              </Card>
              <Card title="招聘漏斗" style={{ marginBottom: 16 }}>
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  {summary.funnel.filter((item) => item.count > 0).map((item) => {
                    const max = Math.max(...summary.funnel.map((value) => value.count), 1);
                    return <div key={item.stage_key}><Space style={{ width: 130 }}><span>{item.name}</span><strong>{item.count}</strong></Space><Progress percent={Math.round(item.count / max * 100)} showInfo={false} strokeColor="#CD9324" /></div>;
                  })}
                  {!summary.funnel.some((item) => item.count > 0) && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无流程数据" />}
                </Space>
              </Card>
            </Col>
            <Col xs={24} xl={9}>
              <Card title={<Space><BellOutlined />最近动态</Space>} style={{ marginBottom: 16 }}>
                {summary.recent_activities.length ? <List size="small" dataSource={summary.recent_activities} renderItem={(item) => <List.Item><List.Item.Meta title={`${item.operator_name || '系统'} · ${item.action}`} description={<>{item.detail || item.biz_type} · {item.created_at}</>} /></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无动态" />}
              </Card>
              <Card title="系统状态">
                <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>{health?.platform_provider === 'mock' ? '当前使用 Mock 平台身份，适合本地联调。' : `平台身份：${health?.platform_provider}`}</Typography.Paragraph>
                <Typography.Text type="secondary">未读通知：{summary.notification_unread} 条</Typography.Text>
              </Card>
            </Col>
          </Row>
        </>
      )}
    </div>
  );
}
