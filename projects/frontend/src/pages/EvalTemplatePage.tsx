import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Button, Drawer, Form, Input, Popconfirm, Select, Space, Table, Tag,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';

import { PageLoading } from '@/components/PageLoading';
import { msg } from '@/utils/message';
import {
  INTERVIEW_ROUNDS, deleteEvalTemplate, fetchEvalTemplate, fetchEvalTemplates,
  saveEvalTemplate,
} from '@/services/template';
import type { EvalBinding, EvalTemplate } from '@/services/template';

interface BindingRow extends EvalBinding {
  rowKey: string;
}

let seq = 0;
function nextKey() {
  seq += 1;
  return `bind-${seq}`;
}

export function EvalTemplatePage() {
  const [list, setList] = useState<EvalTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [round, setRound] = useState('');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<{ name: string; remark: string; dimensions: string[] }>();
  const [bindings, setBindings] = useState<BindingRow[]>([]);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchEvalTemplates({ keyword, round: round || undefined, page: 1 });
      setList(data.list);
    } finally {
      setLoading(false);
    }
  }, [keyword, round]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  async function openEditor(id: number | null) {
    setEditingId(id);
    if (id) {
      const tpl = await fetchEvalTemplate(id);
      form.setFieldsValue({
        name: tpl.name,
        remark: tpl.remark,
        dimensions: tpl.dimensions?.map((d) => d.name) ?? [],
      });
      setBindings((tpl.bindings ?? []).map((b) => ({ ...b, rowKey: nextKey() })));
    } else {
      form.resetFields();
      form.setFieldsValue({ dimensions: ['专业能力', '沟通表达', '业务理解', '团队协作', '价值观匹配'] });
      setBindings([{ rowKey: nextKey(), job_id: '', job_name: '', round: '一面' }]);
    }
    setDrawerOpen(true);
  }

  async function handleSave() {
    const values = await form.validateFields();
    if (!values.dimensions?.length) {
      msg.error('至少需要一个评分维度');
      return;
    }
    if (!bindings.length) {
      msg.error('至少需要一条关联职位与轮次');
      return;
    }
    setSaving(true);
    try {
      await saveEvalTemplate(editingId, {
        name: values.name,
        remark: values.remark ?? '',
        dimensions: values.dimensions,
        bindings: bindings.map(({ job_id, job_name, round: r }) => ({ job_id, job_name, round: r })),
      });
      msg.success('评价模板已保存');
      setDrawerOpen(false);
      void loadList();
    } finally {
      setSaving(false);
    }
  }

  const columns = [
    { title: '模板名称', dataIndex: 'name' },
    {
      title: '关联职位', dataIndex: 'jobs',
      render: (v: string[]) => (v.length ? v.join('、') : <Tag>通用</Tag>),
    },
    {
      title: '关联轮次', dataIndex: 'rounds',
      render: (v: string[]) => v.join(' / '),
    },
    {
      title: '评分维度', dataIndex: 'dimension_names',
      render: (v: string[]) => v.join(' / '),
    },
    { title: '更新时间', dataIndex: 'updated_at', width: 170 },
    {
      title: '操作', width: 130,
      render: (_: unknown, record: EvalTemplate) => (
        <Space>
          <Button size="small" type="link" onClick={() => void openEditor(record.id)}>编辑</Button>
          <Popconfirm
            title="删除该评价模板？"
            onConfirm={async () => {
              await deleteEvalTemplate(record.id);
              msg.success('已删除');
              void loadList();
            }}
          >
            <Button size="small" type="link" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">面试评价模板配置</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => void openEditor(null)}>
          新建评价模板
        </Button>
      </div>
      <div className="hrats-block">
        <Space style={{ marginBottom: 12 }} wrap>
          <Input.Search
            placeholder="模板名称"
            allowClear
            style={{ width: 220 }}
            onSearch={(v) => setKeyword(v)}
          />
          <Select
            placeholder="面试轮次"
            allowClear
            style={{ width: 160 }}
            value={round || undefined}
            onChange={(v) => setRound(v ?? '')}
            options={INTERVIEW_ROUNDS.map((r) => ({ value: r, label: r }))}
          />
        </Space>
        {loading ? (
          <PageLoading />
        ) : (
          <Table rowKey="id" size="middle" columns={columns} dataSource={list} pagination={false} />
        )}
      </div>

      <Drawer
        title={editingId ? '编辑评价模板' : '新建评价模板'}
        width={680}
        forceRender
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        extra={
          <Button type="primary" loading={saving} onClick={() => void handleSave()}>
            保存
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="模板名称" rules={[{ required: true, message: '请输入模板名称' }]}>
            <Input placeholder="例如：技术序列一面评价表" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input placeholder="选填" />
          </Form.Item>
          <Form.Item
            name="dimensions"
            label="评分维度（各维度 1-5 分）"
            rules={[{ required: true, message: '请配置评分维度' }]}
          >
            <Select
              mode="tags"
              placeholder="输入维度名称后回车，可增删"
              tokenSeparators={[',', '/']}
            />
          </Form.Item>
        </Form>

        <div style={{ marginBottom: 8 }}>关联职位与轮次</div>
        {bindings.map((b) => (
          <Space key={b.rowKey} style={{ display: 'flex', marginBottom: 8 }} align="start">
            <Input
              placeholder="关联职位（职位模块上线后可选）"
              style={{ width: 240 }}
              value={b.job_name}
              onChange={(e) =>
                setBindings((rows) =>
                  rows.map((r) => (r.rowKey === b.rowKey ? { ...r, job_name: e.target.value } : r)),
                )
              }
            />
            <Select
              style={{ width: 140 }}
              value={b.round}
              onChange={(v) =>
                setBindings((rows) =>
                  rows.map((r) => (r.rowKey === b.rowKey ? { ...r, round: v } : r)),
                )
              }
              options={INTERVIEW_ROUNDS.map((r) => ({ value: r, label: r }))}
            />
            <Button
              danger
              icon={<DeleteOutlined />}
              onClick={() => setBindings((rows) => rows.filter((r) => r.rowKey !== b.rowKey))}
            />
          </Space>
        ))}
        <Button
          block type="dashed" icon={<PlusOutlined />}
          onClick={() => setBindings((rows) => [...rows, { rowKey: nextKey(), job_id: '', job_name: '', round: '一面' }])}
        >
          添加关联
        </Button>
      </Drawer>
    </div>
  );
}
