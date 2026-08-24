import { CopyOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Button, Drawer, Form, Input, InputNumber, Popconfirm, Select, Space, Table, Tag,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { fetchRequirements } from '@/services/requirement';
import { fetchPipelineTemplates } from '@/services/template';
import type { PipelineTemplate } from '@/services/template';
import {
  JOB_STATUS_TEXT, copyJob, fetchJobs, jobAction, saveJob,
} from '@/services/job';
import type { Job } from '@/services/job';
import { msg } from '@/utils/message';
import { downloadProtectedFile } from '@/services/http';
import { useCurrentUser } from '@/services/user';

const JOB_TYPES = [
  { value: 'full_time', label: '全职' }, { value: 'part_time', label: '兼职' },
  { value: 'intern', label: '实习' }, { value: 'outsource', label: '外包' },
];
const INTERVIEW_ROUNDS = [
  { value: '一面', label: '一面' }, { value: '二面', label: '二面' },
  { value: '三面', label: '三面' }, { value: 'HR面试', label: 'HR面试' },
  { value: '复试', label: '复试' },
];

export function JobsPage() {
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const canManage = user?.role === 'hr';
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
        status: filters.status || undefined, keyword: filters.keyword || undefined,
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

  async function openEditor(record: Job | null) {
    setEditingId(record?.id ?? null);
    if (record) {
      form.setFieldsValue({ ...record, interview_rounds: record.interview_rounds?.length ? record.interview_rounds : ['一面'] });
    } else {
      form.resetFields();
      form.setFieldsValue({ interview_rounds: ['一面'] });
    }
    if (!templates.length) setTemplates((await fetchPipelineTemplates(1, 50)).list);
    if (!requirements.length) {
      setRequirements((await fetchRequirements({ page_size: 100 })).list.map((r) => ({ id: r.id, name: r.name })));
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

  const actionsOf = (job: Job) => {
    const map: Record<string, { action: string; label: string }[]> = {
      draft: [{ action: 'submit', label: '提交发布' }],
      pending_publish: [{ action: 'publish', label: '发布' }],
      recruiting: [{ action: 'pause', label: '暂停' }, { action: 'close', label: '关闭' }],
      paused: [{ action: 'resume', label: '恢复' }, { action: 'close', label: '关闭' }],
      closed: [],
    };
    return map[job.status] ?? [];
  };

  const columns = [
    { title: '职位名称', dataIndex: 'name', render: (v: string, r: Job) => <a onClick={() => navigate(`/jobs/${r.id}`)}>{v}</a> },
    { title: '编码', dataIndex: 'code', width: 140 },
    { title: '部门', dataIndex: 'dept_name', width: 120 },
    { title: '类型', dataIndex: 'job_type', width: 80, render: (v: string) => JOB_TYPES.find((t) => t.value === v)?.label ?? v },
    { title: '人数', dataIndex: 'headcount', width: 70 },
    { title: '状态', dataIndex: 'status', width: 100, render: (v: string) => <Tag color={v === 'recruiting' ? 'success' : 'gold'}>{JOB_STATUS_TEXT[v] ?? v}</Tag> },
    { title: '负责人', dataIndex: 'owner_name', width: 90 },
    {
      title: '操作', width: 240, fixed: 'right' as const,
      render: (_: unknown, record: Job) => (
        canManage ? <Space size={4} wrap>
          <Button size="small" type="link" onClick={() => void openEditor(record)}>编辑</Button>
          <Button
            size="small" type="link" icon={<CopyOutlined />}
            onClick={async () => {
              await copyJob(record.id);
              msg.success('已复制职位');
              void load();
            }}
          >
            复制
          </Button>
          {actionsOf(record).map((a) => (
            <Popconfirm
              key={a.action} title={`确认${a.label}？`}
              onConfirm={async () => {
                await jobAction(record.id, a.action);
                msg.success(`已${a.label}`);
                void load();
              }}
            >
              <Button size="small" type="link">{a.label}</Button>
            </Popconfirm>
          ))}
        </Space> : null
      ),
    },
  ];

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">职位管理</h2>
          {canManage && <Button type="primary" icon={<PlusOutlined />} onClick={() => void openEditor(null)}>新建职位</Button>}
      </div>
      <div className="hrats-block">
        <Space style={{ marginBottom: 12 }} wrap>
          <Input.Search
            placeholder="职位名称/编码" allowClear style={{ width: 220 }}
            onSearch={(v) => setFilters((f) => ({ ...f, keyword: v, page: 1 }))}
          />
          <Select
            placeholder="状态" allowClear style={{ width: 140 }}
            value={filters.status || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, status: v ?? '', page: 1 }))}
            options={Object.entries(JOB_STATUS_TEXT).map(([value, label]) => ({ value, label }))}
          />
        {canManage && <Button onClick={() => void downloadProtectedFile('/api/jobs/export', 'jobs.csv')}>导出</Button>}
        </Space>
        {loading ? <PageLoading /> : (
          <Table
            rowKey="id" size="middle" columns={columns} dataSource={list} scroll={{ x: 1100 }}
            pagination={{
              current: filters.page, pageSize: 10, total,
              onChange: (page) => setFilters((f) => ({ ...f, page })),
            }}
          />
        )}
      </div>

      <Drawer
        title={editingId ? '编辑职位' : '新建职位'} width={600}
        forceRender
        open={drawerOpen} onClose={() => setDrawerOpen(false)}
        extra={<Button type="primary" loading={saving} onClick={() => void handleSave()}>保存</Button>}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="职位名称" rules={[{ required: true, message: '必填' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="code" label="职位编码（留空自动生成）">
            <Input />
          </Form.Item>
          <Form.Item name="dept_name" label="所属部门">
            <Input />
          </Form.Item>
          <Form.Item name="requirement_id" label="关联招聘需求（可留空为临时职位）">
            <Select allowClear showSearch optionFilterProp="label"
              options={requirements.map((r) => ({ value: r.id, label: r.name }))} />
          </Form.Item>
          <Form.Item name="template_id" label="招聘流程模板">
            <Select allowClear options={templates.map((t) => ({ value: t.id, label: t.name }))} />
          </Form.Item>
          <Form.Item name="interview_rounds" label="面试轮次（按顺序执行）" rules={[{ required: true, message: '至少选择一轮面试' }]}>
            <Select mode="multiple" options={INTERVIEW_ROUNDS} placeholder="例如：一面、二面、三面" />
          </Form.Item>
          <Space style={{ width: '100%' }} styles={{ item: { width: '33%' } }}>
            <Form.Item name="job_type" label="职位类型" style={{ width: '100%' }}>
              <Select options={JOB_TYPES} />
            </Form.Item>
            <Form.Item name="level" label="职级" style={{ width: '100%' }}>
              <Input />
            </Form.Item>
            <Form.Item name="headcount" label="招聘人数" style={{ width: '100%' }}>
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
          </Space>
          <Form.Item name="location" label="工作地点">
            <Input />
          </Form.Item>
          <Form.Item name="salary_range" label="薪资范围">
            <Input placeholder="例如：25k-40k" />
          </Form.Item>
          <Form.Item name="report_to" label="汇报对象">
            <Input />
          </Form.Item>
          <Form.Item name="skill_tags" label="关键能力标签（逗号分隔）">
            <Input />
          </Form.Item>
          <Form.Item name="description" label="职位描述">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="qualification" label="任职资格">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
