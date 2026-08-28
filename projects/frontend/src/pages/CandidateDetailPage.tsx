import { DeleteOutlined, EditOutlined, FileSearchOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import {
  Button, Card, Col, Descriptions, Empty, Form, Input, List, Modal, Popconfirm, Row,
  Select, Table, Tag, Upload,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import {
  fetchCandidate, fetchTransitions, parseResume, saveCandidate, unlockApplication, uploadResume,
} from '@/services/candidate';
import { fetchInterviews, INTERVIEW_STATUS_TEXT } from '@/services/interview';
import type { Interview } from '@/services/interview';
import { fetchOffers, OFFER_STATUS_COLOR, OFFER_STATUS_TEXT } from '@/services/offer';
import type { Offer } from '@/services/offer';
import { addToPool, fetchPool, removeFromPool } from '@/services/talentPool';
import type { PoolEntry } from '@/services/talentPool';
import type { CandidateDetail } from '@/services/candidate';
import { useCurrentUser } from '@/services/user';
import { msg } from '@/utils/message';
import { openProtectedFile } from '@/services/http';

const STAGE_TEXT: Record<string, string> = {
  // PRD v1.1 默认九阶段
  new_resume: '待筛选', pending_screen: '待筛选', hr_screen_passed: '人力筛选',
  pending_interview: '待面试', interviewing: '面试中', interview_passed: '面试通过',
  offer_pending: '录用通知', pending_onboard: '待入职', onboarded: '已入职',
  // 终态
  eliminated: '淘汰', abandoned: '放弃', talent_pool: '人才库',
  // v1.0 旧阶段（兼容历史数据）
  business_screen: '业务复筛', interview_1: '一面', interview_2: '二面',
  interview_3: '三面', hr_interview: '人力面', offer_approval: '最终筛选', offer: '录用通知',
  // 可选环节
  written_test: '笔试', assessment: '测评', background_check: '背调',
  re_interview: '复试', custom: '自定义',
};

function stageText(stage: string | undefined) {
  const labels: Record<string, string> = {
    ...STAGE_TEXT,
    hr_screen_passed: '人力筛选',
    offer_pending: '录用通知',
    offer: '录用通知',
    hr_interview: '人力面',
  };
  return labels[stage ?? ''] ?? '其他阶段';
}

const DEFAULT_STAGE_FLOW = [
  { key: 'pending_screen', label: '\u5F85\u7B5B\u9009' },
  { key: 'hr_screen_passed', label: '人力筛选' },
  { key: 'business_screen', label: '\u4E1A\u52A1\u7B5B\u9009' },
  { key: 'interview_1', label: '\u4E00\u9762' },
  { key: 'interview_2', label: '\u4E8C\u9762' },
  { key: 'hr_interview', label: '人力面' },
  { key: 'offer_approval', label: '\u6700\u7EC8\u7B5B\u9009' },
] as const;

const DEFAULT_STAGE_ALIASES: Record<string, string> = {
  new_resume: 'pending_screen',
  pending_interview: 'interview_1',
  interviewing: 'interview_1',
  interview_passed: 'interview_1',
  offer_pending: 'offer_approval',
  pending_onboard: 'offer_approval',
  onboarded: 'offer_approval',
};

type StageTransition = {
  from_stage: string;
  to_stage: string;
  reason: string;
  operator_name: string;
  created_at: string;
};

function stageFlowIndex(stageKey: string) {
  const normalized = DEFAULT_STAGE_ALIASES[stageKey] || stageKey;
  return DEFAULT_STAGE_FLOW.findIndex((stage) => stage.key === normalized);
}

function StageProgress({ currentStage, transitions }: { currentStage: string; transitions: StageTransition[] }) {
  const reached = [currentStage, ...transitions.flatMap((item) => [item.from_stage, item.to_stage])]
    .map(stageFlowIndex)
    .filter((index) => index >= 0);
  const currentIndex = reached.length ? Math.max(...reached) : -1;

  return (
    <div style={{ overflowX: 'auto', padding: '18px 8px 6px' }}>
      <div style={{ display: 'flex', minWidth: 680, alignItems: 'flex-start' }}>
        {DEFAULT_STAGE_FLOW.map((stage, index) => {
          const completed = index < currentIndex;
          const active = index === currentIndex;
          const leftDone = index > 0 && index <= currentIndex;
          const rightDone = index < currentIndex;
          return (
            <div key={stage.key} style={{ flex: 1, minWidth: 90, textAlign: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', height: 18 }}>
                {index > 0 && (
                  <div style={{ flex: 1, height: leftDone ? 4 : 1, background: leftDone ? '#d99b1d' : '#d9d9d9' }} />
                )}
                <div
                  title={active ? '\u5F53\u524D\u9636\u6BB5' : completed ? '\u5DF2\u5B8C\u6210' : '\u672A\u5F00\u59CB'}
                  style={{
                    width: active ? 16 : 14,
                    height: active ? 16 : 14,
                    borderRadius: '50%',
                    flex: '0 0 auto',
                    background: completed || active ? '#d99b1d' : '#fff',
                    border: `${active ? 3 : 2}px solid ${completed || active ? '#d99b1d' : '#c9c9c9'}`,
                    boxSizing: 'border-box',
                  }}
                />
                {index < DEFAULT_STAGE_FLOW.length - 1 && (
                  <div style={{ flex: 1, height: rightDone ? 4 : 1, background: rightDone ? '#d99b1d' : '#d9d9d9' }} />
                )}
              </div>
              <div style={{ marginTop: 9, color: active || completed ? '#262626' : '#9a9a9a', fontWeight: active ? 600 : 400, whiteSpace: 'nowrap' }}>
                {stage.label}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

type ResumeFormValues = {
  version: number;
  name: string;
  gender: string;
  phone: string;
  email: string;
  city: string;
  tags: string;
  remark: string;
  education: CandidateDetail['education'];
  work_experience: CandidateDetail['work_experience'];
};

export function CandidateDetailPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const [detail, setDetail] = useState<CandidateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedAppId, setSelectedAppId] = useState<number | null>(null);
  const [transitions, setTransitions] = useState<StageTransition[]>([]);
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [poolEntry, setPoolEntry] = useState<PoolEntry | null>(null);
  const [poolModalOpen, setPoolModalOpen] = useState(false);
  const [poolCategory, setPoolCategory] = useState('');
  const [poolReason, setPoolReason] = useState('');
  const [resumeEditOpen, setResumeEditOpen] = useState(false);
  const [resumeForm] = Form.useForm<ResumeFormValues>();

  const load = useCallback(async () => {
    if (!id) return;
    const data = await fetchCandidate(Number(id));
    setDetail(data);
    if (data.applications.length && selectedAppId == null) {
      setSelectedAppId(data.applications[0].id);
    }
  }, [id, selectedAppId]);

  useEffect(() => {
    setLoading(true);
    load().finally(() => setLoading(false));
  }, [load]);

  useEffect(() => {
    if (selectedAppId) {
      fetchTransitions(selectedAppId).then(setTransitions);
    }
  }, [selectedAppId]);

  useEffect(() => {
    if (id) {
      fetchInterviews({ candidate_id: Number(id), page_size: 50 }).then((d) => setInterviews(d.list));
      fetchOffers({ candidate_id: Number(id), page_size: 50 }).then((d) => setOffers(d.list));
      fetchPool({ candidate_id: Number(id), page_size: 1 }).then((d) => setPoolEntry(d.list[0] ?? null));
    }
  }, [id]);

  if (loading && !detail) return <PageLoading />;
  if (!detail) return <Empty description="候选人不存在" />;

  const canUnlock = user?.roles?.includes('unlock');
  const canManage = user?.role === 'hr';
  const canResume = ['hr', 'business_screener', 'interviewer'].includes(user?.role ?? '');
  const candidate = detail;
  const selectedApplication = detail.applications.find((application) => application.id === selectedAppId)
    ?? detail.applications[0];

  function openResumeEditor(values?: Partial<ResumeFormValues>) {
    resumeForm.setFieldsValue({
      version: candidate.version,
      name: candidate.name,
      gender: candidate.gender,
      phone: candidate.phone,
      email: candidate.email,
      city: candidate.city,
      tags: candidate.tags,
      remark: candidate.remark,
      education: candidate.education,
      work_experience: candidate.work_experience,
      ...values,
    });
    setResumeEditOpen(true);
  }

  async function saveResumeProfile() {
    const values = await resumeForm.validateFields();
    const result = await saveCandidate(candidate.id, values);
    if (result.duplicated) {
      msg.error('手机号或邮箱与其他候选人重复，请确认后再保存');
      return;
    }
    msg.success('候选人简历信息已保存');
    setResumeEditOpen(false);
    await load();
  }

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">
          {detail.name}
          {detail.lock && (
            <Tag color="error" style={{ marginLeft: 8 }}>
              锁定中 · {detail.lock.start_at} ~ {detail.lock.end_at}
            </Tag>
          )}
        </h2>
        <Button onClick={() => navigate('/candidates')}>返回列表</Button>
      </div>
      <Row gutter={16}>
        <Col xs={24} lg={12}>
          <Card
            title="基本信息" size="small" style={{ marginBottom: 16 }}
            extra={canManage ? (
              <Button size="small" icon={<EditOutlined />} onClick={() => openResumeEditor()}>
                维护简历
              </Button>
            ) : null}
          >
            <Descriptions column={2} size="small">
              <Descriptions.Item label="性别">{detail.gender || '-'}</Descriptions.Item>
              <Descriptions.Item label="城市">{detail.city || '-'}</Descriptions.Item>
              <Descriptions.Item label="手机号">{detail.phone}</Descriptions.Item>
              <Descriptions.Item label="邮箱">{detail.email}</Descriptions.Item>
              <Descriptions.Item label="来源">{detail.source}</Descriptions.Item>
              <Descriptions.Item label="负责人">{detail.owner_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="标签" span={2}>{detail.tags || '-'}</Descriptions.Item>
              <Descriptions.Item label="备注" span={2}>{detail.remark || '-'}</Descriptions.Item>
            </Descriptions>
          </Card>
          <Card
            title="简历附件" size="small" style={{ marginBottom: 16 }}
            extra={canResume ? (
              <Upload
                showUploadList={false} accept=".pdf,.docx,.doc,.jpg,.jpeg,.png"
                beforeUpload={async (file) => {
                  const up = await uploadResume(file as File, detail.id);
                  msg.success('简历已上传');
                  const parsed = await parseResume(up.attachment_id);
                  if (parsed.parse_status === 'system') {
                    const fields = parsed.fields;
                    if (canManage) {
                      openResumeEditor({
                        name: fields.name || detail.name,
                        gender: fields.gender || detail.gender,
                        phone: fields.phone || detail.phone,
                        email: fields.email || detail.email,
                        education: fields.education?.length ? fields.education : detail.education,
                        work_experience: fields.work_experience?.length ? fields.work_experience : detail.work_experience,
                      });
                    } else {
                      Modal.info({
                        title: '解析结果',
                        content: <pre style={{ fontSize: 12 }}>{JSON.stringify(fields, null, 2)}</pre>,
                      });
                    }
                  } else {
                    msg.error(parsed.message);
                  }
                  void load();
                  return false;
                }}
              >
                <Button size="small" icon={<UploadOutlined />}>上传简历</Button>
              </Upload>
            ) : null}
          >
            <List
              size="small"
              locale={{ emptyText: '暂无附件' }}
              dataSource={detail.attachments}
              renderItem={(a) => (
                <List.Item
                  actions={[
                    <Button key="view" size="small" type="link" icon={<FileSearchOutlined />}
                      onClick={() => void openProtectedFile(`/api/attachments/${a.id}`)}>
                      预览
                    </Button>,
                  ]}
                >
                  {a.file_name}
                  {a.parse_status === 'system' && <Tag color="success" style={{ marginLeft: 8 }}>系统解析</Tag>}
                  {a.parse_status === 'failed' && <Tag color="warning" style={{ marginLeft: 8 }}>解析失败·人工录入</Tag>}
                </List.Item>
              )}
            />
          </Card>
          <Card title="教育经历" size="small" style={{ marginBottom: 16 }}>
            <List
              size="small" locale={{ emptyText: '暂无' }} dataSource={detail.education}
              renderItem={(e) => (
                <List.Item>{`${e.school ?? ''} · ${e.major ?? ''} · ${e.degree ?? ''} · ${e.graduate_at ?? ''}`}</List.Item>
              )}
            />
          </Card>
          <Card title="工作经历" size="small">
            <List
              size="small" locale={{ emptyText: '暂无' }} dataSource={detail.work_experience}
              renderItem={(w) => (
                <List.Item>{`${w.company ?? ''} · ${w.position ?? ''}（${w.start ?? ''} ~ ${w.end ?? ''}）`}</List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="应聘记录（点击切换查看过程）" size="small" style={{ marginBottom: 16 }}>
            <Table
              rowKey="id" size="small" pagination={false} dataSource={detail.applications}
              locale={{ emptyText: '暂无应聘记录' }}
              rowClassName={(r) => (r.id === selectedAppId ? 'ant-table-row-selected' : '')}
              onRow={(r) => ({ onClick: () => setSelectedAppId(r.id), style: { cursor: 'pointer' } })}
              columns={[
                { title: '职位', dataIndex: 'job_name' },
                { title: '阶段', dataIndex: 'current_stage', width: 100, render: (v: string) => stageText(v) },
                { title: '状态', dataIndex: 'status', width: 90 },
                { title: '进入时间', dataIndex: 'stage_entered_at', width: 150 },
              ]}
            />
          </Card>
          <Card
            title="阶段流转记录" size="small" style={{ marginBottom: 16 }}
            extra={
              canUnlock && detail.applications.some((a) => a.id === selectedAppId && a.status === 'in_progress') ? (
                <Button
                  size="small" danger
                  onClick={() => {
                    Modal.confirm({
                      title: '强制解锁（将记录操作日志）',
                      content: '请输入解锁原因',
                      onOk: async () => {
                        const reason = window.prompt('解锁原因');
                        if (!reason) return;
                        await unlockApplication(selectedAppId!, reason);
                        msg.success('已解锁');
                        void load();
                      },
                    });
                  }}
                >
                  强制解锁
                </Button>
              ) : null
            }
          >
            <StageProgress currentStage={selectedApplication?.current_stage ?? 'pending_screen'} transitions={transitions} />
            {false && transitions.length ? (
              <Timeline
                items={transitions.map((t) => ({
                  children: `${STAGE_TEXT[t.from_stage] || t.from_stage || '进入流程'} → ${STAGE_TEXT[t.to_stage] || t.to_stage}｜${t.reason || '-'}｜${t.operator_name || '系统'} · ${t.created_at}`,
                }))}
              />
            ) : <Empty description="选择应聘记录查看流转" />}
          </Card>
          <Card
            title="面试记录" size="small" style={{ marginBottom: 16 }}
            extra={canManage ? <Button size="small" type="primary" onClick={() => navigate('/interviews')}>安排面试</Button> : null}
          >
            <Table
              rowKey="id" size="small" pagination={false} dataSource={interviews}
              locale={{ emptyText: '暂无面试安排' }}
              columns={[
                { title: '轮次', dataIndex: 'round', width: 70 },
                { title: '时间', dataIndex: 'start_at', width: 130 },
                { title: '面试官', dataIndex: 'interviewer_name', width: 80 },
                {
                  title: '状态', dataIndex: 'status', width: 80,
                  render: (v: string) => INTERVIEW_STATUS_TEXT[v] ?? v,
                },
              ]}
            />
          </Card>
          <Card
            title="Offer 记录" size="small" style={{ marginBottom: 16 }}
            extra={canManage ? (
              <Button
                size="small" type="primary"
                onClick={() => navigate(`/offers?new=1&candidate=${id}`)}
              >
                创建 Offer
              </Button>
            ) : null}
          >
            <Table
              rowKey="id" size="small" pagination={false} dataSource={offers}
              locale={{ emptyText: '暂无 Offer 记录' }}
              columns={[
                { title: '职位', dataIndex: 'job_name' },
                { title: '薪资', dataIndex: 'salary', width: 90 },
                { title: '有效期', dataIndex: 'valid_until', width: 100 },
                {
                  title: '状态', dataIndex: 'status', width: 80,
                  render: (v: string) => (
                    <Tag color={OFFER_STATUS_COLOR[v]}>{OFFER_STATUS_TEXT[v] ?? v}</Tag>
                  ),
                },
              ]}
            />
          </Card>
          <Card
            title="人才库" size="small" style={{ marginBottom: 16 }}
            extra={canManage ? (
              poolEntry ? (
                <Popconfirm
                  title="确认移出人才库？"
                  onConfirm={async () => {
                    await removeFromPool(poolEntry.id);
                    msg.success('已移出人才库');
                    setPoolEntry(null);
                  }}
                >
                  <Button size="small" danger>移出人才库</Button>
                </Popconfirm>
              ) : (
                <Button size="small" type="primary" onClick={() => setPoolModalOpen(true)}>
                  加入人才库
                </Button>
              )
            ) : null}
          >
            {poolEntry ? (
              <Descriptions column={1} size="small">
                <Descriptions.Item label="状态">
                  {poolEntry.status === 'active' ? '待激活' : '已激活'}
                </Descriptions.Item>
                <Descriptions.Item label="分类">{poolEntry.category || '-'}</Descriptions.Item>
                <Descriptions.Item label="标签">
                  {poolEntry.tags?.length ? poolEntry.tags.join('、') : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="来源">{poolEntry.source_text}</Descriptions.Item>
                <Descriptions.Item label="加入原因">{poolEntry.reason || '-'}</Descriptions.Item>
                <Descriptions.Item label="加入时间">{poolEntry.created_at}</Descriptions.Item>
              </Descriptions>
            ) : (
              <Empty description="暂未加入人才库" />
            )}
          </Card>
          <Card title="操作日志" size="small">
            <List
              size="small" locale={{ emptyText: '暂无日志' }}
              dataSource={detail.operation_logs.slice(0, 20)}
              renderItem={(l) => (
                <List.Item>{`${l.operator_name} ${l.action}（${l.detail || ''}） · ${l.created_at}`}</List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>
      <Modal
        title="维护候选人简历"
        open={resumeEditOpen}
        width={820}
        onCancel={() => setResumeEditOpen(false)}
        onOk={() => void saveResumeProfile()}
        okText="保存"
        cancelText="取消"
      >
        <Form form={resumeForm} layout="vertical">
          <Form.Item name="version" hidden>
            <Input type="hidden" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="gender" label="性别">
                <Select allowClear options={[{ value: '男', label: '男' }, { value: '女', label: '女' }]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="phone" label="手机号">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="email" label="邮箱">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="city" label="城市">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="tags" label="标签（逗号分隔）">
                <Input />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="remark" label="备注">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="教育经历">
            <Form.List name="education">
              {(fields, { add, remove }) => (
                <>
                  {fields.map((field) => (
                    <Card key={field.key} size="small" style={{ marginBottom: 8 }}>
                      <Row gutter={8} align="middle">
                        <Col flex="1 1 180px">
                          <Form.Item {...field} name={[field.name, 'school']} label="学校"><Input /></Form.Item>
                        </Col>
                        <Col flex="1 1 140px">
                          <Form.Item {...field} name={[field.name, 'major']} label="专业"><Input /></Form.Item>
                        </Col>
                        <Col flex="0 1 110px">
                          <Form.Item {...field} name={[field.name, 'degree']} label="学历"><Input /></Form.Item>
                        </Col>
                        <Col flex="0 1 130px">
                          <Form.Item {...field} name={[field.name, 'graduate_at']} label="毕业时间"><Input /></Form.Item>
                        </Col>
                        <Col flex="0 0 32px">
                          <Button type="text" danger icon={<DeleteOutlined />} onClick={() => remove(field.name)} />
                        </Col>
                      </Row>
                    </Card>
                  ))}
                  <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({})}>新增教育经历</Button>
                </>
              )}
            </Form.List>
          </Form.Item>
          <Form.Item label="工作经历">
            <Form.List name="work_experience">
              {(fields, { add, remove }) => (
                <>
                  {fields.map((field) => (
                    <Card key={field.key} size="small" style={{ marginBottom: 8 }}>
                      <Row gutter={8} align="middle">
                        <Col flex="1 1 170px">
                          <Form.Item {...field} name={[field.name, 'company']} label="公司"><Input /></Form.Item>
                        </Col>
                        <Col flex="1 1 140px">
                          <Form.Item {...field} name={[field.name, 'position']} label="职位"><Input /></Form.Item>
                        </Col>
                        <Col flex="0 1 110px">
                          <Form.Item {...field} name={[field.name, 'start']} label="开始时间"><Input /></Form.Item>
                        </Col>
                        <Col flex="0 1 110px">
                          <Form.Item {...field} name={[field.name, 'end']} label="结束时间"><Input /></Form.Item>
                        </Col>
                        <Col flex="0 0 32px">
                          <Button type="text" danger icon={<DeleteOutlined />} onClick={() => remove(field.name)} />
                        </Col>
                        <Col span={24}>
                          <Form.Item {...field} name={[field.name, 'desc']} label="工作内容"><Input.TextArea rows={2} /></Form.Item>
                        </Col>
                      </Row>
                    </Card>
                  ))}
                  <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({})}>新增工作经历</Button>
                </>
              )}
            </Form.List>
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title="加入人才库"
        open={poolModalOpen}
        onCancel={() => setPoolModalOpen(false)}
        onOk={async () => {
          if (!id) return;
          await addToPool({
            candidate_id: Number(id),
            category: poolCategory || undefined,
            reason: poolReason || undefined,
            source: 'manual',
          });
          msg.success('已加入人才库');
          setPoolModalOpen(false);
          fetchPool({ candidate_id: Number(id), page_size: 1 }).then((d) => setPoolEntry(d.list[0] ?? null));
        }}
      >
        <p>分类</p>
        <Select
          style={{ width: '100%', marginBottom: 12 }} allowClear placeholder="选择分类"
          value={poolCategory || undefined}
          onChange={(v) => setPoolCategory(v ?? '')}
          options={[
            { value: 'tech', label: '技术类' }, { value: 'product', label: '产品类' },
            { value: 'sales', label: '销售类' }, { value: 'general', label: '综合类' },
          ]}
        />
        <p>加入原因</p>
        <Input.TextArea rows={2} value={poolReason} onChange={(e) => setPoolReason(e.target.value)} />
      </Modal>
    </div>
  );
}
