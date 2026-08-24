import { ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Input, Select, Space, Table, Typography } from 'antd';
import type { TableColumnsType } from 'antd';
import { useCallback, useEffect, useState } from 'react';

import { PageLoading } from '@/components/PageLoading';
import { fetchAuditLogs } from '@/services/audit';
import type { AuditLog } from '@/services/audit';

export function AuditLogsPage() {
  const [rows, setRows] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [bizType, setBizType] = useState('');
  const [keyword, setKeyword] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    try { setRows((await fetchAuditLogs({ biz_type: bizType || undefined, keyword: keyword || undefined, page_size: 100 })).list); }
    finally { setLoading(false); }
  }, [bizType, keyword]);
  useEffect(() => { void load(); }, [load]);

  const columns: TableColumnsType<AuditLog> = [
    { title: '时间', dataIndex: 'created_at', width: 170 }, { title: '业务类型', dataIndex: 'biz_type', width: 130 },
    { title: '动作', dataIndex: 'action', width: 180 }, { title: '业务 ID', dataIndex: 'biz_id', width: 100 },
    { title: '操作人', dataIndex: 'operator_name', width: 110 }, { title: '详情', dataIndex: 'detail' },
  ];
  if (loading && !rows.length) return <PageLoading tip="正在加载操作日志…" />;
  return <div>
    <div className="page-head"><div><h2 className="page-title">操作日志</h2><Typography.Text type="secondary">查看关键数据变更、阶段流转、审批和导出记录</Typography.Text></div><Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button></div>
    <Card style={{ marginBottom: 16 }}><Space wrap><Select allowClear placeholder="业务类型" style={{ width: 180 }} value={bizType || undefined} onChange={(value) => setBizType(value || '')} options={[{ value: 'candidate', label: '候选人' }, { value: 'application', label: '应聘记录' }, { value: 'interview', label: '面试' }, { value: 'offer', label: 'Offer' }, { value: 'offer_approval', label: '录用审批' }, { value: 'onboarding', label: '入职' }, { value: 'export', label: '导出' }]} /><Input.Search placeholder="搜索业务 ID / 详情" allowClear style={{ width: 280 }} value={keyword} onChange={(event) => setKeyword(event.target.value)} onSearch={() => void load()} /></Space></Card>
    <Card><Table rowKey="id" columns={columns} dataSource={rows} loading={loading} scroll={{ x: 900 }} pagination={{ pageSize: 20 }} /></Card>
  </div>;
}
