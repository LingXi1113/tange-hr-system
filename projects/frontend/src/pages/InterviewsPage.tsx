import { PlusOutlined } from '@ant-design/icons';
import {
  Button, Checkbox, DatePicker, Drawer, Form, Input, InputNumber, Modal, Popconfirm,
  Select, Space, Table, Tag,
} from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { useCallback, useEffect, useState } from 'react';

import { PageLoading } from '@/components/PageLoading';
import { fetchCandidate, fetchCandidates } from '@/services/candidate';
import { fetchEvalTemplates } from '@/services/template';
import {
  INTERVIEW_ROUND_OPTIONS, INTERVIEW_STATUS_TEXT, INTERVIEW_TYPE_TEXT,
  applyConclusion, completeInterview, fetchInterview, fetchInterviews,
  interviewAction, rescheduleInterview, saveFeedback, saveInterview,
} from '@/services/interview';
import type { Interview } from '@/services/interview';
import { http, unwrap } from '@/services/http';
import { msg } from '@/utils/message';

const TIME_FMT = 'YYYY-MM-DD HH:mm';

interface AppOption {
  id: number;
  job_name: string;
  current_stage: string;
  status: string;
}

export function InterviewsPage() {
  const [list, setList] = useState<Interview[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ status: '', round: '', interviewer: '', page: 1 });

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form] = Form.useForm();
  const [candidates, setCandidates] = useState<{ id: number; name: string }[]>([]);
  const [appOptions, setAppOptions] = useState<AppOption[]>([]);
  const [evalTemplates, setEvalTemplates] = useState<{ id: number; name: string }[]>([]);
  const [saving, setSaving] = useState(false);

  const [rescheduleTarget, setRescheduleTarget] = useState<Interview | null>(null);
  const [rescheduleForm] = Form.useForm();
  const [feedbackTarget, setFeedbackTarget] = useState<Interview | null>(null);
  const [feedbackForm] = Form.useForm();
  const [feedbackSaving, setFeedbackSaving] = useState(false);
  const [conclusionTarget, setConclusionTarget] = useState<Interview | null>(null);
  const [conclusionReason, setConclusionReason] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchInterviews({
        status: filters.status || undefined,
        round: filters.round || undefined,
        interviewer: filters.interviewer || undefined,
        page: filters.page, page_size: 10,
      });
      setList(data.list);
      setTotal(data.total);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  async function openEditor(record: Interview | null) {
    setEditingId(record?.id ?? null);
    if (!candidates.length) {
      setCandidates((await fetchCandidates({ page_size: 100 })).list.map((c) => ({ id: c.id, name: c.name })));
    }
    if (!evalTemplates.length) {
      setEvalTemplates((await fetchEvalTemplates({ page: 1 })).list.map((t) => ({ id: t.id, name: t.name })));
    }
    if (record) {
      const detail = await fetchInterview(record.id);
      await loadAppOptions(detail.candidate_id);
      form.setFieldsValue({
        ...detail,
        start_at: dayjs(detail.start_at),
        end_at: dayjs(detail.end_at),
      });
    } else {
      form.resetFields();
      setAppOptions([]);
    }
    setDrawerOpen(true);
  }

  async function loadAppOptions(candidateId: number) {
    const resp = await http.get(`/api/candidates/${candidateId}/applications`);
    const apps = unwrap<AppOption[]>(resp);
    setAppOptions(apps.filter((a) => a.status === 'in_progress'));
  }

  async function handleSave() {
    const values = await form.validateFields();
    const startAt = values.start_at as Dayjs;
    const endAt = values.end_at as Dayjs | undefined;
    const payload = {
      ...values,
      start_at: startAt.format(TIME_FMT),
      // 面试时长统一按 1 小时处理，结束时间由系统自动生成。
      end_at: (endAt?.isValid() ? endAt : startAt.add(1, 'hour')).format(TIME_FMT),
    };
    setSaving(true);
    try {
      await saveInterview(editingId, payload);
      msg.success(editingId ? '面试已更新' : '面试已创建');
      setDrawerOpen(false);
      void load();
    } finally {
      setSaving(false);
    }
  }

  async function handleComplete(record: Interview) {
    if (record.has_feedback) {
      await completeInterview(record.id, false, record.version);
      msg.success('面试已完成');
      void load();
      return;
    }
    // 无反馈：打开反馈表单（可选择暂不评价完成）
    setFeedbackTarget(record);
    feedbackForm.resetFields();
  }

  async function handleFeedbackSave(markNoEval: boolean) {
    if (!feedbackTarget) return;
    if (markNoEval) {
      await completeInterview(feedbackTarget.id, true, feedbackTarget.version);
      msg.success('已标记暂不评价并完成面试');
      setFeedbackTarget(null);
      void load();
      return;
    }
    const values = await feedbackForm.validateFields();
    setFeedbackSaving(true);
    try {
      await saveFeedback(feedbackTarget.id, {
        version: feedbackTarget.feedback?.version,
        conclusion: values.conclusion,
        comment: values.comment ?? '',
        risk_note: values.risk_note ?? '',
        suggested_salary: values.suggested_salary ?? '',
        evaluator_name: values.evaluator_name ?? '',
        dimension_scores: (values.dimensions || [])
          .filter((d: { name?: string }) => d?.name)
          .map((d: { name: string; score: number }) => ({ name: d.name, score: d.score ?? 3 })),
      });
      msg.success('反馈已保存');
      if (feedbackTarget.status === 'confirmed') {
        await completeInterview(feedbackTarget.id, false, feedbackTarget.version);
        msg.success('面试已完成');
      }
      setFeedbackTarget(null);
      void load();
    } finally {
      setFeedbackSaving(false);
    }
  }

  async function handleApplyConclusion(pass: boolean) {
    if (!conclusionTarget) return;
    // 取应聘记录当前 version（乐观锁）
    const detail = await fetchCandidate(conclusionTarget.candidate_id);
    const app = detail.applications.find((a) => a.id === conclusionTarget.application_id);
    if (!app) {
      msg.error('应聘记录不存在');
      return;
    }
    if (!pass && !conclusionReason.trim()) {
      msg.error('面试不通过淘汰候选人必须填写原因');
      return;
    }
    const result = await applyConclusion(conclusionTarget.id, {
      version: app.version, reason: conclusionReason.trim() || undefined,
    });
    msg.success(pass
      ? `候选人已推进至：${result.application.current_stage}`
      : '候选人已淘汰');
    setConclusionTarget(null);
    setConclusionReason('');
    void load();
  }

  const columns = [
    { title: '候选人', dataIndex: 'candidate_name', width: 100 },
    { title: '职位', dataIndex: 'job_name', width: 140 },
    { title: '轮次', dataIndex: 'round', width: 80 },
    { title: '类型', dataIndex: 'type', width: 70, render: (v: string) => INTERVIEW_TYPE_TEXT[v] ?? v },
    {
      title: '时间', width: 260,
      render: (_: unknown, r: Interview) => `${r.start_at} ~ ${r.end_at.slice(11)}`,
    },
    { title: '面试官', dataIndex: 'interviewer_name', width: 90 },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => (
        <Tag color={v === 'completed' ? 'success' : v === 'cancelled' ? 'default' : 'gold'}>
          {INTERVIEW_STATUS_TEXT[v] ?? v}
        </Tag>
      ),
    },
    {
      title: '反馈', dataIndex: 'has_feedback', width: 70,
      render: (v: boolean) => (v ? <Tag color="success">已填</Tag> : <Tag>未填</Tag>),
    },
    {
      title: '操作', width: 250, fixed: 'right' as const,
      render: (_: unknown, r: Interview) => (
        <Space size={2} wrap>
          {r.status === 'pending' && (
              <Popconfirm title="发起邀请？" onConfirm={async () => { await interviewAction(r.id, 'invite', r.version); msg.success('已邀请'); void load(); }}>
              <Button size="small" type="link">邀请</Button>
            </Popconfirm>
          )}
          {(r.status === 'invited' || r.status === 'rescheduled') && (
            <Popconfirm title="确认面试？" onConfirm={async () => { await interviewAction(r.id, 'confirm', r.version); msg.success('已确认'); void load(); }}>
              <Button size="small" type="link">确认</Button>
            </Popconfirm>
          )}
          {r.status === 'confirmed' && (
            <Button size="small" type="link" onClick={() => void handleComplete(r)}>完成</Button>
          )}
          {r.status === 'completed' && (
            <>
              <Button
                size="small" type="link"
                onClick={async () => {
                  const detail = await fetchInterview(r.id);
                  setFeedbackTarget(detail);
                  feedbackForm.setFieldsValue({
                    ...(detail.feedback ?? {}),
                    dimensions: detail.feedback?.dimension_scores ?? [],
                  });
                }}
              >
                反馈
              </Button>
              {r.has_feedback && !r.feedback_skip_eval && r.feedback_conclusion !== 'hold' && (
                <Button
                  size="small" type="link"
                  onClick={async () => {
                    const detail = await fetchInterview(r.id);
                    setConclusionTarget(detail);
                  }}
                >
                  应用结论
                </Button>
              )}
            </>
          )}
          {!['completed', 'cancelled'].includes(r.status) && (
            <>
              <Button size="small" type="link" onClick={() => { setRescheduleTarget(r); rescheduleForm.setFieldsValue({ reason: '' }); }}>
                改期
              </Button>
              <Button size="small" type="link" onClick={() => void openEditor(r)}>编辑</Button>
              <Popconfirm title="取消该面试？" onConfirm={async () => { await interviewAction(r.id, 'cancel', r.version); msg.success('已取消'); void load(); }}>
                <Button size="small" type="link" danger>取消</Button>
              </Popconfirm>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">面试管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => void openEditor(null)}>
          安排面试
        </Button>
      </div>
      <div className="hrats-block">
        <Space style={{ marginBottom: 12 }} wrap>
          <Select
            placeholder="状态" allowClear style={{ width: 130 }}
            value={filters.status || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, status: v ?? '', page: 1 }))}
            options={Object.entries(INTERVIEW_STATUS_TEXT).map(([value, label]) => ({ value, label }))}
          />
          <Select
            placeholder="轮次" allowClear style={{ width: 130 }}
            value={filters.round || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, round: v ?? '', page: 1 }))}
            options={INTERVIEW_ROUND_OPTIONS.map((r) => ({ value: r, label: r }))}
          />
          <Input.Search
            placeholder="面试官" allowClear style={{ width: 180 }}
            onSearch={(v) => setFilters((f) => ({ ...f, interviewer: v, page: 1 }))}
          />
        </Space>
        {loading ? <PageLoading /> : (
          <Table
            rowKey="id" size="middle" columns={columns} dataSource={list} scroll={{ x: 1200 }}
            pagination={{
              current: filters.page, pageSize: 10, total,
              onChange: (page) => setFilters((f) => ({ ...f, page })),
            }}
          />
        )}
      </div>

      {/* 新建/编辑抽屉 */}
      <Drawer
        title={editingId ? '编辑面试' : '安排面试'} width={560} forceRender
        open={drawerOpen} onClose={() => setDrawerOpen(false)}
        extra={<Button type="primary" loading={saving} onClick={() => void handleSave()}>保存</Button>}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="version" hidden><Input /></Form.Item>
          <Form.Item name="candidate_id" label="候选人" rules={[{ required: true, message: '必填' }]}>
            <Select
              showSearch optionFilterProp="label" placeholder="选择候选人"
              options={candidates.map((c) => ({ value: c.id, label: c.name }))}
              onChange={(v) => {
                form.setFieldsValue({ application_id: undefined });
                void loadAppOptions(v);
              }}
            />
          </Form.Item>
          <Form.Item name="application_id" label="应聘记录（候选人 + 职位绑定）" rules={[{ required: true, message: '必填' }]}>
            <Select
              placeholder="先选择候选人"
              options={appOptions.map((a) => ({
                value: a.id, label: `${a.job_name} · ${a.current_stage}`,
              }))}
            />
          </Form.Item>
          <Space style={{ width: '100%' }} styles={{ item: { width: '50%' } }}>
            <Form.Item name="round" label="面试轮次" rules={[{ required: true, message: '必填' }]} style={{ width: '100%' }}>
              <Select options={INTERVIEW_ROUND_OPTIONS.map((r) => ({ value: r, label: r }))} />
            </Form.Item>
            <Form.Item name="type" label="面试类型" rules={[{ required: true, message: '必填' }]} style={{ width: '100%' }}>
              <Select options={[
                { value: 'onsite', label: '现场' }, { value: 'video', label: '视频' }, { value: 'phone', label: '电话' },
              ]} />
            </Form.Item>
          </Space>
          <Space className="interview-time-fields" style={{ width: '100%' }} styles={{ item: { width: '50%' } }}>
            <Form.Item name="start_at" label="开始时间" rules={[{ required: true, message: '必填' }]} style={{ width: '100%' }}>
              <DatePicker
                showTime format={TIME_FMT} style={{ width: '100%' }}
                onChange={(value) => form.setFieldValue('end_at', value ? value.add(1, 'hour') : undefined)}
              />
            </Form.Item>
            <Form.Item name="end_at" label="结束时间" rules={[{ required: true, message: '必填' }]} style={{ width: '100%' }}>
              <DatePicker showTime format={TIME_FMT} style={{ width: '100%' }} />
            </Form.Item>
          </Space>
          <Form.Item name="location" label="面试地点">
            <Input placeholder="现场面试地点" />
          </Form.Item>
          <Form.Item name="meeting_link" label="视频会议链接">
            <Input placeholder="视频/电话面试链接" />
          </Form.Item>
          <Space style={{ width: '100%' }} styles={{ item: { width: '50%' } }}>
            <Form.Item name="interviewer_name" label="面试官" rules={[{ required: true, message: '必填' }]} style={{ width: '100%' }}>
              <Input />
            </Form.Item>
            <Form.Item name="interviewer_contact" label="面试官联系方式" style={{ width: '100%' }}>
              <Input />
            </Form.Item>
          </Space>
          <Form.Item name="template_id" label="面试评价模板">
            <Select
              allowClear placeholder="复用现有评价模板"
              options={evalTemplates.map((t) => ({ value: t.id, label: t.name }))}
            />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Drawer>

      {/* 改期弹窗 */}
      <Modal
        title={`改期：${rescheduleTarget?.candidate_name ?? ''} ${rescheduleTarget?.round ?? ''}`}
        open={!!rescheduleTarget}
        onCancel={() => setRescheduleTarget(null)}
        onOk={async () => {
          const values = await rescheduleForm.validateFields();
          if (!rescheduleTarget) return;
          await rescheduleInterview(rescheduleTarget.id, {
            start_at: (values.start_at as Dayjs).format(TIME_FMT),
            end_at: (values.end_at as Dayjs).format(TIME_FMT),
            reason: values.reason,
            version: rescheduleTarget.version,
          });
          msg.success('已改期，原记录保留');
          setRescheduleTarget(null);
          void load();
        }}
      >
        {rescheduleTarget && (
          <p style={{ color: 'rgba(23,26,29,0.6)' }}>
            原时间：{rescheduleTarget.start_at} ~ {rescheduleTarget.end_at.slice(11)}
          </p>
        )}
        <Form form={rescheduleForm} layout="vertical">
          <Space style={{ width: '100%' }} styles={{ item: { width: '50%' } }}>
            <Form.Item name="start_at" label="新开始时间" rules={[{ required: true, message: '必填' }]} style={{ width: '100%' }}>
              <DatePicker showTime format={TIME_FMT} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="end_at" label="新结束时间" rules={[{ required: true, message: '必填' }]} style={{ width: '100%' }}>
              <DatePicker showTime format={TIME_FMT} style={{ width: '100%' }} />
            </Form.Item>
          </Space>
          <Form.Item name="reason" label="改期原因" rules={[{ required: true, message: '必填' }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 反馈弹窗 */}
      <Modal
        title={`面试反馈：${feedbackTarget?.candidate_name ?? ''} ${feedbackTarget?.round ?? ''}`}
        open={!!feedbackTarget} width={620}
        onCancel={() => setFeedbackTarget(null)}
        footer={[
          <Button key="skip" onClick={() => void handleFeedbackSave(true)}>暂不评价并完成</Button>,
          <Button key="save" type="primary" loading={feedbackSaving} onClick={() => void handleFeedbackSave(false)}>
            保存反馈
          </Button>,
        ]}
      >
        <Form form={feedbackForm} layout="vertical">
          <Form.Item name="version" hidden><Input /></Form.Item>
          <Form.List name="dimensions">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => (
                  <Space key={field.key} align="baseline">
                    <Form.Item name={[field.name, 'name']} rules={[{ required: true, message: '维度名' }]}>
                      <Input placeholder="评分维度" />
                    </Form.Item>
                    <Form.Item name={[field.name, 'score']} rules={[{ required: true, message: '分数' }]}>
                      <InputNumber min={1} max={5} placeholder="1-5" />
                    </Form.Item>
                    <Button type="link" danger onClick={() => remove(field.name)}>删除</Button>
                  </Space>
                ))}
                <Button
                  type="dashed" block
                  onClick={() => add({ name: '', score: 3 })}
                >
                  添加评分维度
                </Button>
              </>
            )}
          </Form.List>
          <Form.Item name="conclusion" label="综合结论" rules={[{ required: true, message: '必填' }]} style={{ marginTop: 12 }}>
            <Select options={[
              { value: 'pass', label: '通过' }, { value: 'hold', label: '待定' }, { value: 'fail', label: '不通过' },
            ]} />
          </Form.Item>
          <Form.Item name="comment" label="评价内容">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="risk_note" label="风险提示">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Space style={{ width: '100%' }} styles={{ item: { width: '50%' } }}>
            <Form.Item name="suggested_salary" label="建议薪资" style={{ width: '100%' }}>
              <Input placeholder="例如：30k" />
            </Form.Item>
            <Form.Item name="evaluator_name" label="面试官（代录时填写）" style={{ width: '100%' }}>
              <Input />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      {/* 应用结论弹窗 */}
      <Modal
        title="应用面试结论"
        open={!!conclusionTarget}
        onCancel={() => setConclusionTarget(null)}
        footer={null}
      >
        {conclusionTarget?.feedback && (
          <p>
            结论：
            <Tag color={conclusionTarget.feedback.conclusion === 'pass' ? 'success' : 'error'}>
              {conclusionTarget.feedback.conclusion === 'pass' ? '通过 → 推进至「面试通过」' : '不通过 → 淘汰候选人'}
            </Tag>
          </p>
        )}
        {conclusionTarget?.feedback?.conclusion === 'fail' && (
          <Input.TextArea
            rows={3} placeholder="必填淘汰原因"
            value={conclusionReason} onChange={(e) => setConclusionReason(e.target.value)}
          />
        )}
        <div style={{ marginTop: 12, textAlign: 'right' }}>
          <Button onClick={() => setConclusionTarget(null)} style={{ marginRight: 8 }}>取消</Button>
          <Button
            type="primary"
            danger={conclusionTarget?.feedback?.conclusion === 'fail'}
            onClick={() => void handleApplyConclusion(conclusionTarget?.feedback?.conclusion === 'pass')}
          >
            确认执行
          </Button>
        </div>
      </Modal>
    </div>
  );
}
