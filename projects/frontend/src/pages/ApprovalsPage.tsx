import { CheckOutlined, CloseOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Input, Modal, Select, Space, Table, Tag, Typography } from 'antd';
import type { TableColumnsType } from 'antd';
import { useCallback, useEffect, useState } from 'react';

import { PageLoading } from '@/components/PageLoading';
import { approvalAction, fetchApprovals } from '@/services/approval';
import type { ApprovalRecord } from '@/services/approval';
import { useCurrentUser } from '@/services/user';
import { msg } from '@/utils/message';

const statusText: Record<string, string> = { pending: '审批中', approved: '已通过', rejected: '已驳回' };

export function ApprovalsPage() {
  const { user } = useCurrentUser();
  const [rows, setRows] = useState<ApprovalRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('');
  const [rejectTarget, setRejectTarget] = useState<ApprovalRecord | null>(null);
  const [reason, setReason] = useState('');
  const [acting, setActing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setRows((await fetchApprovals({ status: status || undefined, page_size: 100 })).list); }
    finally { setLoading(false); }
  }, [status]);
  useEffect(() => { void load(); }, [load]);

  async function act(record: ApprovalRecord, action: 'approve' | 'reject', rejectReason?: string) {
    setActing(true);
    try {
      await approvalAction(record.id, { action, version: record.version, reason: rejectReason });
      msg.success(action === 'approve' ? '审批已通过' : '审批已驳回');
      setRejectTarget(null); setReason(''); void load();
    } finally { setActing(false); }
  }

  const columns: TableColumnsType<ApprovalRecord> = [
    { title: '候选人', dataIndex: 'candidate_name' },
    { title: '职位', dataIndex: 'job_name', render: (value, row) => <Space direction="vertical" size={0}><span>{value}</span><Typography.Text type="secondary">{row.position}</Typography.Text></Space> },
    { title: 'Offer', dataIndex: 'offer_id', render: (value, row) => <Space direction="vertical" size={0}><span>#{value} · {row.salary}</span><Typography.Text type="secondary">入职：{row.onboard_date || '-'}</Typography.Text></Space> },
    { title: '审批进度', dataIndex: 'steps', render: (steps: ApprovalRecord['steps'], row) => <Space wrap>{steps.map((step) => <Tag key={step.key} color={step.status === 'approved' ? 'green' : step.status === 'rejected' ? 'red' : step.status === 'pending' ? 'gold' : 'default'}>{step.name}：{step.status === 'waiting' ? '待轮到' : step.status === 'approved' ? '通过' : step.status === 'rejected' ? '驳回' : row.status === 'pending' ? '待审批' : statusText[row.status]}</Tag>)}</Space> },
    { title: '期限', dataIndex: 'deadline_at', render: (value, row) => <Space direction="vertical" size={0}><span>{value || '-'}</span>{row.overdue ? <Tag color="red">已超期</Tag> : row.status === 'pending' ? <Typography.Text type="secondary">剩余 {row.days_remaining} 天</Typography.Text> : null}</Space> },
    { title: '状态', dataIndex: 'status', render: (value) => <Tag color={value === 'approved' ? 'green' : value === 'rejected' ? 'red' : 'gold'}>{statusText[value] || value}</Tag> },
    { title: '操作', key: 'action', render: (_, row) => {
      const current = row.steps.find((step) => step.key === row.current_step);
      const canAct = row.status === 'pending' && current?.approver_id === user?.user_id;
      if (!canAct) return <Typography.Text type="secondary">{row.status === 'pending' ? `待 ${current?.approver_name || '审批人'}` : '已结束'}</Typography.Text>;
      return <Space><Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => void act(row, 'approve')}>通过</Button><Button size="small" danger icon={<CloseOutlined />} onClick={() => { setRejectTarget(row); setReason(''); }}>驳回</Button></Space>;
    } },
  ];

  if (loading && !rows.length) return <PageLoading tip="正在加载录用审批…" />;
  return (
    <div>
      <div className="page-head"><div><h2 className="page-title">录用审批</h2><Typography.Text type="secondary">Offer 提交后按组织统筹、总经理、董事长顺序审批</Typography.Text></div><Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button></div>
      <Card style={{ marginBottom: 16 }}><Space><Select value={status} onChange={setStatus} style={{ width: 140 }} options={[{ value: '', label: '全部状态' }, { value: 'pending', label: '审批中' }, { value: 'approved', label: '已通过' }, { value: 'rejected', label: '已驳回' }]} /><Typography.Text type="secondary">当前身份：{user?.name}（{user?.role_name}）</Typography.Text></Space></Card>
      <Card><Table rowKey="id" columns={columns} dataSource={rows} loading={loading} scroll={{ x: 1100 }} pagination={{ pageSize: 10 }} /></Card>
      <Modal title="驳回录用审批" open={Boolean(rejectTarget)} confirmLoading={acting} okText="确认驳回" cancelText="取消" onCancel={() => setRejectTarget(null)} onOk={() => { if (!reason.trim()) { msg.error('驳回必须填写原因'); return; } if (rejectTarget) void act(rejectTarget, 'reject', reason.trim()); }}>
        <Input.TextArea rows={4} placeholder="请输入驳回原因" value={reason} onChange={(event) => setReason(event.target.value)} />
      </Modal>
    </div>
  );
}
