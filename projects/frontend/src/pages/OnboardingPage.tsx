import { CheckCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Descriptions, Drawer, Progress, Select, Space, Table, Tag, Typography } from 'antd';
import type { TableColumnsType } from 'antd';
import { useCallback, useEffect, useState } from 'react';

import { PageLoading } from '@/components/PageLoading';
import { completeOnboarding, fetchOnboarding, fetchOnboardingDetail, startOnboarding, updateOnboardingItem } from '@/services/onboarding';
import type { OnboardingItem, OnboardingRecord } from '@/services/onboarding';
import { msg } from '@/utils/message';

const statusText: Record<string, string> = { pending: '待办理', in_progress: '办理中', completed: '已完成', cancelled: '已取消' };

export function OnboardingPage() {
  const [rows, setRows] = useState<OnboardingRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('');
  const [detail, setDetail] = useState<OnboardingRecord | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setRows((await fetchOnboarding({ status: status || undefined, page_size: 100 })).list); }
    finally { setLoading(false); }
  }, [status]);
  useEffect(() => { void load(); }, [load]);

  async function openDetail(id: number) {
    setDetailLoading(true);
    try { setDetail(await fetchOnboardingDetail(id)); }
    finally { setDetailLoading(false); }
  }
  async function refreshDetail(id = detail?.id) {
    if (!id) return;
    const next = await fetchOnboardingDetail(id);
    setDetail(next); void load();
  }
  async function setItem(item: OnboardingItem, nextStatus: string) {
    if (!detail) return;
    await updateOnboardingItem(detail.id, item.key, { status: nextStatus, version: detail.version });
    msg.success('资料状态已更新');
    await refreshDetail();
  }

  const columns: TableColumnsType<OnboardingRecord> = [
    { title: '候选人', dataIndex: 'candidate_name' }, { title: '职位', dataIndex: 'job_name' },
    { title: '入职日期', dataIndex: 'planned_date', render: (value) => value || '-' },
    { title: '资料进度', key: 'progress', render: (_, row) => <Space><Progress percent={row.total_count ? Math.round(row.completed_count / row.total_count * 100) : 0} size="small" style={{ width: 120 }} /><span>{row.completed_count}/{row.total_count}</span></Space> },
    { title: '状态', dataIndex: 'status', render: (value) => <Tag color={value === 'completed' ? 'green' : value === 'in_progress' ? 'processing' : 'gold'}>{statusText[value] || value}</Tag> },
    { title: '负责人', dataIndex: 'owner_name' },
    { title: '操作', key: 'action', render: (_, row) => <Button type="link" onClick={() => void openDetail(row.id)}>查看资料</Button> },
  ];

  if (loading && !rows.length) return <PageLoading tip="正在加载入职资料…" />;
  return (
    <div>
      <div className="page-head"><div><h2 className="page-title">入职资料</h2><Typography.Text type="secondary">管理待入职候选人的资料收集、核验和入职完成</Typography.Text></div><Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button></div>
      <Card style={{ marginBottom: 16 }}><Select value={status} onChange={setStatus} style={{ width: 140 }} options={[{ value: '', label: '全部状态' }, { value: 'pending', label: '待办理' }, { value: 'in_progress', label: '办理中' }, { value: 'completed', label: '已完成' }]} /></Card>
      <Card><Table rowKey="id" columns={columns} dataSource={rows} loading={loading} scroll={{ x: 950 }} pagination={{ pageSize: 10 }} /></Card>
      <Drawer title={detail ? `${detail.candidate_name} · 入职资料` : '入职资料'} width={560} open={Boolean(detail)} onClose={() => setDetail(null)}>
        {detailLoading || !detail ? <PageLoading /> : <>
          <Descriptions size="small" column={2} style={{ marginBottom: 20 }}>
            <Descriptions.Item label="职位">{detail.job_name}</Descriptions.Item><Descriptions.Item label="入职日期">{detail.planned_date || '-'}</Descriptions.Item>
            <Descriptions.Item label="Offer 岗位">{detail.offer_position || '-'}</Descriptions.Item><Descriptions.Item label="状态"><Tag>{statusText[detail.status] || detail.status}</Tag></Descriptions.Item>
          </Descriptions>
          <Typography.Title level={5}>资料清单</Typography.Title>
          <Space direction="vertical" style={{ width: '100%' }}>
            {detail.checklist.map((item) => <Card size="small" key={item.key}>
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Space><CheckCircleOutlined style={{ color: item.status === 'verified' ? '#389e0d' : '#bfbfbf' }} /><span>{item.name}</span></Space>
                <Select size="small" value={item.status} disabled={detail.status === 'completed'} onChange={(value) => void setItem(item, value)} options={[{ value: 'pending', label: '待提交' }, { value: 'submitted', label: '已提交' }, { value: 'verified', label: '已核验' }, { value: 'rejected', label: '需补充' }]} />
              </Space>
            </Card>)}
          </Space>
          <Space style={{ marginTop: 20 }}>
            {detail.status === 'pending' && <Button onClick={async () => { await startOnboarding(detail.id, detail.version); msg.success('已开始办理'); await refreshDetail(); }}>开始办理</Button>}
            {detail.status !== 'completed' && <Button type="primary" onClick={async () => { try { await completeOnboarding(detail.id, detail.version); msg.success('入职已完成'); await refreshDetail(); } catch { /* 业务错误已提示 */ } }}>完成入职</Button>}
          </Space>
        </>}
      </Drawer>
    </div>
  );
}
