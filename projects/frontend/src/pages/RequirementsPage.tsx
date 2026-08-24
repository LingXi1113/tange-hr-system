import { PlusOutlined } from '@ant-design/icons';
import {
  Button, DatePicker, Drawer, Form, Input, InputNumber, Popconfirm, Select,
  Space, Table, Tag,
} from 'antd';
import dayjs from 'dayjs';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { fetchDepartments, fetchPlatformUsers } from '@/services/system';
import type { PlatformDepartment, PlatformUser } from '@/services/system';
import {
  REQ_STATUS_TEXT, fetchRequirements, requirementAction, saveRequirement,
} from '@/services/requirement';
import type { Requirement } from '@/services/requirement';
import { fetchJobs } from '@/services/job';
import type { Job } from '@/services/job';
import { msg } from '@/utils/message';
import { useCurrentUser } from '@/services/user';

const PRIORITY_OPTIONS = [
  { value: 'high', label: '高' }, { value: 'mid', label: '中' }, { value: 'low', label: '低' },
];
const TYPE_OPTIONS = [
  { value: 'new_headcount', label: '新增编制' },
  { value: 'replacement', label: '替补' },
  { value: 'temp_project', label: '临时项目' },
];

export function RequirementsPage() {
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const canManage = user?.role === 'hr';
  const [list, setList] = useState<Requirement[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ status: '', priority: '', keyword: '', page: 1 });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form] = Form.useForm();
  const [users, setUsers] = useState<PlatformUser[]>([]);
  const [departments, setDepartments] = useState<PlatformDepartment[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchRequirements({
        status: filters.status || undefined,
        priority: filters.priority || undefined,
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

  async function openEditor(record: Requirement | null) {
    setEditingId(record?.id ?? null);
    if (record) {
      form.setFieldsValue({
        ...record,
        job_id: record.job_id ?? undefined,
        due_date: record.due_date ? dayjs(record.due_date) : null,
      });
    } else {
      form.resetFields();
    }
    if (!users.length) setUsers(await fetchPlatformUsers());
    if (!departments.length) setDepartments(await fetchDepartments());
    if (!jobs.length) setJobs((await fetchJobs({ page_size: 100 })).list);
    setDrawerOpen(true);
  }

  async function handleSave(submit: boolean) {
    const values = await form.validateFields().catch(() => null);
    if (!values) {
      if (submit) return;
      msg.error('请至少填写需求名称');
    }
    const payload = {
      ...values,
      due_date: values?.due_date ? dayjs(values.due_date).format('YYYY-MM-DD') : '',
      save_as_draft: !submit,
    };
    setSaving(true);
    try {
      await saveRequirement(editingId, payload);
      msg.success(submit ? '已提交，进入招聘中' : '草稿已保存');
      setDrawerOpen(false);
      void load();
    } finally {
      setSaving(false);
    }
  }

  async function doAction(record: Requirement, action: string, label: string) {
    await requirementAction(record.id, action);
    msg.success(`已${label}`);
    void load();
  }

  const actionsOf = (record: Requirement) => {
    const btns: { action: string; label: string; danger?: boolean }[] = [];
    if (record.status === 'draft') btns.push({ action: 'submit', label: '提交' });
    if (record.status === 'pending_confirm') {
      btns.push({ action: 'confirm', label: '确认' }, { action: 'close', label: '关闭', danger: true });
    }
    if (record.status === 'recruiting') {
      btns.push({ action: 'pause', label: '暂停' }, { action: 'complete', label: '完成' }, { action: 'close', label: '关闭', danger: true });
    }
    if (record.status === 'paused') {
      btns.push({ action: 'resume', label: '恢复' }, { action: 'close', label: '关闭', danger: true });
    }
    return btns;
  };

  const columns = [
    { title: '需求名称', dataIndex: 'name', render: (v: string, r: Requirement) => <a onClick={() => navigate(`/requirements/${r.id}`)}>{v}</a> },
    { title: '部门', dataIndex: 'dept_name', width: 120 },
    { title: '人数', dataIndex: 'headcount', width: 70 },
    { title: '类型', dataIndex: 'request_type', width: 100, render: (v: string) => TYPE_OPTIONS.find((t) => t.value === v)?.label ?? v },
    { title: '优先级', dataIndex: 'priority', width: 80, render: (v: string) => PRIORITY_OPTIONS.find((p) => p.value === v)?.label ?? v },
    { title: '状态', dataIndex: 'status', width: 90, render: (v: string) => <Tag color={v === 'recruiting' ? 'success' : v === 'closed' ? 'default' : 'gold'}>{REQ_STATUS_TEXT[v] ?? v}</Tag> },
    { title: '负责人', dataIndex: 'owner_name', width: 90 },
    { title: '期望到岗', dataIndex: 'due_date', width: 110 },
    {
      title: '操作', width: 220, fixed: 'right' as const,
      render: (_: unknown, record: Requirement) => (
        canManage ? <Space size={4} wrap>
          <Button size="small" type="link" onClick={() => void openEditor(record)}>编辑</Button>
          {actionsOf(record).map((a) => (
            <Popconfirm
              key={a.action}
              title={`确认${a.label}该需求？`}
              onConfirm={() => void doAction(record, a.action, a.label)}
            >
              <Button size="small" type="link" danger={a.danger}>{a.label}</Button>
            </Popconfirm>
          ))}
        </Space> : null
      ),
    },
  ];

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">招聘需求</h2>
        {canManage && <Button type="primary" icon={<PlusOutlined />} onClick={() => void openEditor(null)}>
          新建需求
        </Button>}
      </div>
      <div className="hrats-block">
        <Space style={{ marginBottom: 12 }} wrap>
          <Input.Search
            placeholder="需求名称" allowClear style={{ width: 200 }}
            onSearch={(v) => setFilters((f) => ({ ...f, keyword: v, page: 1 }))}
          />
          <Select
            placeholder="状态" allowClear style={{ width: 130 }}
            value={filters.status || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, status: v ?? '', page: 1 }))}
            options={Object.entries(REQ_STATUS_TEXT).map(([value, label]) => ({ value, label }))}
          />
          <Select
            placeholder="优先级" allowClear style={{ width: 130 }}
            value={filters.priority || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, priority: v ?? '', page: 1 }))}
            options={PRIORITY_OPTIONS}
          />
        </Space>
        {loading ? <PageLoading /> : (
          <Table
            rowKey="id" size="middle" columns={columns} dataSource={list}
            scroll={{ x: 1100 }}
            pagination={{
              current: filters.page, pageSize: 10, total,
              onChange: (page) => setFilters((f) => ({ ...f, page })),
            }}
          />
        )}
      </div>

      <Drawer
        title={editingId ? '编辑招聘需求' : '新建招聘需求'}
        forceRender
        width={560} open={drawerOpen} onClose={() => setDrawerOpen(false)}
        extra={
          <Space>
            <Button onClick={() => void handleSave(false)} loading={saving}>保存草稿</Button>
            <Button type="primary" onClick={() => void handleSave(true)} loading={saving}>提交</Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="需求名称" rules={[{ required: true, message: '必填' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="dept_id" label="所属部门" rules={[{ required: true, message: '必填' }]}>
            <Select
              showSearch optionFilterProp="label" placeholder="取自即先平台部门"
              options={departments.map((d) => ({ value: d.dept_id, label: d.name }))}
              onChange={(v) => {
                const dept = departments.find((d) => d.dept_id === v);
                form.setFieldsValue({ dept_name: dept?.name ?? '' });
              }}
            />
          </Form.Item>
          <Form.Item name="dept_name" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="job_id" label="关联职位（保存后生效）" extra="已关联其他招聘需求的职位不可重复关联">
            <Select
              allowClear showSearch optionFilterProp="label" placeholder="关联已有职位"
              options={jobs.map((j) => ({
                value: j.id,
                label: `${j.name}（${j.code}）${j.requirement_id && j.requirement_id !== editingId ? '（已关联其他需求）' : ''}`,
                disabled: Boolean(j.requirement_id && j.requirement_id !== editingId),
              }))}
            />
          </Form.Item>
          <Form.Item name="headcount" label="招聘人数" rules={[{ required: true, message: '必填' }]}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="request_type" label="需求类型" rules={[{ required: true, message: '必填' }]}>
            <Select options={TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="priority" label="优先级" rules={[{ required: true, message: '必填' }]}>
            <Select options={PRIORITY_OPTIONS} />
          </Form.Item>
          <Form.Item name="due_date" label="期望到岗日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="owner_id" label="负责人">
            <Select
              allowClear showSearch optionFilterProp="label" placeholder="默认当前 HR"
              options={users.map((u) => ({ value: u.user_id, label: `${u.name}（${u.role_name}）` }))}
            />
          </Form.Item>
          <Form.Item name="reason" label="需求原因">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="requirements" label="任职要求" rules={[{ required: true, message: '必填' }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
