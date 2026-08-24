import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Col, DatePicker, Empty, Row, Select, Space, Statistic, Table, Tabs, Tag, Typography } from 'antd';
import type { TableColumnsType } from 'antd';
import { Dayjs } from 'dayjs';
import { useEffect, useMemo, useState } from 'react';

import { PageLoading } from '@/components/PageLoading';
import { fetchJobs } from '@/services/job';
import { fetchDepartments, fetchPlatformUsers } from '@/services/system';
import { downloadReport, fetchChannelReport, fetchCycleReport, fetchFunnelReport, fetchRequirementsReport } from '@/services/report';
import type { ChannelReport, CycleReport, FunnelReport, ReportFilters, RequirementReport } from '@/services/report';
import { msg } from '@/utils/message';

type TabKey = 'requirements' | 'funnel' | 'channels' | 'cycle';

const statusText: Record<string, string> = {
  draft: '草稿', pending_confirm: '待确认', recruiting: '招聘中', paused: '已暂停', completed: '已完成', closed: '已关闭',
};

export function ReportsPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('requirements');
  const [filters, setFilters] = useState<ReportFilters>({});
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [jobs, setJobs] = useState<{ id: number; name: string }[]>([]);
  const [users, setUsers] = useState<{ user_id: string; name: string }[]>([]);
  const [departments, setDepartments] = useState<{ dept_id: string; name: string }[]>([]);
  const [requirements, setRequirements] = useState<RequirementReport | null>(null);
  const [funnel, setFunnel] = useState<FunnelReport | null>(null);
  const [channels, setChannels] = useState<ChannelReport | null>(null);
  const [cycle, setCycle] = useState<CycleReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const load = async (nextFilters = filters) => {
    setLoading(true);
    try {
      const [req, funnelData, channelData, cycleData] = await Promise.all([
        fetchRequirementsReport(), fetchFunnelReport(nextFilters), fetchChannelReport(nextFilters), fetchCycleReport(nextFilters),
      ]);
      setRequirements(req); setFunnel(funnelData); setChannels(channelData); setCycle(cycleData);
    } finally { setLoading(false); }
  };

  useEffect(() => {
    void fetchJobs({ page_size: 100 }).then((data) => setJobs(data.list.map((job) => ({ id: job.id, name: job.name }))));
    void fetchPlatformUsers().then((data) => setUsers(data.map((user) => ({ user_id: user.user_id, name: user.name }))));
    void fetchDepartments().then(setDepartments);
    void load();
    // 首次加载只执行一次，后续由筛选确认按钮触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyFilters = () => {
    const next = {
      ...filters,
      date_from: dateRange?.[0].format('YYYY-MM-DD'),
      date_to: dateRange?.[1].format('YYYY-MM-DD'),
    };
    setFilters(next);
    void load(next);
  };

  const exportCurrent = async () => {
    setExporting(true);
    try { await downloadReport(activeTab, filters); msg.success('报表已下载'); } finally { setExporting(false); }
  };

  const requirementColumns: TableColumnsType<RequirementReport['rows'][number]> = useMemo(() => [
    { title: '需求', dataIndex: 'name', render: (value, row) => <Space direction="vertical" size={0}><span>{value}</span><Typography.Text type="secondary">{row.code}</Typography.Text></Space> },
    { title: '部门', dataIndex: 'dept_name' },
    { title: '状态', dataIndex: 'status', render: (value) => <Tag color={value === 'recruiting' ? 'green' : 'default'}>{statusText[value] || value}</Tag> },
    { title: '编制', dataIndex: 'headcount' }, { title: '职位数', dataIndex: 'job_count' }, { title: '候选人', dataIndex: 'candidate_count' },
    { title: '截止日期', dataIndex: 'due_date', render: (value, row) => <span style={{ color: row.overdue ? '#cf1322' : undefined }}>{value || '-'}</span> },
  ], []);
  const funnelColumns: TableColumnsType<FunnelReport['rows'][number]> = [
    { title: '阶段', dataIndex: 'name' }, { title: '阶段键', dataIndex: 'stage_key' }, { title: '人数', dataIndex: 'count' },
  ];
  const channelColumns: TableColumnsType<ChannelReport['rows'][number]> = [
    { title: '来源', dataIndex: 'source' }, { title: '投递', dataIndex: 'applications' }, { title: '候选人', dataIndex: 'candidates' },
    { title: '面试', dataIndex: 'interviews' }, { title: 'Offer', dataIndex: 'offers' }, { title: '入职', dataIndex: 'onboarded' },
    { title: '面试率', dataIndex: 'interview_rate', render: (value) => `${value}%` }, { title: 'Offer率', dataIndex: 'offer_rate', render: (value) => `${value}%` },
  ];

  if (loading && !requirements) return <PageLoading tip="正在生成招聘报表…" />;
  return (
    <div>
      <div className="page-head"><div><h2 className="page-title">招聘报表</h2><Typography.Text type="secondary">基于 MongoDB 实时数据生成，可按时间和职位筛选</Typography.Text></div><Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button></div>
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <DatePicker.RangePicker value={dateRange} onChange={(value) => setDateRange(value as [Dayjs, Dayjs] | null)} allowClear />
          <Select allowClear placeholder="全部职位" style={{ width: 220 }} value={filters.job_id} onChange={(value) => setFilters({ ...filters, job_id: value })} options={jobs.map((job) => ({ value: job.id, label: job.name }))} />
          <Select allowClear placeholder="全部部门" style={{ width: 170 }} value={filters.dept_id} onChange={(value) => setFilters({ ...filters, dept_id: value })} options={departments.map((department) => ({ value: department.dept_id, label: department.name }))} />
          <Select allowClear placeholder="全部负责人" style={{ width: 170 }} value={filters.owner_id} onChange={(value) => setFilters({ ...filters, owner_id: value })} options={users.map((user) => ({ value: user.user_id, label: user.name }))} />
          <Select allowClear placeholder="全部来源" style={{ width: 150 }} value={filters.source} onChange={(value) => setFilters({ ...filters, source: value })} options={[{ value: 'website', label: '官网投递' }, { value: 'referral', label: '内部推荐' }, { value: 'headhunt', label: '猎头' }, { value: 'job_site', label: '招聘网站' }, { value: 'campus', label: '校园招聘' }, { value: 'manual', label: '手动录入' }]} />
          <Select allowClear placeholder="需求状态" style={{ width: 150 }} value={filters.requirement_status} onChange={(value) => setFilters({ ...filters, requirement_status: value })} options={[{ value: 'draft', label: '草稿' }, { value: 'pending_confirm', label: '待确认' }, { value: 'recruiting', label: '招聘中' }, { value: 'paused', label: '已暂停' }, { value: 'completed', label: '已完成' }, { value: 'closed', label: '已关闭' }]} />
          <Button type="primary" onClick={applyFilters}>应用筛选</Button>
          <Button icon={<DownloadOutlined />} loading={exporting} onClick={() => void exportCurrent()}>导出当前报表</Button>
        </Space>
      </Card>
      <Tabs activeKey={activeTab} onChange={(key) => setActiveTab(key as TabKey)} items={[
        { key: 'requirements', label: '需求达成', children: requirements ? <><Row gutter={16} style={{ marginBottom: 16 }}>{[['total', '需求总数'], ['recruiting', '招聘中'], ['completed', '已完成'], ['overdue', '逾期']].map(([key, label]) => <Col xs={12} sm={6} key={key}><Card><Statistic title={label} value={requirements.summary[key] || 0} /></Card></Col>)}</Row><Table rowKey="id" columns={requirementColumns} dataSource={requirements.rows} scroll={{ x: 900 }} /></> : <Empty /> },
        { key: 'funnel', label: '招聘漏斗', children: funnel ? <><Card style={{ marginBottom: 16 }}><Statistic title="统计范围内应聘记录" value={funnel.total} /></Card><Table rowKey="stage_key" columns={funnelColumns} dataSource={funnel.rows} /></> : <Empty /> },
        { key: 'channels', label: '渠道效果', children: channels ? <><Card style={{ marginBottom: 16 }}><Statistic title="统计范围内投递数" value={channels.total} /></Card><Table rowKey="source" columns={channelColumns} dataSource={channels.rows} scroll={{ x: 900 }} /></> : <Empty /> },
        { key: 'cycle', label: '招聘周期', children: cycle ? <Row gutter={[16, 16]}>{[['avg_recruitment_days', '平均招聘周期'], ['avg_screening_days', '平均筛选耗时'], ['avg_interview_days', '平均面试耗时'], ['avg_offer_to_onboard_days', 'Offer 到入职']].map(([key, label]) => <Col xs={24} sm={12} lg={6} key={key}><Card><Statistic title={label} value={cycle.metrics[key as keyof CycleReport['metrics']]} suffix="天" precision={1} /></Card></Col>)}</Row> : <Empty /> },
      ]} />
    </div>
  );
}
