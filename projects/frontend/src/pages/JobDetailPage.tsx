import { LinkOutlined } from '@ant-design/icons';
import { Button, Card, Col, Descriptions, Empty, Row, Table, Tag, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { JOB_STATUS_TEXT, fetchJob } from '@/services/job';
import type { Job } from '@/services/job';
import { http, unwrap } from '@/services/http';
import type { Application } from '@/services/candidate';
import { msg } from '@/utils/message';

export function JobDetailPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    Promise.all([
      fetchJob(Number(id)),
      http.get(`/api/jobs/${id}/applications`).then((r) => unwrap<Application[]>(r)),
    ])
      .then(([j, apps]) => {
        setJob(j);
        setApplications(apps);
      })
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <PageLoading />;
  if (!job) return <Empty description="职位不存在" />;

  const publicUrl = `${window.location.origin}/#/public/job/${job.public_token}`;

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">
          {job.name} <Tag color="gold">{JOB_STATUS_TEXT[job.status] ?? job.status}</Tag>
        </h2>
        <Button onClick={() => navigate('/jobs')}>返回列表</Button>
      </div>
      <Row gutter={16}>
        <Col xs={24} lg={14}>
          <Card title="职位信息" size="small" style={{ marginBottom: 16 }}>
            <Descriptions column={2} size="small">
              <Descriptions.Item label="编码">{job.code}</Descriptions.Item>
              <Descriptions.Item label="部门">{job.dept_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="地点">{job.location || '-'}</Descriptions.Item>
              <Descriptions.Item label="职级">{job.level || '-'}</Descriptions.Item>
              <Descriptions.Item label="人数">{job.headcount}</Descriptions.Item>
              <Descriptions.Item label="薪资范围">{job.salary_range || '-'}</Descriptions.Item>
              <Descriptions.Item label="面试轮次">{job.interview_rounds?.join(' → ') || '一面'}</Descriptions.Item>
              <Descriptions.Item label="职位描述" span={2}>{job.description || '-'}</Descriptions.Item>
              <Descriptions.Item label="任职资格" span={2}>{job.qualification || '-'}</Descriptions.Item>
            </Descriptions>
          </Card>
          <Card title="应聘记录" size="small">
            <Table
              rowKey="id" size="small" pagination={false} dataSource={applications}
              locale={{ emptyText: '暂无应聘记录' }}
              columns={[
                {
                  title: '候选人', dataIndex: 'candidate_name',
                  render: (v: string, r: Application) => <a onClick={() => navigate(`/candidates/${r.candidate_id}`)}>{v}</a>,
                },
                { title: '来源', dataIndex: 'source', width: 100 },
                { title: '当前阶段', dataIndex: 'current_stage', width: 120 },
                { title: '状态', dataIndex: 'status', width: 100 },
                { title: '进入时间', dataIndex: 'stage_entered_at', width: 160 },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="公开页与投递" size="small">
            <p style={{ color: 'rgba(23,26,29,0.6)' }}>
              公开页提供简易投递表单，候选人无需注册登录。暂停/关闭的职位停止接收投递。
            </p>
            <Typography.Paragraph copyable={{ text: publicUrl }} style={{ wordBreak: 'break-all' }}>
              {publicUrl}
            </Typography.Paragraph>
            <Button
              type="primary" icon={<LinkOutlined />}
              onClick={() => window.open(`/#/public/job/${job.public_token}`, '_blank')}
            >
              打开公开页
            </Button>
            <Button
              style={{ marginLeft: 8 }}
              onClick={async () => {
                await navigator.clipboard.writeText(publicUrl);
                msg.success('公开链接已复制');
              }}
            >
              复制链接
            </Button>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
