import { Button, Card, Input, InputNumber, Select, Space, Switch, Table, Tabs, Tag } from 'antd';
import { useCallback, useEffect, useState } from 'react';

import { PageLoading } from '@/components/PageLoading';
import { msg } from '@/utils/message';
import { useCurrentUser } from '@/services/user';
import {
  DICT_TYPE_OPTIONS, createDict, fetchDicts, fetchOfferApprovers, fetchPlatformUsers,
  fetchSystemParams, updateDict, updateOfferApprovers, updateSystemParams,
} from '@/services/system';
import type { DictItem, OfferApproverConfig, PlatformUser } from '@/services/system';
import { STAGE_META } from '@/services/template';

function OfferApproverTab({ canEdit }: { canEdit: boolean }) {
  const [config, setConfig] = useState<OfferApproverConfig | null>(null);
  const [users, setUsers] = useState<PlatformUser[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchOfferApprovers(), fetchPlatformUsers()])
      .then(([cfg, us]) => {
        setConfig(cfg);
        setUsers(us);
        setValues({
          org_approver_id: cfg.org_approver.user_id,
          gm_id: cfg.gm.user_id,
          chairman_id: cfg.chairman.user_id,
          offer_sender_id: cfg.offer_sender.user_id,
        });
      })
      .finally(() => setLoading(false));
  }, []);

  async function save() {
    setSaving(true);
    try {
      const next = await updateOfferApprovers({
        org_approver_id: values.org_approver_id,
        gm_id: values.gm_id,
        chairman_id: values.chairman_id,
        offer_sender_id: values.offer_sender_id,
      });
      setConfig(next);
      msg.success('审批人配置已保存，立即生效');
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <PageLoading />;

  const fields: { key: keyof typeof values; label: string }[] = [
    { key: 'org_approver_id', label: '组织统筹审批人' },
    { key: 'gm_id', label: '总经理审批人' },
    { key: 'chairman_id', label: '董事长审批人' },
    { key: 'offer_sender_id', label: 'Offer 发送专人' },
  ];

  return (
    <div className="hrats-block">
      <p style={{ color: 'rgba(23,26,29,0.6)' }}>
        固定审批链：HR提交录用 → 组织统筹审批 → 总经理审批 → 董事长审批 → Offer专人发送。
        变更立即生效，不影响进行中审批的历史节点归属。
        {config?.updated_at ? <Tag>最近更新：{config.updated_at}</Tag> : null}
      </p>
      {fields.map((f) => (
        <div key={f.key} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <span style={{ width: 140 }}>{f.label}</span>
          <Select
            style={{ width: 280 }}
            disabled={!canEdit}
            value={values[f.key] || undefined}
            placeholder="选择平台成员"
            showSearch
            optionFilterProp="label"
            onChange={(v) => setValues((prev) => ({ ...prev, [f.key]: v }))}
            options={users.map((u) => ({
              value: u.user_id,
              label: `${u.name}（${u.role_name} · ${u.dept_name}）`,
            }))}
          />
        </div>
      ))}
      {canEdit && (
        <Button type="primary" loading={saving} onClick={() => void save()}>
          保存审批人配置
        </Button>
      )}
    </div>
  );
}

function ParamsTab({ canEdit }: { canEdit: boolean }) {
  const [lockDays, setLockDays] = useState<Record<string, number>>({});
  const [checklist, setChecklist] = useState<string[]>([]);
  const [newItem, setNewItem] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchSystemParams()
      .then((data) => {
        setLockDays(data.lock_days_default ?? {});
        setChecklist(data.onboarding_checklist_default ?? []);
      })
      .finally(() => setLoading(false));
  }, []);

  async function save() {
    setSaving(true);
    try {
      await updateSystemParams([
        { key: 'lock_days_default', value: lockDays },
        { key: 'onboarding_checklist_default', value: checklist },
      ]);
      msg.success('系统参数已保存，立即生效');
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <PageLoading />;

  const rows = STAGE_META.map((m) => ({
    key: m.key,
    name: m.name,
    category: m.category,
    days: lockDays[m.key] ?? 0,
  }));

  return (
    <div>
      <Card title="各阶段锁定期默认天数（0 = 不锁定）" size="small" style={{ marginBottom: 16 }}>
        <Table
          rowKey="key"
          size="small"
          pagination={false}
          dataSource={rows}
          columns={[
            { title: '阶段', dataIndex: 'name', width: 140 },
            { title: '环节类型', dataIndex: 'category', width: 120 },
            {
              title: '锁定天数', dataIndex: 'days', width: 160,
              render: (v: number, record: { key: string }) => (
                <InputNumber
                  size="small" min={0} value={v} disabled={!canEdit}
                  onChange={(n) => setLockDays((prev) => ({ ...prev, [record.key]: n ?? 0 }))}
                />
              ),
            },
          ]}
        />
      </Card>
      <Card title="入职资料清单默认条目" size="small" style={{ marginBottom: 16 }}>
        <Space wrap style={{ marginBottom: 12 }}>
          {checklist.map((item) => (
            <Tag
              key={item}
              closable={canEdit}
              onClose={() => setChecklist((prev) => prev.filter((v) => v !== item))}
            >
              {item}
            </Tag>
          ))}
        </Space>
        {canEdit && (
          <Space.Compact style={{ width: 320 }}>
            <Input
              placeholder="新增清单项"
              value={newItem}
              onChange={(e) => setNewItem(e.target.value)}
              onPressEnter={() => {
                const v = newItem.trim();
                if (!v) return;
                if (checklist.includes(v)) {
                  msg.error('该条目已存在');
                  return;
                }
                setChecklist((prev) => [...prev, v]);
                setNewItem('');
              }}
            />
            <Button
              onClick={() => {
                const v = newItem.trim();
                if (!v) return;
                if (checklist.includes(v)) {
                  msg.error('该条目已存在');
                  return;
                }
                setChecklist((prev) => [...prev, v]);
                setNewItem('');
              }}
            >
              添加
            </Button>
          </Space.Compact>
        )}
      </Card>
      {canEdit && (
        <Button type="primary" loading={saving} onClick={() => void save()}>
          保存系统参数
        </Button>
      )}
    </div>
  );
}

function DictTab({ canEdit }: { canEdit: boolean }) {
  const [type, setType] = useState('source_channel');
  const [items, setItems] = useState<DictItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [code, setCode] = useState('');
  const [name, setName] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchDicts(type));
    } finally {
      setLoading(false);
    }
  }, [type]);

  useEffect(() => {
    void load();
  }, [load]);

  async function add() {
    if (!code.trim() || !name.trim()) {
      msg.error('编码与名称必填');
      return;
    }
    await createDict({ type, code: code.trim(), name: name.trim() });
    msg.success('已新增字典条目');
    setCode('');
    setName('');
    void load();
  }

  return (
    <div className="hrats-block">
      <Space style={{ marginBottom: 12 }} wrap>
        <span>字典类型</span>
        <Select
          style={{ width: 200 }}
          value={type}
          onChange={setType}
          options={DICT_TYPE_OPTIONS}
        />
      </Space>
      {loading ? (
        <PageLoading />
      ) : (
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={items}
          columns={[
            { title: '编码', dataIndex: 'code', width: 180 },
            { title: '名称', dataIndex: 'name' },
            {
              title: '状态', dataIndex: 'enabled', width: 100,
              render: (v: boolean, record: DictItem) => (
                <Switch
                  size="small" checked={v} disabled={!canEdit}
                  checkedChildren="启用" unCheckedChildren="停用"
                  onChange={async (c) => {
                    await updateDict(record.id, { enabled: c });
                    msg.success(c ? '已启用' : '已停用（不影响历史数据）');
                    void load();
                  }}
                />
              ),
            },
          ]}
        />
      )}
      {canEdit && (
        <Space style={{ marginTop: 12 }} wrap>
          <Input placeholder="编码" style={{ width: 160 }} value={code} onChange={(e) => setCode(e.target.value)} />
          <Input placeholder="名称" style={{ width: 200 }} value={name} onChange={(e) => setName(e.target.value)} />
          <Button type="primary" onClick={() => void add()}>新增条目</Button>
        </Space>
      )}
    </div>
  );
}

export function SettingsPage() {
  const { user } = useCurrentUser();
  const canEdit = user?.role === 'super_admin';

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">系统设置</h2>
      </div>
      <div className="hrats-block">
        {!canEdit && (
          <Tag color="gold" style={{ marginBottom: 12 }}>
            当前为只读视图，系统设置仅由超级管理员维护。
          </Tag>
        )}
        <Tabs
          defaultActiveKey="approvers"
          items={[
            { key: 'approvers', label: 'Offer 审批人', children: <OfferApproverTab canEdit={canEdit} /> },
            { key: 'params', label: '系统参数', children: <ParamsTab canEdit={canEdit} /> },
            { key: 'dicts', label: '字典管理', children: <DictTab canEdit={canEdit} /> },
          ]}
        />
      </div>
    </div>
  );
}
