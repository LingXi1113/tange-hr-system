import {
  Alert, Button, Card, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tabs, Tag,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { msg } from '@/utils/message';
import { useCurrentUser } from '@/services/user';
import {
  DICT_TYPE_OPTIONS, createDict, createScreeningMatchItem, deleteScreeningMatchItem,
  fetchDicts, fetchInterviewerQualifications, fetchOfferApprovers, fetchPlatformUsers, fetchScreeningMatchItems,
  fetchSystemParams, updateDict, updateInterviewerQualification, updateOfferApprovers,
  updateScreeningMatchItem, updateSystemParams,
} from '@/services/system';
import type {
  DictItem, OfferApproverConfig, PlatformUser, ScreeningMatchItem,
  ScreeningMatchItemPayload, ScreeningMatchMeta,
} from '@/services/system';
import { STAGE_META } from '@/services/template';

const EMPTY_MATCH_ITEM: ScreeningMatchItemPayload = {
  profile: 'tech',
  name: '',
  weight: 10,
  evaluator: 'custom_terms',
  target_count: 1,
  terms: [],
  enabled: true,
  sort: 999,
};

function ScreeningMatchTab({ canEdit }: { canEdit: boolean }) {
  const [profile, setProfile] = useState<ScreeningMatchItem['profile']>('tech');
  const [meta, setMeta] = useState<ScreeningMatchMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<ScreeningMatchItemPayload>(EMPTY_MATCH_ITEM);
  const [termsText, setTermsText] = useState('');
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setMeta(await fetchScreeningMatchItems(profile));
    } finally {
      setLoading(false);
    }
  }, [profile]);

  useEffect(() => {
    void load();
  }, [load]);

  function startAdd() {
    setEditingId(null);
    setDraft({ ...EMPTY_MATCH_ITEM, profile });
    setTermsText('');
    setOpen(true);
  }

  function startEdit(item: ScreeningMatchItem) {
    setEditingId(item.id);
    setDraft({
      profile: item.profile,
      name: item.name,
      weight: item.weight,
      evaluator: item.evaluator,
      target_count: item.target_count,
      terms: item.terms,
      enabled: item.enabled,
      sort: item.sort,
    });
    setTermsText(item.terms.join('，'));
    setOpen(true);
  }

  async function save() {
    const normalizedTerms = termsText
      .split(/[,，;；\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
    const nextDraft = { ...draft, terms: Array.from(new Set(normalizedTerms)) };
    if (!draft.name.trim()) {
      msg.error('请输入匹配项名称');
      return;
    }
    if (draft.evaluator === 'custom_terms' && nextDraft.terms.length === 0) {
      msg.error('自定义关键词匹配至少需要一个关键词');
      return;
    }
    setSaving(true);
    try {
      if (editingId) {
        await updateScreeningMatchItem(editingId, {
          name: draft.name,
          weight: draft.weight,
          evaluator: draft.evaluator,
          target_count: draft.target_count,
          terms: nextDraft.terms,
          enabled: draft.enabled,
          sort: draft.sort,
        });
        msg.success('匹配项已更新，后续筛选立即使用新规则');
      } else {
        await createScreeningMatchItem(nextDraft);
        msg.success('匹配项已新增，后续筛选立即使用新规则');
      }
      setOpen(false);
      await load();
    } finally {
      setSaving(false);
    }
  }

  const totalWeight = (meta?.items ?? [])
    .filter((item) => item.enabled)
    .reduce((sum, item) => sum + item.weight, 0);

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="这里配置的是智能筛选的评分维度"
        description="按岗位类型分别维护。启用项的分值会自动折算为 100 分；修改后只影响新执行或重新执行的筛选，历史结果保留原评分。"
      />
      <Space wrap style={{ marginBottom: 12 }}>
        <span>岗位类型</span>
        <Select
          value={profile}
          showSearch
          optionFilterProp="label"
          style={{ width: 260 }}
          onChange={setProfile}
          options={['通用模板', '具体岗位'].map((group) => ({
            label: group,
            options: (meta?.profiles ?? [
              { key: 'tech', name: '技术研发', base_profile: 'tech', group: '通用模板' },
              { key: 'product_ops', name: '产品与电商运营', base_profile: 'product_ops', group: '通用模板' },
              { key: 'sales', name: '销售与商务', base_profile: 'sales', group: '通用模板' },
            ]).filter((item) => item.group === group).map((item) => ({
              value: item.key,
              label: item.name,
            })),
          }))}
        />
        <Tag color={Math.abs(totalWeight - 100) < 0.01 ? 'green' : 'gold'}>
          当前启用权重：{totalWeight}
        </Tag>
        {canEdit && <Button type="primary" onClick={startAdd}>新增匹配项</Button>}
      </Space>
      {loading ? <PageLoading /> : (
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={meta?.items ?? []}
          columns={[
            { title: '匹配项', dataIndex: 'name', width: 180 },
            { title: '计算依据', dataIndex: 'evaluator_name', width: 180 },
            { title: '权重', dataIndex: 'weight', width: 90 },
            { title: '达标命中数', dataIndex: 'target_count', width: 110 },
            {
              title: '关键词', dataIndex: 'terms',
              render: (terms: string[], item: ScreeningMatchItem) => (
                item.evaluator === 'custom_terms'
                  ? (terms.length ? terms.join('、') : '未配置')
                  : <span style={{ color: 'rgba(23,26,29,0.55)' }}>使用系统/职位配置</span>
              ),
            },
            {
              title: '启用', dataIndex: 'enabled', width: 80,
              render: (enabled: boolean, item: ScreeningMatchItem) => (
                <Switch
                  size="small"
                  checked={enabled}
                  disabled={!canEdit}
                  onChange={(checked) => {
                    void (async () => {
                      await updateScreeningMatchItem(item.id, { enabled: checked });
                      msg.success(checked ? '匹配项已启用' : '匹配项已停用');
                      await load();
                    })();
                  }}
                />
              ),
            },
            {
              title: '操作', width: 150,
              render: (_: unknown, item: ScreeningMatchItem) => canEdit ? (
                <Space>
                  <Button type="link" size="small" onClick={() => startEdit(item)}>编辑</Button>
                  <Popconfirm
                    title="删除这个匹配项？"
                    description="删除后，新执行的简历筛选将不再计算此项。"
                    onConfirm={() => {
                      void (async () => {
                        await deleteScreeningMatchItem(item.id);
                        msg.success('匹配项已删除');
                        await load();
                      })();
                    }}
                  >
                    <Button type="link" danger size="small">删除</Button>
                  </Popconfirm>
                </Space>
              ) : '-',
            },
          ]}
        />
      )}
      <Modal
        title={editingId ? '编辑智能匹配项' : '新增智能匹配项'}
        open={open}
        confirmLoading={saving}
        onOk={() => void save()}
        onCancel={() => setOpen(false)}
        okText="保存"
        cancelText="取消"
      >
        <div style={{ display: 'grid', gridTemplateColumns: '110px 1fr', gap: '14px 12px', alignItems: 'center' }}>
          <span>匹配项名称</span>
          <Input value={draft.name} onChange={(event) => setDraft((prev) => ({ ...prev, name: event.target.value }))} />
          <span>计算依据</span>
          <Select
            value={draft.evaluator}
            options={(meta?.evaluators ?? []).map((item) => ({ value: item.key, label: item.name }))}
            onChange={(value) => setDraft((prev) => ({ ...prev, evaluator: value }))}
          />
          <span>权重</span>
          <InputNumber
            min={1} max={100} precision={1} value={draft.weight} style={{ width: '100%' }}
            onChange={(value) => setDraft((prev) => ({ ...prev, weight: value ?? 1 }))}
          />
          <span>达标命中数</span>
          <InputNumber
            min={1} max={20} value={draft.target_count} style={{ width: '100%' }}
            onChange={(value) => setDraft((prev) => ({ ...prev, target_count: value ?? 1 }))}
          />
          <span>自定义关键词</span>
          <Input.TextArea
            disabled={draft.evaluator !== 'custom_terms'}
            placeholder={draft.evaluator === 'custom_terms' ? '用逗号分隔，例如：TikTok Shop、亚马逊' : '当前计算依据使用系统词库或职位要求'}
            value={termsText}
            autoSize={{ minRows: 2, maxRows: 4 }}
            onChange={(event) => setTermsText(event.target.value)}
          />
        </div>
      </Modal>
    </div>
  );
}

function OfferApproverTab({ canEdit }: { canEdit: boolean }) {
  const [config, setConfig] = useState<OfferApproverConfig | null>(null);
  const [users, setUsers] = useState<PlatformUser[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void Promise.all([fetchOfferApprovers(), fetchPlatformUsers()])
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

function InterviewerQualificationTab() {
  const [users, setUsers] = useState<PlatformUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [savingUserId, setSavingUserId] = useState('');

  const load = useCallback(async (search = '') => {
    setLoading(true);
    try {
      setUsers(await fetchInterviewerQualifications(search));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggle(user: PlatformUser, enabled: boolean) {
    setSavingUserId(user.user_id);
    try {
      const updated = await updateInterviewerQualification(user.user_id, enabled);
      setUsers((current) => current.map((item) => (
        item.user_id === updated.user_id ? updated : item
      )));
      msg.success(enabled ? `已授予 ${user.name} 面试资格` : `已取消 ${user.name} 的面试资格`);
    } finally {
      setSavingUserId('');
    }
  }

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="面试资格不会改变账号原有主角色"
        description="获得资格后，该账号可被选择为面试官，并能查看获指派候选人的简历、填写和提交面试评价。权限变更立即生效。"
      />
      <Input.Search
        allowClear
        placeholder="按姓名或账号搜索"
        value={keyword}
        onChange={(event) => setKeyword(event.target.value)}
        onSearch={(value) => void load(value.trim())}
        style={{ width: 320, marginBottom: 12 }}
      />
      <Table
        rowKey="user_id"
        size="small"
        loading={loading}
        pagination={false}
        dataSource={users}
        columns={[
          { title: '姓名', dataIndex: 'name', width: 140 },
          { title: '账号', dataIndex: 'user_id', width: 180 },
          { title: '主角色', dataIndex: 'role_name', width: 150 },
          { title: '所属部门', dataIndex: 'dept_name' },
          {
            title: '面试资格', width: 210,
            render: (_, user: PlatformUser) => (
              <Space>
                <Switch
                  checked={Boolean(user.interviewer_qualified)}
                  disabled={Boolean(user.interviewer_inherent)}
                  loading={savingUserId === user.user_id}
                  checkedChildren="已授权"
                  unCheckedChildren="未授权"
                  onChange={(checked) => void toggle(user, checked)}
                />
                {user.interviewer_inherent && <Tag color="blue">平台角色自带</Tag>}
                {!user.interviewer_inherent && user.interviewer_local_enabled && <Tag color="green">管理员授权</Tag>}
              </Space>
            ),
          },
        ]}
      />
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
    void fetchSystemParams()
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
                  onChange={(c) => {
                    void (async () => {
                      await updateDict(record.id, { enabled: c });
                      msg.success(c ? '已启用' : '已停用（不影响历史数据）');
                      await load();
                    })();
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
  const [searchParams, setSearchParams] = useSearchParams();
  const canEdit = user?.role === 'super_admin';
  const canEditScreening = user?.role === 'super_admin' || user?.role === 'hr';
  const requestedTab = searchParams.get('tab');
  const activeTab = requestedTab === 'interviewer-qualification' && canEdit
    ? requestedTab
    : requestedTab && ['approvers', 'params', 'dicts'].includes(requestedTab)
      ? requestedTab
      : 'screening';

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">系统设置</h2>
      </div>
      <div className="hrats-block">
        {!canEdit && !canEditScreening && (
          <Tag color="gold" style={{ marginBottom: 12 }}>
            当前为只读视图，智能匹配项由 HR 维护，其余设置由超级管理员维护。
          </Tag>
        )}
        {!canEdit && canEditScreening && (
          <Tag color="blue" style={{ marginBottom: 12 }}>
            HR 可维护智能匹配项；审批人、系统参数和字典仍为只读。
          </Tag>
        )}
        <Tabs
          activeKey={activeTab}
          onChange={(key) => {
            setSearchParams(key === 'screening' ? {} : { tab: key });
          }}
          items={[
            { key: 'screening', label: '智能匹配项', children: <ScreeningMatchTab canEdit={canEditScreening} /> },
            ...(canEdit ? [{
              key: 'interviewer-qualification',
              label: '面试资格',
              children: <InterviewerQualificationTab />,
            }] : []),
            { key: 'approvers', label: 'Offer 审批人', children: <OfferApproverTab canEdit={canEdit} /> },
            { key: 'params', label: '系统参数', children: <ParamsTab canEdit={canEdit} /> },
            { key: 'dicts', label: '字典管理', children: <DictTab canEdit={canEdit} /> },
          ]}
        />
      </div>
    </div>
  );
}
