import { ArrowRightOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Col, Empty, Row, Statistic, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { fetchDashboardSummary } from '@/services/dashboard';
import type { DashboardSummary } from '@/services/dashboard';

export function TasksPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const load = () => {
    setLoading(true);
    void fetchDashboardSummary().then(setData).finally(() => setLoading(false));
  };
  useEffect(load, []);

  if (loading) return <PageLoading tip="正在加载我的任务…" />;
  return (
    <div>
      <div className="page-head">
        <div><h2 className="page-title">我的任务</h2><Typography.Text type="secondary">按招聘流程汇总的待处理事项</Typography.Text></div>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </div>
      {!data ? <Empty description="任务数据暂不可用" /> : (
        <Row gutter={[16, 16]}>
          {data.todo_items.map((item) => (
            <Col xs={24} sm={12} lg={8} key={item.key}>
              <Card hoverable onClick={() => navigate(item.route)}>
                <Statistic title={item.title} value={item.count} suffix="项" />
                <Button type="link" style={{ paddingLeft: 0, marginTop: 12 }}>去处理 <ArrowRightOutlined /></Button>
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
}
