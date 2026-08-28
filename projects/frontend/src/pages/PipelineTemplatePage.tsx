import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Button, Drawer, Form, Input, InputNumber, Popconfirm, Select, Space,
  Switch, Table, Tag, Typography,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';

import { PageLoading } from '@/components/PageLoading';
import { useCurrentUser } from '@/services/user';
import { msg } from '@/utils/message';
import {
  fetchPipelineTemplate, fetchPipelineTemplates, savePipelineTemplate,
  setPipelineTemplateStatus, deletePipelineTemplate,
  DEADLINE_BASIS_OPTIONS, EXPIRY_ACTION_OPTIONS, REMINDER_OPTIONS, STAGE_META,
} from '@/services/template';
import type { PipelineTemplate, TemplateStage } from '@/services/template';

interface StageRow extends Omit<TemplateStage, 'id'> {
  rowKey: string;
}

let rowSeq = 0;
function nextKey() {
  rowSeq += 1;
  return `stage-${rowSeq}`;
}

const DEFAULT_RULES: Record<string, Partial<TemplateStage>> = {
  new_resume: { lock_days: 0 },
  pending_screen: { lock_days: 5 },
  business_screen: { lock_days: 5 },
  pending_interview: { lock_days: 7 },
  interviewing: { lock_days: 7, requires_interview: true, requires_feedback: true },
  interview_1: { lock_days: 7, requires_interview: true, requires_feedback: true },
  interview_2: { lock_days: 7, requires_interview: true, requires_feedback: true },
  interview_3: { lock_days: 7, requires_interview: true, requires_feedback: true },
  hr_interview: { lock_days: 7, requires_interview: true, requires_feedback: true },
  interview_passed: { lock_days: 30, unprocessed_days: 15, reminder_days_before: 3, expiry_action: 'eliminated', enter_talent_pool: true },
  offer_approval: { lock_days: 30, unprocessed_days: 15, expiry_action: 'eliminated', enter_talent_pool: true },
  offer_pending: { lock_days: 15 },
  offer: { lock_days: 15 },
  pending_onboard: { lock_days: 45, unprocessed_days: 90, reminder_days_before: 7, expiry_action: 'abandoned', deadline_basis: 'planned_onboard_date', enter_talent_pool: true },
  onboarded: { lock_days: 9999 },
};

function normalizeStage(stage: Partial<TemplateStage>, rowKey: string): StageRow {
  const defaults = DEFAULT_RULES[stage.stage_key ?? ''] ?? {};
  return {
    rowKey,
    stage_key: stage.stage_key ?? '', name: stage.name ?? '', category: stage.category ?? '',
    sort_order: stage.sort_order ?? 0,
    lock_days: stage.lock_days ?? defaults.lock_days ?? 0,
    unprocessed_days: stage.unprocessed_days ?? defaults.unprocessed_days ?? 0,
    reminder_days_before: stage.reminder_days_before ?? 0,
    expiry_action: stage.expiry_action ?? defaults.expiry_action ?? 'none',
    deadline_basis: stage.deadline_basis ?? defaults.deadline_basis ?? 'stage_entered',
    required: stage.required ?? true, skippable: stage.skippable ?? false,
    requires_interview: stage.requires_interview ?? false,
    requires_feedback: stage.requires_feedback ?? false,
    auto_reminder: stage.auto_reminder ?? false,
    enter_talent_pool: stage.enter_talent_pool ?? defaults.enter_talent_pool ?? false,
    reminder_type: stage.reminder_type ?? '', optional_flag: stage.optional_flag ?? false,
  };
}

export function PipelineTemplatePage() {
  const { user } = useCurrentUser();
  const canManage = user?.role === 'super_admin';
  const [templates, setTemplates] = useState<PipelineTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [rulesEnabled, setRulesEnabled] = useState(true);
  const [form] = Form.useForm<{ name: string; remark: string }>();
  const [stages, setStages] = useState<StageRow[]>([]);

  const loadTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchPipelineTemplates(1, 50);
      setTemplates(data.list);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTemplates();
  }, [loadTemplates]);

  async function openEditor(id: number | null) {
    setEditingId(id);
    if (id) {
      const tpl = await fetchPipelineTemplate(id);
      form.setFieldsValue({ name: tpl.name, remark: tpl.remark });
      setRulesEnabled(tpl.stage_rules_enabled !== false);
      const ordered = [...(tpl.stages ?? [])].sort(
        (a, b) => Number(a.optional_flag) - Number(b.optional_flag) || a.sort_order - b.sort_order,
      );
      setStages(ordered.map((s) => normalizeStage(s, nextKey())));
    } else {
      form.resetFields();
      setRulesEnabled(true);
      // 新建默认带出主干阶段（锁定期保存时未填取系统参数默认）
      setStages(
        STAGE_META.filter((m) => !m.optional).map((m, idx) => normalizeStage({
          stage_key: m.key, name: m.name, category: m.category, sort_order: idx + 1,
          required: true, skippable: false, reminder_type: 'enter', optional_flag: false,
          ...DEFAULT_RULES[m.key],
        }, nextKey())),
      );
    }
    setDrawerOpen(true);
  }

  function updateStage(rowKey: string, patch: Partial<StageRow>) {
    setStages((rows) => rows.map((r) => (r.rowKey === rowKey ? { ...r, ...patch } : r)));
  }

  function onStageKeyChange(rowKey: string, stageKey: string) {
    const meta = STAGE_META.find((m) => m.key === stageKey);
    if (!meta) return;
    updateStage(rowKey, {
      stage_key: meta.key,
      name: meta.name,
      category: meta.category,
      optional_flag: meta.optional,
      ...DEFAULT_RULES[meta.key],
    });
  }

  function moveStage(rowKey: string, direction: -1 | 1) {
    setStages((rows) => {
      const index = rows.findIndex((r) => r.rowKey === rowKey);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= rows.length) return rows;
      const next = [...rows];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function handleSave() {
    const values = await form.validateFields();
    if (!stages.length) {
      msg.error('至少需要一个阶段');
      return;
    }
    const mainStages = stages.filter((s) => !s.optional_flag);
    const optionalStages = stages.filter((s) => s.optional_flag);
    const payload = {
      name: values.name,
      remark: values.remark ?? '',
      stage_rules_enabled: rulesEnabled,
      stages: [
        ...mainStages.map((s, idx) => ({ ...s, sort_order: idx + 1 })),
        ...optionalStages.map((s) => ({ ...s, sort_order: 0 })),
      ],
    };
    setSaving(true);
    try {
      await savePipelineTemplate(editingId, payload);
      msg.success('模板已保存');
      setDrawerOpen(false);
      void loadTemplates();
    } finally {
      setSaving(false);
    }
  }

  const columns = [
    { title: '模板名称', dataIndex: 'name' },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => (v === 'active' ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>),
    },
    { title: '阶段数', dataIndex: 'stage_count', width: 90 },
    { title: '更新时间', dataIndex: 'updated_at', width: 170 },
    {
      title: '操作', width: 200,
      render: (_: unknown, record: PipelineTemplate) => canManage ? (
        <Space>
          <Button size="small" type="link" onClick={() => void openEditor(record.id)}>编辑</Button>
          <Button
            size="small" type="link"
            onClick={async () => {
              await setPipelineTemplateStatus(record.id, record.status === 'active' ? 'disabled' : 'active');
              msg.success(record.status === 'active' ? '已停用' : '已启用');
              void loadTemplates();
            }}
          >
            {record.status === 'active' ? '停用' : '启用'}
          </Button>
          <Popconfirm
            title="删除该流程模板？"
            onConfirm={async () => {
              await deletePipelineTemplate(record.id);
              msg.success('已删除');
              void loadTemplates();
            }}
          >
            <Button size="small" type="link" danger>删除</Button>
          </Popconfirm>
        </Space>
      ) : null,
    },
  ];

  const stageColumns = [
    {
      title: '顺序', width: 60,
      render: (_: unknown, record: StageRow) =>
        record.optional_flag
          ? '-'
          : stages.filter((s) => !s.optional_flag).findIndex((s) => s.rowKey === record.rowKey) + 1,
    },
    {
      title: '阶段', dataIndex: 'stage_key', width: 140,
      render: (v: string, record: StageRow) => (
        <Select
          size="small" style={{ width: 128 }} value={v}
          onChange={(key) => onStageKeyChange(record.rowKey, key)}
          options={STAGE_META.map((m) => ({ value: m.key, label: m.name }))}
        />
      ),
    },
    { title: '环节类型', dataIndex: 'category', width: 90 },
    {
      title: '必选', dataIndex: 'required', width: 70,
      render: (v: boolean, record: StageRow) =>
        record.optional_flag ? <Tag>按职位配置</Tag> : (
          <Switch size="small" checked={v} onChange={(c) => updateStage(record.rowKey, { required: c })} />
        ),
    },
    {
      title: '锁定期(天)', dataIndex: 'lock_days', width: 110,
      render: (v: number, record: StageRow) => (
        <InputNumber size="small" min={0} max={9999} value={v} onChange={(n) => updateStage(record.rowKey, { lock_days: n ?? 0 })} />
      ),
    },
    {
      title: '未处理期限', dataIndex: 'unprocessed_days', width: 105,
      render: (v: number, record: StageRow) => (
        <InputNumber size="small" min={0} max={3650} value={v}
          onChange={(n) => updateStage(record.rowKey, { unprocessed_days: n ?? 0 })} />
      ),
    },
    {
      title: '提前提醒(天)', dataIndex: 'reminder_days_before', width: 115,
      render: (v: number, record: StageRow) => (
        <InputNumber size="small" min={0} max={3650} value={v}
          onChange={(n) => updateStage(record.rowKey, { reminder_days_before: n ?? 0 })} />
      ),
    },
    {
      title: '到期动作', dataIndex: 'expiry_action', width: 120,
      render: (v: TemplateStage['expiry_action'], record: StageRow) => (
        <Select size="small" style={{ width: 112 }} value={v}
          onChange={(value) => updateStage(record.rowKey, { expiry_action: value })}
          options={EXPIRY_ACTION_OPTIONS} />
      ),
    },
    {
      title: '期限起算', dataIndex: 'deadline_basis', width: 130,
      render: (v: TemplateStage['deadline_basis'], record: StageRow) => (
        <Select size="small" style={{ width: 122 }} value={v}
          onChange={(value) => updateStage(record.rowKey, { deadline_basis: value })}
          options={DEADLINE_BASIS_OPTIONS} />
      ),
    },
    {
      title: '提醒', dataIndex: 'reminder_type', width: 120,
      render: (v: string, record: StageRow) => (
        <Select
          size="small" style={{ width: 104 }} value={v}
          onChange={(rv) => updateStage(record.rowKey, { reminder_type: rv })}
          options={REMINDER_OPTIONS}
        />
      ),
    },
    {
      title: '规则', width: 300,
      render: (_: unknown, record: StageRow) => (
        <Space size={6} wrap>
          <Switch size="small" checked={record.skippable}
            onChange={(v) => updateStage(record.rowKey, { skippable: v })} />允许跳过
          <Switch size="small" checked={record.requires_interview}
            onChange={(v) => updateStage(record.rowKey, { requires_interview: v })} />需面试
          <Switch size="small" checked={record.requires_feedback}
            onChange={(v) => updateStage(record.rowKey, { requires_feedback: v })} />需反馈
          <Switch size="small" checked={record.auto_reminder}
            onChange={(v) => updateStage(record.rowKey, { auto_reminder: v })} />自动提醒
          <Switch size="small" checked={record.enter_talent_pool}
            onChange={(v) => updateStage(record.rowKey, { enter_talent_pool: v })} />进人才库
        </Space>
      ),
    },
    {
      title: '操作', width: 120,
      render: (_: unknown, record: StageRow) => (
        <Space size={4}>
          <Button size="small" type="link" onClick={() => moveStage(record.rowKey, -1)}>上移</Button>
          <Button size="small" type="link" onClick={() => moveStage(record.rowKey, 1)}>下移</Button>
          <Button
            size="small" type="link" danger icon={<DeleteOutlined />}
            onClick={() => setStages((rows) => rows.filter((r) => r.rowKey !== record.rowKey))}
          />
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">流程模板配置</h2>
        <Button type="primary" icon={<PlusOutlined />} style={{ display: canManage ? undefined : 'none' }} onClick={() => void openEditor(null)}>
          新建流程模板
        </Button>
      </div>
      <div className="hrats-block">
        {!canManage && (
          <Typography.Text type="secondary">
            当前为只读视图，招聘流程由超级管理员统一维护，修改后会同步到所有 HR。
          </Typography.Text>
        )}
        {loading ? (
          <PageLoading />
        ) : (
          <Table
            rowKey="id"
            size="middle"
            columns={columns}
            dataSource={templates}
            pagination={false}
          />
        )}
      </div>

      <Drawer
        title={editingId ? '编辑流程模板' : '新建流程模板'}
        width={1380}
        forceRender
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        extra={
          <Button type="primary" loading={saving} onClick={() => void handleSave()}>
            保存配置
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="模板名称" rules={[{ required: true, message: '请输入模板名称' }]}>
            <Input placeholder="例如：默认招聘流程模板" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input placeholder="选填" />
          </Form.Item>
        </Form>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <Typography.Text strong>启用招聘阶段规则</Typography.Text>
            <Switch checked={rulesEnabled} onChange={setRulesEnabled} />
          </Space>
          <Typography.Text type="secondary">
            锁定天数用于客保；未处理期限到期后执行到期动作。入职日期起算适用于“待入职 90 天”规则。
          </Typography.Text>
        </Space>
        <Table
          rowKey="rowKey"
          size="small"
          style={{ marginTop: 12 }}
          columns={stageColumns}
          dataSource={stages}
          pagination={false}
          scroll={{ x: 1360 }}
        />
        <Button
          block type="dashed" icon={<PlusOutlined />} style={{ marginTop: 12 }}
          onClick={() =>
            setStages((rows) => [
              ...rows,
              {
                ...normalizeStage({
                  stage_key: '', name: '', category: '', sort_order: rows.length + 1,
                  required: true, skippable: false, reminder_type: '', optional_flag: false,
                }, nextKey()),
              },
            ])
          }
        >
          添加阶段
        </Button>
      </Drawer>
    </div>
  );
}
