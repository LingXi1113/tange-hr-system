import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  MoreOutlined,
  PlusOutlined,
  RightOutlined,
  ShareAltOutlined,
  StopOutlined,
} from '@ant-design/icons';
import {
  Button, Drawer, Dropdown, Empty, Form, Input, Modal, Pagination, Select, Space, Spin, Tag, Tooltip,
} from 'antd';
import type { MenuProps } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { downloadProtectedFile } from '@/services/http';
import {
  JOB_STATUS_TEXT, copyJob, deleteJob, fetchJobs, jobAction, saveJob, shareJob,
} from '@/services/job';
import type { Job } from '@/services/job';
import { fetchRequirements } from '@/services/requirement';
import { fetchPipelineTemplates } from '@/services/template';
import type { PipelineTemplate } from '@/services/template';
import { useCurrentUser } from '@/services/user';
import { msg } from '@/utils/message';

const JOB_TYPES = [
  { value: 'full_time', label: '正式' },
  { value: 'part_time', label: '兼职' },
  { value: 'intern', label: '实习' },
  { value: 'outsource', label: '外包' },
];

const INTERVIEW_ROUNDS = [
  { value: '一面', label: '一面' },
  { value: '二面', label: '二面' },
  { value: '三面', label: '三面' },
  { value: 'HR面试', label: 'HR面试' },
  { value: '复试', label: '复试' },
];

const ENTITY_OPTIONS = [
  { value: 'entity-shuze', label: '广东数则科技有限公司' },
  { value: 'entity-zhenai', label: '真爱美家' },
];

const DEPARTMENT_OPTIONS = [
  { value: 'dept-general', label: '总经办' },
  { value: 'dept-rd', label: '研发部' },
  { value: 'dept-market', label: '市场部' },
  { value: 'dept-solution', label: '方案部' },
  { value: 'dept-channel', label: '渠道部' },
  { value: 'dept-international', label: '国际部' },
  { value: 'dept-organization', label: '组织部' },
  { value: 'dept-ecology', label: '生态部' },
  { value: 'dept-sales', label: '销售部' },
];

const PROGRESS_ITEMS: { key: keyof Job['progress']; label: string }[] = [
  { key: 'received', label: '接收简历' },
  { key: 'invited', label: '面试邀约' },
  { key: 'interviewed', label: '参加面试' },
  { key: 'offered', label: '发送 Offer' },
  { key: 'pending_onboard', label: '待入职' },
  { key: 'onboarded', label: '已入职' },
];

function progressRoute(jobId: number, key: keyof Job['progress']) {
  const encodedJobId = encodeURIComponent(String(jobId));
  if (key === 'received') return `/candidates?job_id=${encodedJobId}`;
  if (key === 'invited') return `/interviews?job_id=${encodedJobId}&status_group=invited`;
  if (key === 'interviewed') return `/interviews?job_id=${encodedJobId}&status_group=interviewed`;
  if (key === 'offered') return `/offers?job_id=${encodedJobId}&status_group=sent_history`;
  if (key === 'pending_onboard') {
    return `/onboarding?job_id=${encodedJobId}&application_stage=pending_onboard`;
  }
  return `/onboarding?job_id=${encodedJobId}&application_stage=onboarded`;
}

function recommendedDepartment(positionName: string) {
  const name = positionName.trim().toLowerCase();
  if (['seo', '在线客服', '舆情管控', '市场专员'].some((value) => name.includes(value.toLowerCase()))) return 'dept-market';
  if (['产品经理', '前端开发', '后台开发', '后端开发'].some((value) => name.includes(value))) return 'dept-rd';
  if (['图文', '视频'].some((value) => name.includes(value))) return 'dept-ecology';
  if (['方案顾问', 'bd'].some((value) => name.includes(value.toLowerCase()))) return 'dept-sales';
  return '';
}

export function JobsPage() {
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const canCreate = user?.role === 'hr';
  const [list, setList] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ status: '', keyword: '', page: 1 });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form] = Form.useForm();
  const [templates, setTemplates] = useState<PipelineTemplate[]>([]);
  const [requirements, setRequirements] = useState<{ id: number; name: string }[]>([]);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchJobs({
        status: filters.status || undefined,
        keyword: filters.keyword || undefined,
        page: filters.page,
        page_size: 10,
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

  const isOwner = (job: Job) => canCreate && job.owner_id === user?.user_id;

  async function openEditor(record: Job | null) {
    if (record && !isOwner(record)) {
      msg.warning('只有创建该职位的 HR 可以修改，当前账号仅可审阅');
      return;
    }
    setEditingId(record?.id ?? null);
    if (record) {
      form.setFieldsValue({
        ...record,
        interview_rounds: record.interview_rounds?.length ? record.interview_rounds : ['一面'],
      });
    } else {
      form.resetFields();
      form.setFieldsValue({
        entity_id: 'entity-shuze',
        entity_name: '广东数则科技有限公司',
        job_type: 'full_time',
        interview_rounds: ['一面'],
      });
    }
    if (!templates.length) setTemplates((await fetchPipelineTemplates(1, 50)).list);
    if (!requirements.length) {
      const data = await fetchRequirements({ page_size: 100 });
      setRequirements(data.list.map((item) => ({ id: item.id, name: item.name })));
    }
    setDrawerOpen(true);
  }

  async function handleSave() {
    const values = await form.validateFields();
    setSaving(true);
    try {
      await saveJob(editingId, values);
      msg.success('职位已保存');
      setDrawerOpen(false);
      void load();
    } finally {
      setSaving(false);
    }
  }

  function statusAction(job: Job) {
    if (job.status === 'draft') return { action: 'submit', label: '提交发布' };
    if (job.status === 'pending_publish') return { action: 'publish', label: '发布' };
    if (job.status === 'recruiting') return { action: 'pause', label: '暂停' };
    if (job.status === 'paused') return { action: 'resume', label: '恢复' };
    return null;
  }

  async function runStatusAction(job: Job) {
    const action = statusAction(job);
    if (!action) return;
    await jobAction(job.id, action.action);
    msg.success(`已${action.label}`);
    void load();
  }

  function confirmClose(job: Job) {
    Modal.confirm({
      title: '确认关闭当前职位？',
      content: '关闭后职位将停止招聘，历史候选人和流程数据会保留。',
      okText: '确认关闭',
      cancelText: '取消',
      onOk: async () => {
        await jobAction(job.id, 'close');
        msg.success('职位已关闭');
        void load();
      },
    });
  }

  function confirmDelete(job: Job) {
    Modal.confirm({
      title: '确认删除当前职位？',
      content: '只有尚无候选人记录的职位可以删除，删除后不可恢复。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await deleteJob(job.id);
        msg.success('职位已删除');
        void load();
      },
    });
  }

  function operationMenu(job: Job): MenuProps {
    return {
      items: [
        { key: 'edit', icon: <EditOutlined />, label: '编辑' },
        { key: 'copy', icon: <CopyOutlined />, label: '复制' },
        {
          key: 'close', icon: <StopOutlined />, label: '关闭',
          disabled: !['recruiting', 'paused'].includes(job.status),
        },
        {
          key: 'share', icon: <ShareAltOutlined />,
          label: job.shared_to_super_admin ? '已共享' : '共享',
          disabled: job.shared_to_super_admin,
        },
        {
          key: 'delete', icon: <DeleteOutlined />, label: '删除', danger: true,
          disabled: job.progress.received > 0,
        },
      ],
      onClick: ({ key }) => {
        if (key === 'edit') void openEditor(job);
        if (key === 'copy') {
          void copyJob(job.id).then(() => {
            msg.success('已复制职位');
            void load();
          });
        }
        if (key === 'close') confirmClose(job);
        if (key === 'share') {
          void shareJob(job.id).then(() => {
            msg.success('已共享给超级管理员');
            void load();
          });
        }
        if (key === 'delete') confirmDelete(job);
      },
    };
  }

  return (
    <div className="jobs-page">
      <div className="page-head">
        <h2 className="page-title">职位管理</h2>
        {canCreate && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => void openEditor(null)}>
            新建职位
          </Button>
        )}
      </div>

      <div className="hrats-block jobs-toolbar">
        <Space wrap>
          <Input.Search
            placeholder="职位名称/职位编码"
            allowClear
            style={{ width: 260 }}
            onSearch={(value) => setFilters((current) => ({ ...current, keyword: value, page: 1 }))}
          />
          <Select
            placeholder="职位状态"
            allowClear
            style={{ width: 150 }}
            value={filters.status || undefined}
            onChange={(value) => setFilters((current) => ({ ...current, status: value ?? '', page: 1 }))}
            options={Object.entries(JOB_STATUS_TEXT).map(([value, label]) => ({ value, label }))}
          />
          {canCreate && <Button onClick={() => void downloadProtectedFile('/api/jobs/export', 'jobs.csv')}>导出</Button>}
        </Space>
      </div>

      <Spin spinning={loading}>
        <div className="job-card-list">
          {!loading && list.length === 0 && <Empty description="暂无职位" />}
          {list.map((job) => {
            const nextAction = statusAction(job);
            const owner = isOwner(job);
            return (
              <article className="job-management-card" key={job.id}>
                <header className="job-management-head">
                  <button type="button" className="job-management-title" onClick={() => navigate(`/jobs/${job.id}`)}>
                    <strong>{job.name}</strong>
                    <Tag color={job.status === 'recruiting' ? 'success' : job.status === 'closed' ? 'default' : 'gold'}>
                      {JOB_STATUS_TEXT[job.status] ?? job.status}
                    </Tag>
                    {job.shared_to_super_admin && <Tag color="blue">已共享</Tag>}
                  </button>
                  <div className="job-management-actions">
                    {owner && nextAction && (
                      <Button size="small" onClick={() => void runStatusAction(job)}>{nextAction.label}</Button>
                    )}
                    <Tooltip title={owner ? '' : '仅创建该职位的 HR 可操作'}>
                      <span>
                        <Dropdown menu={operationMenu(job)} trigger={['click']} disabled={!owner}>
                          <Button size="small">操作 <MoreOutlined /></Button>
                        </Dropdown>
                      </span>
                    </Tooltip>
                  </div>
                </header>

                <div className="job-management-meta">
                  <span>招聘 HR：{job.owner_name || '未设置'}</span>
                  <span>城市：{job.location || '未设置'}</span>
                  <span>用工类型：{(JOB_TYPES.find((item) => item.value === job.job_type)?.label ?? job.job_type) || '未设置'}</span>
                  <span>所属主体：{job.entity_name || '未设置'}</span>
                  <span>所属部门：{job.dept_name || '未设置'}</span>
                </div>

                <div className="job-management-links">
                  <span><b>所属流程</b>{job.template_name || '默认招聘流程'}</span>
                  <span><b>关联需求</b>{job.requirement_name || '未关联招聘需求'}</span>
                </div>

                <div className="job-management-progress">
                  {PROGRESS_ITEMS.map((item, index) => (
                    <span className="job-management-progress-step" key={item.key}>
                      <button
                        type="button"
                        onClick={() => navigate(progressRoute(job.id, item.key))}
                        aria-label={`查看${job.name}的${item.label}`}
                      >
                        <b>{item.label}</b>
                        <strong>{job.progress[item.key]}</strong>
                      </button>
                      {index < PROGRESS_ITEMS.length - 1 && <RightOutlined />}
                    </span>
                  ))}
                </div>
              </article>
            );
          })}
        </div>
      </Spin>

      {total > 10 && (
        <Pagination
          className="jobs-pagination"
          current={filters.page}
          pageSize={10}
          total={total}
          showSizeChanger={false}
          onChange={(page) => setFilters((current) => ({ ...current, page }))}
        />
      )}

      <Drawer
        title={editingId ? '编辑职位' : '新建职位'}
        width={620}
        forceRender
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        extra={<Button type="primary" loading={saving} onClick={() => void handleSave()}>保存</Button>}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="职位名称" rules={[{ required: true, message: '必填' }]}>
            <Input
              onBlur={(event) => {
                const departmentId = recommendedDepartment(event.target.value);
                if (!departmentId || form.getFieldValue('dept_id')) return;
                const department = DEPARTMENT_OPTIONS.find((item) => item.value === departmentId);
                form.setFieldsValue({
                  dept_id: departmentId,
                  dept_name: department?.label ?? '',
                  entity_id: 'entity-shuze',
                  entity_name: '广东数则科技有限公司',
                });
              }}
            />
          </Form.Item>
          <Form.Item name="code" label="职位编码（留空自动生成）"><Input /></Form.Item>
          <Form.Item name="entity_id" label="所属主体" rules={[{ required: true, message: '请选择所属主体' }]}>
            <Select
              options={ENTITY_OPTIONS}
              onChange={(value) => {
                const entity = ENTITY_OPTIONS.find((item) => item.value === value);
                form.setFieldsValue({ entity_name: entity?.label ?? '' });
              }}
            />
          </Form.Item>
          <Form.Item name="entity_name" hidden><Input /></Form.Item>
          <Form.Item name="dept_id" label="所属部门" rules={[{ required: true, message: '请选择所属部门' }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={DEPARTMENT_OPTIONS}
              onChange={(value) => {
                const department = DEPARTMENT_OPTIONS.find((item) => item.value === value);
                form.setFieldsValue({ dept_name: department?.label ?? '' });
              }}
            />
          </Form.Item>
          <Form.Item name="dept_name" hidden><Input /></Form.Item>
          <Form.Item name="template_id" label="所属流程">
            <Select allowClear options={templates.map((item) => ({ value: item.id, label: item.name }))} />
          </Form.Item>
          <Form.Item name="requirement_id" label="关联需求">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={requirements.map((item) => ({ value: item.id, label: item.name }))}
            />
          </Form.Item>
          <Form.Item name="interview_rounds" label="面试轮次" rules={[{ required: true, message: '至少选择一轮面试' }]}>
            <Select mode="multiple" options={INTERVIEW_ROUNDS} />
          </Form.Item>
          <Form.Item name="job_type" label="用工类型"><Select options={JOB_TYPES} /></Form.Item>
          <Form.Item name="location" label="工作城市"><Input /></Form.Item>
          <Form.Item name="level" label="职级"><Input /></Form.Item>
          <Form.Item name="salary_range" label="薪资范围"><Input placeholder="例如：25k-40k" /></Form.Item>
          <Form.Item name="report_to" label="汇报对象"><Input /></Form.Item>
          <Form.Item name="skill_tags" label="关键能力标签（逗号分隔）"><Input /></Form.Item>
          <Form.Item name="description" label="职位描述"><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="qualification" label="任职资格"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
