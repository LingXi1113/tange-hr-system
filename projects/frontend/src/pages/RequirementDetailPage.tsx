import { Button, Card, Col, Descriptions, Empty, Row, Table, Tag, Timeline } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { REQ_STATUS_TEXT, fetchRequirement } from '@/services/requirement';
import type { RequirementDetail } from '@/services/requirement';

export function RequirementDetailPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<RequirementDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    fetchRequirement(Number(id))
      .then(setDetail)
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <PageLoading />;
  if (!detail) return <Empty description="需求不存在" />;

  const distribution = Object.entries(detail.candidate_stats.stage_distribution);

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">
          {detail.name} <Tag color="gold">{REQ_STATUS_TEXT[detail.status] ?? detail.status}</Tag>
        </h2>
        <Button onClick={() => navigate('/requirements')}>返回列表</Button>
      </div>
      <Row gutter={16}>
        <Col xs={24} lg={14}>
          <Card title="基础信息" size="small" style={{ marginBottom: 16 }}>
            <Descriptions column={2} size="small">
              <Descriptions.Item label="所属部门">{detail.dept_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="招聘人数">{detail.headcount}</Descriptions.Item>
              <Descriptions.Item label="需求类型">{detail.request_type}</Descriptions.Item>
              <Descriptions.Item label="优先级">{detail.priority}</Descriptions.Item>
              <Descriptions.Item label="期望到岗">{detail.due_date || '-'}</Descriptions.Item>
              <Descriptions.Item label="负责人">{detail.owner_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="需求原因" span={2}>{detail.reason || '-'}</Descriptions.Item>
              <Descriptions.Item label="任职要求" span={2}>{detail.requirements || '-'}</Descriptions.Item>
              <Descriptions.Item label="备注" span={2}>{detail.remark || '-'}</Descriptions.Item>
            </Descriptions>
          </Card>
          <Card title="关联职位" size="small" style={{ marginBottom: 16 }}>
            <Table
              rowKey="id" size="small" pagination={false} dataSource={detail.jobs}
              locale={{ emptyText: '暂无关联职位' }}
              columns={[
                { title: '职位', dataIndex: 'name', render: (v: string, r: { id: number }) => <a onClick={() => navigate(`/jobs/${r.id}`)}>{v}</a> },
                { title: '编码', dataIndex: 'code' },
                { title: '状态', dataIndex: 'status' },
                { title: '人数', dataIndex: 'headcount' },
              ]}
            />
          </Card>
          <Card title="操作记录" size="small">
            {detail.operation_logs.length ? (
              <Timeline
                items={detail.operation_logs.map((l) => ({
                  children: `${l.operator_name} ${l.action}（${l.detail || ''}） · ${l.created_at}`,
                }))}
              />
            ) : <Empty description="暂无操作记录" />}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="候选人进展" size="small">
            <p>候选人总数：{detail.candidate_stats.total}</p>
            {distribution.length ? (
              <Table
                rowKey={(r) => r.stage} size="small" pagination={false}
                dataSource={distribution.map(([stage, count]) => ({ stage, count }))}
                columns={[
                  { title: '当前阶段', dataIndex: 'stage' },
                  { title: '人数', dataIndex: 'count' },
                ]}
              />
            ) : <Empty description="暂无候选人" />}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
