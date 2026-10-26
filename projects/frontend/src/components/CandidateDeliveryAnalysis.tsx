import { Button, Card, Col, Collapse, Empty, Row, Space, Tag, Timeline, Typography } from 'antd';
import { useEffect, useState } from 'react';

import { PageLoading } from './PageLoading';
import type { DeliveryAnalysis } from '@/services/candidate';
import { applicationStatus, deliverySource } from '@/utils/applicationPresentation';

export function CandidateDeliveryAnalysis({ data, loading, failed, selectedId, onSelect, onRetry }: {
  data: DeliveryAnalysis | null;
  loading: boolean;
  failed: boolean;
  selectedId: number | null;
  onSelect: (applicationId: number) => void;
  onRetry: () => void;
}) {
  const [expanded, setExpanded] = useState<string[]>([]);
  useEffect(() => { setExpanded(selectedId ? [String(selectedId)] : []); }, [selectedId]);
  if (loading) return <PageLoading tip="正在加载投递分析" />;
  if (!data) return <Empty description={failed ? '投递分析加载失败' : '暂无投递记录'}>
    {failed && <Button onClick={onRetry}>重新加载</Button>}
  </Empty>;
  const { summary } = data;
  const allExpanded = data.applications.length > 0 && expanded.length === data.applications.length;
  return (
    <div className="candidate-delivery-analysis">
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="投递分析" size="small">
            <div className="delivery-metrics">
              <div><strong>{summary.total_deliveries}</strong><span>投递次数</span></div>
              <div><strong>{summary.highest_stage || '-'}</strong><span>最高到达阶段</span></div>
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="推荐分析" size="small">
            <div className="delivery-metrics">
              <div><strong>{summary.recommendations ?? 0}</strong><span>推荐业务复筛</span></div>
              <div><strong>{summary.passed_recommendations ?? 0}</strong><span>通过</span></div>
              <div><strong>{summary.recommendation_pass_rate ?? 0}%</strong><span>通过率</span></div>
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="面试分析" size="small">
            <div className="delivery-metrics">
              <div><strong>{summary.interviews}</strong><span>面试场次</span></div>
              <div><strong>{summary.passed_interviews}</strong><span>评价通过</span></div>
              <div><strong>{summary.interview_pass_rate}%</strong><span>评价通过率</span></div>
            </div>
          </Card>
        </Col>
      </Row>
      <div className="delivery-section-head">
        <Typography.Title level={5} style={{ margin: 0 }}>投递明细</Typography.Title>
        <Button type="link" onClick={() => setExpanded(allExpanded ? [] : data.applications.map((app) => String(app.id)))}>
          {allExpanded ? '一键收起' : '一键展开'}
        </Button>
      </div>
      {!data.applications.length ? <Empty description="暂无投递记录" /> : (
        <Collapse
          activeKey={expanded}
          onChange={(keys) => setExpanded(Array.isArray(keys) ? keys : [keys])}
          expandIconPosition="end"
          ghost
          items={data.applications.map((app) => {
            const status = applicationStatus(app);
            return {
              key: String(app.id),
              label: (
                <div className="delivery-record-heading">
                  <Space wrap>
                    <span>{app.created_at || app.stage_entered_at || '-'}</span>
                    <Typography.Text strong>{app.job_name || '职位已删除'}</Typography.Text>
                    <Typography.Text type="secondary">最高到达：{app.highest_stage_name}</Typography.Text>
                  </Space>
                  <Tag color={status.color}>{status.label} · {app.stage_name}</Tag>
                </div>
              ),
              children: (
                <div className="delivery-record-body">
                  <Space wrap style={{ marginBottom: 20 }}>
                    <Typography.Text type="secondary">负责人：{app.owner_name || '-'}</Typography.Text>
                    <Typography.Text type="secondary">来源：{deliverySource(app.source)}</Typography.Text>
                    <Button size="small" onClick={() => onSelect(app.id)}>查看本次投递及处理流程</Button>
                    {app.closed_reason && <Typography.Text type="secondary">归档原因：{app.closed_reason}</Typography.Text>}
                    {app.replacement_application_id && (
                      <Button size="small" onClick={() => onSelect(app.replacement_application_id!)}>查看更换后的投递</Button>
                    )}
                    {app.previous_application_id && (
                      <Button size="small" onClick={() => onSelect(app.previous_application_id!)}>查看上次投递</Button>
                    )}
                  </Space>
                  <Timeline items={(app.timeline || []).map((event) => ({
                    key: event.id,
                    children: <div>
                      <Typography.Text type="secondary">{event.created_at || '时间未记录'}</Typography.Text>
                      <div style={{ marginTop: 6 }}><Typography.Text strong>{event.title}</Typography.Text></div>
                      {event.operator_name && <div style={{ marginTop: 4 }}>操作人：{event.operator_name}</div>}
                      {event.detail && <div className="delivery-event-detail">{event.detail}</div>}
                    </div>,
                  }))} />
                </div>
              ),
            };
          })}
        />
      )}
      <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>
        按应聘记录分别统计，同一候选人多次投递不会合并为一条记录；推荐通过率按业务复筛后推进统计，面试通过率按有效评价统计。
      </Typography.Paragraph>
    </div>
  );
}
