import { PlusOutlined, TagOutlined } from '@ant-design/icons';
import {
  Button, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Drawer,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';

import { PageLoading } from '@/components/PageLoading';
import { fetchJobs } from '@/services/job';
import {
  POOL_SOURCE_TEXT, activatePoolEntry, addToPool, batchPoolTags,
  batchRemoveFromPool, fetchPool, removeFromPool, updatePoolEntry,
} from '@/services/talentPool';
import type { PoolEntry } from '@/services/talentPool';
import { msg } from '@/utils/message';
import { useCurrentUser } from '@/services/user';
import { downloadProtectedFile } from '@/services/http';

const CATEGORY_OPTIONS = [
  { value: 'tech', label: '技术类' }, { value: 'product', label: '产品类' },
  { value: 'sales', label: '销售类' }, { value: 'general', label: '综合类' },
];

export function TalentPoolPage() {
  const { user } = useCurrentUser();
  const canManage = user?.role === 'hr';
  const [list, setList] = useState<PoolEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    keyword: '', category: '', tag: '', source: '', status: '', page: 1,
  });
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [jobs, setJobs] = useState<{ id: number; name: string }[]>([]);

  const [editTarget, setEditTarget] = useState<PoolEntry | null>(null);
  const [editForm] = Form.useForm();
  const [activateTarget, setActivateTarget] = useState<PoolEntry | null>(null);
  const [activateJobId, setActivateJobId] = useState<number | null>(null);
  const [batchTagOpen, setBatchTagOpen] = useState(false);
  const [batchTagForm] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchPool({
        keyword: filters.keyword || undefined,
        category: filters.category || undefined,
        tag: filters.tag || undefined,
        source: filters.source || undefined,
        status: filters.status || undefined,
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

  useEffect(() => {
    fetchJobs({ page_size: 100 }).then((d) => setJobs(d.list.map((j) => ({ id: j.id, name: j.name }))));
  }, []);

  const columns = [
    { title: '姓名', dataIndex: 'candidate_name', width: 100 },
    { title: '手机号', dataIndex: 'phone', width: 130 },
    { title: '邮箱', dataIndex: 'email', width: 170 },
    {
      title: '分类', dataIndex: 'category', width: 90,
      render: (v: string) => CATEGORY_OPTIONS.find((c) => c.value === v)?.label ?? v ?? '-',
    },
    {
      title: '标签', dataIndex: 'tags', width: 150,
      render: (v: string[]) => (v?.length ? v.map((t) => <Tag key={t}>{t}</Tag>) : '-'),
    },
    { title: '来源', dataIndex: 'source_text', width: 110 },
    { title: '可推荐职位', dataIndex: 'recommended_job_name', width: 130, render: (v: string) => v || '-' },
    { title: '最近联系', dataIndex: 'last_contact_at', width: 100, render: (v: string) => v?.slice(0, 10) || '-' },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => (v === 'active'
        ? <Tag color="success">待激活</Tag>
        : <Tag color="purple">已激活</Tag>),
    },
    {
      title: '操作', width: 200, fixed: 'right' as const,
      render: (_: unknown, r: PoolEntry) => (
        canManage ? <Space size={2} wrap>
          <Button size="small" type="link" onClick={() => {
            setEditTarget(r);
            editForm.setFieldsValue({
              category: r.category, tags: r.tags, reason: r.reason,
              recommended_job_id: r.recommended_job_id,
              last_contact_at: r.last_contact_at ? r.last_contact_at.slice(0, 10) : '',
            });
          }}>
            维护
          </Button>
          {r.status === 'active' && (
            <Button size="small" type="link" onClick={() => { setActivateTarget(r); setActivateJobId(null); }}>
              重新激活
            </Button>
          )}
          <Popconfirm
            title="确认移出人才库？"
            onConfirm={async () => {
              await removeFromPool(r.id);
              msg.success('已移出人才库');
              void load();
            }}
          >
            <Button size="small" type="link" danger>移出</Button>
          </Popconfirm>
        </Space> : null
      ),
    },
  ];

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">人才库</h2>
        <Space>
          {canManage && <Button
            disabled={!selectedIds.length}
            icon={<TagOutlined />}
            onClick={() => setBatchTagOpen(true)}
          >
            批量改标签
          </Button>}
          {canManage && <Popconfirm
            title={`确认批量移出 ${selectedIds.length} 条记录？`}
            disabled={!selectedIds.length}
            onConfirm={async () => {
              const res = await batchRemoveFromPool(selectedIds);
              msg.success(`已移出 ${res.removed} 条`);
              setSelectedIds([]);
              void load();
            }}
          >
            <Button danger disabled={!selectedIds.length}>批量移出</Button>
          </Popconfirm>}
          {canManage && <Button onClick={() => void downloadProtectedFile('/api/talent-pool/export', 'talent_pool.csv')}>导出</Button>}
        </Space>
      </div>
      <div className="hrats-block">
        <Space style={{ marginBottom: 12 }} wrap>
          <Input.Search
            placeholder="姓名/手机/邮箱" allowClear style={{ width: 200 }}
            onSearch={(v) => setFilters((f) => ({ ...f, keyword: v, page: 1 }))}
          />
          <Select
            placeholder="分类" allowClear style={{ width: 120 }}
            value={filters.category || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, category: v ?? '', page: 1 }))}
            options={CATEGORY_OPTIONS}
          />
          <Input
            placeholder="标签" allowClear style={{ width: 130 }}
            onPressEnter={(e) => setFilters((f) => ({ ...f, tag: (e.target as HTMLInputElement).value, page: 1 }))}
            onBlur={(e) => setFilters((f) => ({ ...f, tag: e.target.value, page: 1 }))}
          />
          <Select
            placeholder="来源" allowClear style={{ width: 140 }}
            value={filters.source || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, source: v ?? '', page: 1 }))}
            options={Object.entries(POOL_SOURCE_TEXT).map(([value, label]) => ({ value, label }))}
          />
          <Select
            placeholder="状态" allowClear style={{ width: 120 }}
            value={filters.status || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, status: v ?? '', page: 1 }))}
            options={[{ value: 'active', label: '待激活' }, { value: 'activated', label: '已激活' }]}
          />
        </Space>
        {loading ? <PageLoading /> : (
          <Table
            rowKey="id" size="middle" columns={columns} dataSource={list} scroll={{ x: 1300 }}
            rowSelection={{
              selectedRowKeys: selectedIds,
              onChange: (keys) => setSelectedIds(keys.map(Number)),
            }}
            pagination={{
              current: filters.page, pageSize: 10, total,
              onChange: (page) => setFilters((f) => ({ ...f, page })),
            }}
          />
        )}
      </div>

      {/* 维护抽屉 */}
      <Drawer
        title={`维护：${editTarget?.candidate_name ?? ''}`} width={480} forceRender
        open={!!editTarget} onClose={() => setEditTarget(null)}
        extra={
          <Button
            type="primary"
            onClick={async () => {
              const values = await editForm.validateFields();
              if (!editTarget) return;
              await updatePoolEntry(editTarget.id, {
                category: values.category ?? '',
                tags: values.tags ?? [],
                reason: values.reason ?? '',
                recommended_job_id: values.recommended_job_id ?? null,
                last_contact_at: values.last_contact_at ?? '',
              });
              msg.success('已更新');
              setEditTarget(null);
              void load();
            }}
          >
            保存
          </Button>
        }
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="category" label="分类">
            <Select allowClear options={CATEGORY_OPTIONS} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="输入后回车" tokenSeparators={[',']} />
          </Form.Item>
          <Form.Item name="recommended_job_id" label="可推荐职位">
            <Select
              allowClear showSearch optionFilterProp="label"
              options={jobs.map((j) => ({ value: j.id, label: j.name }))}
            />
          </Form.Item>
          <Form.Item name="last_contact_at" label="最近联系时间（YYYY-MM-DD）">
            <Input placeholder="2026-08-01" />
          </Form.Item>
          <Form.Item name="reason" label="加入原因">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Drawer>

      {/* 重新激活弹窗 */}
      <Modal
        title={`重新激活：${activateTarget?.candidate_name ?? ''}`}
        open={!!activateTarget}
        onCancel={() => setActivateTarget(null)}
        onOk={async () => {
          if (!activateTarget || !activateJobId) {
            msg.error('请选择目标职位');
            return;
          }
          await activatePoolEntry(activateTarget.id, activateJobId);
          msg.success('已重新激活，候选人进入新职位流程');
          setActivateTarget(null);
          void load();
        }}
      >
        <p style={{ color: 'rgba(23,26,29,0.6)' }}>
          将为候选人新建目标职位的应聘记录（锁定期与重复投递校验仍然生效）。
        </p>
        <Select
          style={{ width: '100%' }} placeholder="选择招聘中的职位"
          showSearch optionFilterProp="label"
          value={activateJobId ?? undefined}
          onChange={(v) => setActivateJobId(v)}
          options={jobs.map((j) => ({ value: j.id, label: j.name }))}
        />
      </Modal>

      {/* 批量改标签弹窗 */}
      <Modal
        title={`批量修改标签（${selectedIds.length} 条）`}
        open={batchTagOpen}
        onCancel={() => setBatchTagOpen(false)}
        onOk={async () => {
          const values = await batchTagForm.validateFields();
          const res = await batchPoolTags(selectedIds, values.tags ?? [], values.mode);
          msg.success(`已更新 ${res.updated} 条`);
          setBatchTagOpen(false);
          setSelectedIds([]);
          void load();
        }}
      >
        <Form form={batchTagForm} layout="vertical" initialValues={{ mode: 'append' }}>
          <Form.Item name="mode" label="修改方式">
            <Select options={[
              { value: 'append', label: '追加（保留原标签）' },
              { value: 'replace', label: '覆盖（替换原标签）' },
            ]} />
          </Form.Item>
          <Form.Item name="tags" label="标签" rules={[{ required: true, message: '必填' }]}>
            <Select mode="tags" placeholder="输入后回车" tokenSeparators={[',']} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
