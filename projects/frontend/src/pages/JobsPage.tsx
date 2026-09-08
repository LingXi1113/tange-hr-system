import {
  Button, Drawer, Form, Input, InputNumber, Select, Space, Table,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { fetchRequirements } from '@/services/requirement';
import { fetchPipelineTemplates } from '@/services/template';
import type { PipelineTemplate } from '@/services/template';
import {
  fetchJobs, saveJob,
} from '@/services/job';
import type { Job } from '@/services/job';
import { msg } from '@/utils/message';
import { downloadProtectedFile } from '@/services/http';
import { useCurrentUser } from '@/services/user';

const JOB_TYPES = [
  { value: 'full_time', label: '全职' }, { value: 'part_time', label: '兼职' },
  { value: 'intern', label: '实习' }, { value: 'outsource', label: '外包' },
];
export function JobsPage() {
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const canManage = user?.role === 'hr';
  const [list, setList] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ keyword: '', page: 1 });
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
        keyword: filters.keyword || undefined,
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
      form.setFieldsValue(record);
    } else {
      form.resetFields();
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

  const columns = [
    { title: '职位名称', dataIndex: 'name', render: (v: string, r: Job) => <a onClick={() => navigate(`/jobs/${r.id}`)}>{v}</a> },
    { title: '编码', dataIndex: 'code', width: 140 },
    { title: '部门', dataIndex: 'dept_name', width: 120 },
    { title: '类型', dataIndex: 'job_type', width: 80, render: (v: string) => JOB_TYPES.find((t) => t.value === v)?.label ?? v },
    { title: '人数', dataIndex: 'headcount', width: 70 },
    { title: '负责人', dataIndex: 'owner_name', width: 90 },
    {
      title: '操作', width: 90, fixed: 'right' as const,
      render: (_: unknown, record: Job) => (
        canManage ? <Space size={4} wrap>
          <Button size="small" type="link" onClick={() => void openEditor(record)}>编辑</Button>
        </Space> : null
      ),
    },
  ];

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">职位管理</h2>
        <span style={{ color: 'rgba(23,26,29,0.6)' }}>固定职位目录 · HR 可关联全部职位</span>
      </div>
      <div className="hrats-block">
        <Space style={{ marginBottom: 12 }} wrap>
          <Input.Search
            placeholder="职位名称/编码" allowClear style={{ width: 220 }}
            onSearch={(v) => setFilters((f) => ({ ...f, keyword: v, page: 1 }))}
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
        title="编辑职位" width={600}
        forceRender
        open={drawerOpen} onClose={() => setDrawerOpen(false)}
        extra={<Button type="primary" loading={saving} onClick={() => void handleSave()}>保存</Button>}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="职位名称" rules={[{ required: true, message: '必填' }]}> 
            <Input disabled />
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
