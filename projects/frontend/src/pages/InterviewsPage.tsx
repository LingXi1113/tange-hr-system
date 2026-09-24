import { PlusOutlined } from '@ant-design/icons';
import {
  Button, DatePicker, Drawer, Form, Input, InputNumber, Modal,
  Select, Space, Table, Tag,
} from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { assignJob, directInterview, fetchCandidate, fetchCandidates } from '@/services/candidate';
import { fetchJobs } from '@/services/job';
import type { Job } from '@/services/job';
import { fetchEvalTemplates } from '@/services/template';
import {
  INTERVIEW_ROUND_OPTIONS, INTERVIEW_STATUS_TEXT, INTERVIEW_TYPE_TEXT,
  completeInterview, fetchInterview, fetchInterviews,
  rescheduleInterview, saveFeedback, saveInterview,
} from '@/services/interview';
import type { Interview } from '@/services/interview';
import { http, unwrap } from '@/services/http';
import { fetchPlatformUsers } from '@/services/system';
import type { PlatformUser } from '@/services/system';
import { msg } from '@/utils/message';
import { useCurrentUser } from '@/services/user';

const TIME_FMT = 'YYYY-MM-DD HH:mm';

interface AppOption {
  id: number;
  job_id: number;
  job_name: string;
  current_stage: string;
  status: string;
  interview_round?: string;
}

const INTERVIEW_STAGE_KEYS = new Set([
  'pending_interview', 'interviewing',
  'interview_1', 'interview_2', 'interview_3', 'hr_interview', 're_interview',
]);

export function InterviewsPage() {
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const canHrManage = Boolean(user && (user.role === 'hr' || user.role === 'super_admin'
    || user.roles?.some((role) => role === 'hr' || role === 'super_admin')));
  const [searchParams] = useSearchParams();
  const [list, setList] = useState<Interview[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    status: '', round: '', interviewer: '',
    action_state: searchParams.get('action_state') ?? '',
    job_id: searchParams.get('job_id') ? Number(searchParams.get('job_id')) : undefined,
    status_group: searchParams.get('status_group') ?? '', page: 1,
  });

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingJobId, setEditingJobId] = useState<number | null>(null);
  const [form] = Form.useForm();
  const [candidates, setCandidates] = useState<{ id: number; name: string }[]>([]);
  const [appOptions, setAppOptions] = useState<AppOption[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [evalTemplates, setEvalTemplates] = useState<{ id: number; name: string }[]>([]);
  const [interviewers, setInterviewers] = useState<PlatformUser[]>([]);
  const [saving, setSaving] = useState(false);

  const [rescheduleTarget, setRescheduleTarget] = useState<Interview | null>(null);
  const [rescheduleForm] = Form.useForm();
  const [feedbackTarget, setFeedbackTarget] = useState<Interview | null>(null);
  const [feedbackForm] = Form.useForm();
  const feedbackConclusion = Form.useWatch('conclusion', feedbackForm) as string | undefined;
  const [feedbackSaving, setFeedbackSaving] = useState(false);
  const [roundLocked, setRoundLocked] = useState(false);
  const autoOpenedCandidate = useRef<number | null>(null);
  const autoOpenedInterview = useRef<number | null>(null);

  const roundForApplication = (application?: Pick<AppOption, 'current_stage' | 'interview_round'>) => {
    if (!application) return undefined;
    if (application.interview_round && INTERVIEW_ROUND_OPTIONS.includes(application.interview_round)) {
      return application.interview_round;
    }
    const stageRounds: Record<string, string> = {
      interview_1: '一面', interview_2: '二面', interview_3: '三面',
      hr_interview: 'HR面试', re_interview: '复试',
    };
    return stageRounds[application.current_stage];
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchInterviews({
        status: filters.status || undefined,
        round: filters.round || undefined,
        interviewer: filters.interviewer || undefined,
        action_state: filters.action_state || undefined,
        job_id: filters.job_id || undefined,
        status_group: filters.status_group || undefined,
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
    setEditingJobId(null);
    if (!interviewers.length) {
      setInterviewers((await fetchPlatformUsers()).filter((item) =>
        item.role === 'interviewer' || item.role === 'business_screener'));
    }
    if (!candidates.length) {
      setCandidates((await fetchCandidates({ page_size: 100 })).list.map((c) => ({ id: c.id, name: c.name })));
    }
    if (!evalTemplates.length) {
      setEvalTemplates((await fetchEvalTemplates({ page: 1 })).list.map((t) => ({ id: t.id, name: t.name })));
    }
    await loadJobs();
    if (record) {
      const detail = await fetchInterview(record.id);
      await loadAppOptions(detail.candidate_id);
      setEditingJobId(detail.job_id);
      setRoundLocked(Boolean(detail.application_id));
      form.setFieldsValue({
        ...detail,
        start_at: dayjs(detail.start_at),
        end_at: dayjs(detail.end_at),
      });
    } else {
      form.resetFields();
      setAppOptions([]);
      setRoundLocked(false);
      setEditingJobId(null);
    }
    setDrawerOpen(true);
  }

  const loadAppOptions = useCallback(async (candidateId: number) => {
    const resp = await http.get(`/api/candidates/${candidateId}/applications`);
    const apps = unwrap<AppOption[]>(resp);
    const activeApps = apps.filter((a) =>
      a.status === 'in_progress' && INTERVIEW_STAGE_KEYS.has(a.current_stage));
    setAppOptions(activeApps);
    return activeApps;
  }, []);

  const loadJobs = useCallback(async () => {
    if (jobs.length) return jobs;
    const data = await fetchJobs({ page: 1, page_size: 100 });
    setJobs(data.list);
    return data.list;
  }, [jobs]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const openEditorForCandidate = useCallback(async (candidateId: number, applicationId?: number) => {
    setEditingId(null);
    setEditingJobId(null);
    if (!interviewers.length) {
      setInterviewers((await fetchPlatformUsers()).filter((item) =>
        item.role === 'interviewer' || item.role === 'business_screener'));
    }
    if (!candidates.length) {
      const candidateRows = (await fetchCandidates({ page_size: 100 })).list;
      setCandidates(candidateRows.map((c) => ({ id: c.id, name: c.name })));
    }
    if (!evalTemplates.length) {
      setEvalTemplates((await fetchEvalTemplates({ page: 1 })).list.map((t) => ({ id: t.id, name: t.name })));
    }
    const candidate = await fetchCandidate(candidateId);
    setCandidates((current) => current.some((item) => item.id === candidateId)
      ? current
      : [...current, { id: candidate.id, name: candidate.name }]);
    const activeApps = await loadAppOptions(candidateId);
    if (!activeApps.length) await loadJobs();
    const selectedApplicationId = activeApps.some((app) => app.id === applicationId)
      ? applicationId
      : activeApps.length === 1 ? activeApps[0].id : undefined;
    const selectedApplication = candidate.applications.find((app) => app.id === selectedApplicationId)
      || activeApps.find((app) => app.id === selectedApplicationId);
    form.resetFields();
    form.setFieldsValue({
      candidate_id: candidateId,
      // 新建面试由职位选择驱动，保存时再创建/绑定应聘记录。
      application_id: undefined,
      job_id: selectedApplication?.job_id,
      round: roundForApplication(selectedApplication) || INTERVIEW_ROUND_OPTIONS[0],
    });
    setRoundLocked(false);
    setDrawerOpen(true);
  }, [candidates.length, evalTemplates.length, form, interviewers.length, loadAppOptions, loadJobs]);

  useEffect(() => {
    const interviewId = Number(searchParams.get('interview_id'));
    if (interviewId && autoOpenedInterview.current !== interviewId) {
      autoOpenedInterview.current = interviewId;
      void fetchInterview(interviewId).then((detail) => {
        if (searchParams.get('feedback') === '1') {
          return openFeedback(detail);
        }
        return openEditor(detail);
      }).catch(() => {
        autoOpenedInterview.current = null;
      });
      return;
    }
    const candidateId = Number(searchParams.get('candidate_id'));
    const applicationId = Number(searchParams.get('application_id')) || undefined;
    if (!candidateId || autoOpenedCandidate.current === candidateId) return;
    autoOpenedCandidate.current = candidateId;
    void openEditorForCandidate(candidateId, applicationId).catch(() => {
      autoOpenedCandidate.current = null;
    });
  }, [openEditor, openEditorForCandidate, searchParams]);

  async function handleSave() {
    const values = await form.validateFields();
    let applicationId = values.application_id as number | undefined;
    const candidateId = Number(values.candidate_id);
    const jobId = Number(values.job_id);
    if (editingId && editingJobId && jobId !== editingJobId) {
      // 更换职位时不能继续使用原应聘记录，改为切换到新职位对应的记录。
      applicationId = undefined;
    }
    if (!applicationId) {
      if (!candidateId || !jobId) {
        msg.error('安排面试前请选择职位');
        return;
      }
      const existingApplication = appOptions.find((item) => item.job_id === jobId);
      if (existingApplication) {
        applicationId = existingApplication.id;
      } else {
        const application = await assignJob(candidateId, jobId, 'interview_arrangement');
        const enteredInterview = await directInterview(application.id, application.version);
        applicationId = enteredInterview.id;
      }
    }
    const startAt = values.start_at as Dayjs;
    const endAt = values.end_at as Dayjs | undefined;
    const payload = {
      ...values,
      application_id: applicationId,
      start_at: startAt.format(TIME_FMT),
      // 面试时长统一按 1 小时处理，结束时间由系统自动生成。
      end_at: (endAt?.isValid() ? endAt : startAt.add(1, 'hour')).format(TIME_FMT),
    };
    setSaving(true);
    try {
      const saveId = editingId && editingJobId === jobId ? editingId : null;
      await saveInterview(saveId, payload);
      msg.success(saveId ? '面试已更新' : '面试已创建');
      setDrawerOpen(false);
      void load();
    } finally {
      setSaving(false);
    }
  }

  async function openFeedback(record: Interview) {
    const detail = await fetchInterview(record.id);
    setFeedbackTarget(detail);
    feedbackForm.setFieldsValue({
      version: detail.feedback?.version,
      conclusion: detail.feedback?.conclusion,
      comment: detail.feedback?.comment,
      risk_note: detail.feedback?.risk_note,
      dimensions: detail.feedback?.dimension_scores ?? [],
    });
  }

  async function handleFeedbackSave() {
    if (!feedbackTarget) return;
    const values = await feedbackForm.validateFields();
    setFeedbackSaving(true);
    try {
      await saveFeedback(feedbackTarget.id, {
        version: feedbackTarget.feedback?.version,
        conclusion: values.conclusion,
        comment: values.comment ?? '',
        risk_note: values.risk_note ?? '',
        dimension_scores: (values.dimensions || [])
          .filter((d: { name?: string }) => d?.name)
          .map((d: { name: string; score: number }) => ({ name: d.name, score: d.score ?? 3 })),
      });
      if (feedbackTarget.status !== 'cancelled') {
        await completeInterview(feedbackTarget.id, feedbackTarget.version);
      }
      msg.success(values.conclusion === 'pass'
        ? '评价已提交，候选人保留在当前阶段；招聘 HR 可手动调整后续环节'
        : '评价已提交，候选人保留在当前阶段');
      setFeedbackTarget(null);
      void load();
    } finally {
      setFeedbackSaving(false);
    }
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
      title: '当前环节', width: 170,
      render: (_: unknown, r: Interview) => (
        <Space size={4} wrap>
          <Tag color={r.process_state_key === 'interview_evaluated' ? 'success'
            : r.process_state_key === 'awaiting_interviewer_feedback' ? 'gold' : 'blue'}>
            {r.process_state_label || INTERVIEW_STATUS_TEXT[r.status] || r.status}
          </Tag>
          <span style={{ color: 'rgba(23,26,29,0.45)', fontSize: 12 }}>
            {INTERVIEW_STATUS_TEXT[r.status] ?? r.status}
          </span>
        </Space>
      ),
    },
    {
      title: '反馈', dataIndex: 'has_feedback', width: 70,
      render: (v: boolean) => (v ? <Tag color="success">已填</Tag> : <Tag>未填</Tag>),
    },
    {
      title: '操作', width: 220, fixed: 'right' as const,
      render: (_: unknown, r: Interview) => (
        <Space size={2}>
          {r.status !== 'cancelled' && (canHrManage || user?.user_id === r.interviewer_id) && (
            <Button size="small" type="link" onClick={() => void openFeedback(r)}>
              {r.has_feedback ? '修改评价' : '提交评价'}
            </Button>
          )}
          {canHrManage && r.status === 'completed' && r.feedback_conclusion === 'pass' && (
            <Button size="small" type="link" onClick={() => navigate(`/candidates/${r.candidate_id}`)}>
              调整阶段
            </Button>
          )}
          {canHrManage && <Button size="small" type="link" onClick={() => void openEditor(r)}>编辑</Button>}
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
            onChange={(v) => setFilters((f) => ({
              ...f, status: v ?? '', status_group: '', page: 1,
            }))}
            options={Object.entries(INTERVIEW_STATUS_TEXT).map(([value, label]) => ({ value, label }))}
          />
          <Select
            placeholder="职位" allowClear showSearch optionFilterProp="label" style={{ width: 220 }}
            value={filters.job_id}
            onChange={(v) => setFilters((f) => ({ ...f, job_id: v, page: 1 }))}
            options={jobs.map((job) => ({ value: job.id, label: job.name }))}
          />
          <Select
            placeholder="轮次" allowClear style={{ width: 130 }}
            value={filters.round || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, round: v ?? '', page: 1 }))}
            options={INTERVIEW_ROUND_OPTIONS.map((r) => ({ value: r, label: r }))}
          />
          <Select
            placeholder="当前处理状态" allowClear style={{ width: 170 }}
            value={filters.action_state || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, action_state: v ?? '', page: 1 }))}
            options={[
              { value: 'awaiting_interview_schedule', label: '待安排面试' },
              { value: 'awaiting_interview', label: '待参加面试' },
              { value: 'awaiting_interviewer_feedback', label: '待评价（面试官/HR）' },
            ]}
          />
          <Input.Search
            placeholder="面试官" allowClear style={{ width: 180 }}
            onSearch={(v) => setFilters((f) => ({ ...f, interviewer: v, page: 1 }))}
          />
          {filters.status_group && (
            <Tag
              color="blue" closable
              onClose={() => setFilters((current) => ({ ...current, status_group: '', page: 1 }))}
            >
              当前子分类：{filters.status_group === 'interviewed' ? '已参加面试' : '已邀约面试'}
            </Tag>
          )}
        </Space>
        {loading ? <PageLoading /> : (
          <Table
            rowKey="id" size="middle" columns={columns} dataSource={list} scroll={{ x: 1050 }}
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
          <Form.Item name="application_id" hidden><Input /></Form.Item>
          <Form.Item name="candidate_id" label="候选人" rules={[{ required: true, message: '必填' }]}>
            <Select
              showSearch optionFilterProp="label" placeholder="选择候选人"
              options={candidates.map((c) => ({ value: c.id, label: c.name }))}
              onChange={(v) => {
                form.setFieldsValue({ application_id: undefined, job_id: undefined });
                form.setFieldValue('round', INTERVIEW_ROUND_OPTIONS[0]);
                setRoundLocked(false);
                void loadAppOptions(v);
                void loadJobs();
              }}
            />
          </Form.Item>
          <Form.Item name="job_id" label="职位" rules={[{ required: true, message: '请选择职位' }]}>
            <Select
              showSearch optionFilterProp="label"
              placeholder="选择面试职位"
              options={jobs.map((job) => ({
                value: job.id,
                label: `${job.name}${job.dept_name ? `（${job.dept_name}）` : ''}`,
              }))}
              onChange={(value: number) => {
                const application = appOptions.find((item) => item.job_id === value);
                const round = roundForApplication(application)
                  || (value === editingJobId ? form.getFieldValue('round') : INTERVIEW_ROUND_OPTIONS[0]);
                if (round) form.setFieldValue('round', round);
                setRoundLocked(Boolean(editingId && value === editingJobId && round));
              }}
            />
          </Form.Item>
          <Space style={{ width: '100%' }} styles={{ item: { width: '50%' } }}>
            <Form.Item name="round" label="面试轮次" rules={[{ required: true, message: '必填' }]} style={{ width: '100%' }}>
              <Select
                disabled={roundLocked}
                options={INTERVIEW_ROUND_OPTIONS.map((r) => ({ value: r, label: r }))}
              />
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
            <Form.Item name="interviewer_id" label="面试业务人员" rules={[{ required: true, message: '请选择面试业务人员' }]} style={{ width: '100%' }}>
              <Select
                showSearch optionFilterProp="label" placeholder="选择面试业务人员"
                options={interviewers.map((item) => ({ value: item.user_id, label: `${item.name}（${item.role_name}）` }))}
              />
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
        title={`提交面试评价：${feedbackTarget?.candidate_name ?? ''} ${feedbackTarget?.round ?? ''}`}
        open={!!feedbackTarget} width={620}
        onCancel={() => setFeedbackTarget(null)}
        footer={[
          <Button key="save" type="primary" loading={feedbackSaving} onClick={() => void handleFeedbackSave()}>
            提交评价
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
          <Form.Item name="comment" label={feedbackConclusion === 'fail' ? '淘汰原因' : '评价内容'} rules={feedbackConclusion === 'fail' ? [{ required: true, message: '请填写淘汰原因' }] : []}>
            <Input.TextArea rows={2} />
          </Form.Item>
          {feedbackConclusion !== 'fail' && (
            <Form.Item name="risk_note" label="风险提示">
              <Input.TextArea rows={2} />
            </Form.Item>
          )}
          <Form.Item label="评价人">
            <Input value={user?.name || ''} disabled />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
