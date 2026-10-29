import { LinkOutlined, RobotOutlined, TeamOutlined } from '@ant-design/icons';
import { Button, Card, Col, Descriptions, Empty, Form, Input, Modal, Progress, Row, Select, Space, Table, Tag, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { JOB_STATUS_TEXT, fetchJob, saveJob } from '@/services/job';
import type { Job } from '@/services/job';
import { http, unwrap } from '@/services/http';
import { fetchCandidates } from '@/services/candidate';
import type { Application, CandidateRow } from '@/services/candidate';
import { msg } from '@/utils/message';
import { buildJobPortrait, rankCandidatesForJob } from '@/utils/localAi';
import type { LocalRecommendation } from '@/utils/localAi';

interface PortraitFormValues {
  summary: string;
  required: string[];
  preferred: string[];
  interview_focus: string[];
}

export function JobDetailPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [portraitOpen, setPortraitOpen] = useState(false);
  const [recommendOpen, setRecommendOpen] = useState(false);
  const [recommendLoading, setRecommendLoading] = useState(false);
  const [recommendations, setRecommendations] = useState<LocalRecommendation[]>([]);
  const [portraitSaving, setPortraitSaving] = useState(false);
  const [portraitForm] = Form.useForm<PortraitFormValues>();

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
  const portrait = buildJobPortrait(job);
  const hasSavedPortrait = Boolean(
    job.ai_portrait?.summary
    || job.ai_portrait?.required?.length
    || job.ai_portrait?.preferred?.length
    || job.ai_portrait?.interview_focus?.length,
  );

  async function openRecommendations() {
    const currentJob = job;
    if (!currentJob) return;
    setRecommendOpen(true);
    setRecommendLoading(true);
    try {
      const data = await fetchCandidates({ page: 1, page_size: 100 });
      setRecommendations(rankCandidatesForJob(data.list as CandidateRow[], currentJob).slice(0, 20));
    } finally {
      setRecommendLoading(false);
    }
  }

  function openPortraitEditor() {
    portraitForm.setFieldsValue({
      summary: portrait.summary,
      required: portrait.required,
      preferred: portrait.preferred,
      interview_focus: portrait.interviewFocus,
    });
    setPortraitOpen(true);
  }

  async function savePortrait() {
    const currentJob = job;
    if (!currentJob) return;
    const values = await portraitForm.validateFields();
    setPortraitSaving(true);
    try {
      const updated = await saveJob(currentJob.id, { ai_portrait: values });
      setJob(updated);
      setPortraitOpen(false);
      msg.success('岗位画像已保存');
    } finally {
      setPortraitSaving(false);
    }
  }

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
              <Descriptions.Item label="筛选模板">{job.screening_rules.profile_name}</Descriptions.Item>
              <Descriptions.Item label="匹配阈值">
                通过 {job.screening_rules.pass_score} 分／待定 {job.screening_rules.pending_score} 分
              </Descriptions.Item>
              <Descriptions.Item label="核心技能" span={2}>
                {job.screening_rules.required_skills.length
                  ? job.screening_rules.required_skills.map((item) => <Tag key={item}>{item}</Tag>)
                  : '未配置'}
              </Descriptions.Item>
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
                {
                  title: '智能匹配', dataIndex: 'screening_score', width: 110,
                  render: (value: number | null, record: Application) => (
                    value == null ? '-' : (
                      <Tag color={(record.screening_review_decision || record.screening_decision) === 'pass' ? 'success' : 'gold'}>
                        {value}%
                      </Tag>
                    )
                  ),
                },
                { title: '进入时间', dataIndex: 'stage_entered_at', width: 160 },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            title={<Space><RobotOutlined style={{ color: '#7c3aed' }} />AI 招聘辅助<Tag color="purple">本地演示</Tag></Space>}
            size="small"
            style={{ marginBottom: 16 }}
          >
            <Typography.Paragraph type="secondary">
              根据职位要求生成岗位画像，并从现有人才库中给出辅助推荐。当前使用本地规则，配置 API Key 后可升级为语义分析。
            </Typography.Paragraph>
            <Space wrap>
              <Button type="primary" icon={<RobotOutlined />} onClick={openPortraitEditor}>
                {hasSavedPortrait ? '编辑岗位画像' : '生成岗位画像'}
              </Button>
              <Button icon={<TeamOutlined />} onClick={() => void openRecommendations()}>
                人才库推荐
              </Button>
            </Space>
          </Card>
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
      <Modal
        title={<Space><RobotOutlined style={{ color: '#7c3aed' }} />智能岗位画像<Tag color="purple">本地生成</Tag></Space>}
        open={portraitOpen}
        onCancel={() => setPortraitOpen(false)}
        onOk={() => void savePortrait()}
        okText="保存画像"
        cancelText="取消"
        confirmLoading={portraitSaving}
        okButtonProps={{ disabled: job.status === 'closed' }}
        width={720}
      >
        <Typography.Title level={4}>{portrait.title}</Typography.Title>
        <Typography.Paragraph type="secondary">
          系统先根据 JD 和筛选条件生成初稿，HR 可以直接修改。标签输入后按回车添加，保存后刷新页面仍会保留。
        </Typography.Paragraph>
        {job.status === 'closed' && <Typography.Paragraph type="warning">已关闭职位只能查看画像，不能保存修改。</Typography.Paragraph>}
        <Form form={portraitForm} layout="vertical" disabled={job.status === 'closed'}>
          <Form.Item name="summary" label="岗位画像描述" rules={[{ required: true, message: '请填写岗位画像描述' }]}>
            <Input.TextArea rows={5} placeholder="描述岗位目标、主要职责和理想候选人特征" />
          </Form.Item>
          <Form.Item name="required" label="必选条件">
            <Select mode="tags" tokenSeparators={[',', '，']} placeholder="输入学历、年限、核心技能等，按回车添加" />
          </Form.Item>
          <Form.Item name="preferred" label="加分项">
            <Select mode="tags" tokenSeparators={[',', '，']} placeholder="输入行业经验、工具或能力，按回车添加" />
          </Form.Item>
          <Form.Item name="interview_focus" label="建议面试重点">
            <Select mode="tags" tokenSeparators={[',', '，']} placeholder="输入需要在面试中重点验证的内容" />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={<Space><TeamOutlined style={{ color: '#1677ff' }} />人才库智能推荐<Tag color="purple">本地演示</Tag></Space>}
        open={recommendOpen}
        onCancel={() => setRecommendOpen(false)}
        footer={null}
        width={900}
      >
        <Typography.Paragraph type="secondary">
          已按“{job.name}”的必选技能、加分项和学历要求对人才库进行辅助排序，结果不会自动推进或淘汰候选人。
        </Typography.Paragraph>
        <Table
          rowKey={(record) => record.candidate.id}
          loading={recommendLoading}
          dataSource={recommendations}
          pagination={{ pageSize: 8 }}
          columns={[
            {
              title: '候选人', width: 150,
              render: (_, record) => (
                <a onClick={() => navigate(`/candidates/${record.candidate.id}`)}>{record.candidate.name}</a>
              ),
            },
            {
              title: '匹配度', width: 145,
              render: (_, record) => (
                <Progress percent={record.score} size="small" strokeColor={record.score >= 75 ? '#52c41a' : '#1677ff'} />
              ),
            },
            {
              title: '匹配依据',
              render: (_, record) => (
                <div>
                  <Space wrap>{record.matched.slice(0, 5).map((item) => <Tag color="success" key={item}>{item}</Tag>)}</Space>
                  <Typography.Text type="secondary" style={{ display: 'block', marginTop: 6 }}>{record.summary}</Typography.Text>
                </div>
              ),
            },
            {
              title: '待核实', width: 180,
              render: (_, record) => record.missing.length
                ? record.missing.slice(0, 3).map((item) => <Tag color="gold" key={item}>{item}</Tag>)
                : <Tag color="green">暂无明显缺失</Tag>,
            },
          ]}
        />
      </Modal>
    </div>
  );
}
