import { ArrowLeftOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, DatePicker, Empty, Select, Spin, Table, Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import type { Dayjs } from 'dayjs';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { fetchJobs, JOB_STATUS_TEXT } from '@/services/job';
import type { Job } from '@/services/job';
import { fetchJobProgressReport } from '@/services/report';
import type { JobProgressReport, ReportFilters } from '@/services/report';
import { fetchDepartments, fetchPlatformUsers } from '@/services/system';

const JOB_TYPE_TEXT: Record<string, string> = {
  full_time: '正式',
  part_time: '兼职',
  intern: '实习',
  outsource: '外包',
};

const METRIC_CARDS: { key: keyof JobProgressReport['summary']; label: string; unit: string }[] = [
  { key: 'received', label: '接收简历', unit: '人' },
  { key: 'recommended', label: '推荐简历', unit: '人' },
  { key: 'scheduled', label: '安排面试', unit: '人' },
  { key: 'interviewed', label: '进行面试', unit: '人' },
  { key: 'offered', label: 'Offer', unit: '人' },
  { key: 'pending_onboard', label: '待入职', unit: '人' },
  { key: 'onboarded', label: '入职', unit: '人' },
  { key: 'regularized', label: '转正', unit: '人' },
];

interface RankPanelProps {
  title: string;
  rows: { name: string; value: number }[];
  suffix?: string;
}

function RankPanel({ title, rows, suffix = '人' }: RankPanelProps) {
  const sortedRows = [...rows].sort((a, b) => b.value - a.value).slice(0, 8);
  const max = Math.max(...sortedRows.map((item) => item.value), 0);

  return (
    <section className="job-progress-panel">
      <h3>{title}</h3>
      {max <= 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
      ) : (
        <div className="job-progress-ranks">
          {sortedRows.map((item, index) => (
            <div className="job-progress-rank" key={`${item.name}-${index}`}>
              <span className="job-progress-rank-name" title={item.name}>{item.name}</span>
              <span className="job-progress-rank-track">
                <span style={{ width: `${Math.max((item.value / max) * 100, 2)}%` }} />
              </span>
              <strong>{item.value}{suffix}</strong>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

const EMPTY_REPORT: JobProgressReport = {
  summary: {
    received: 0, recommended: 0, scheduled: 0, interviewed: 0,
    offered: 0, pending_onboard: 0, onboarded: 0, regularized: 0,
    active_jobs: 0, completion_rate: 0, onboarding_cycle: 0,
  },
  rankings: {},
  rows: [],
};

export function JobProgressReportPage() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [owners, setOwners] = useState<{ value: string; label: string }[]>([]);
  const [departments, setDepartments] = useState<{ value: string; label: string }[]>([]);
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [draftFilters, setDraftFilters] = useState<ReportFilters>({});
  const [filters, setFilters] = useState<ReportFilters>({});
  const [report, setReport] = useState<JobProgressReport>(EMPTY_REPORT);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setReport(await fetchJobProgressReport(filters));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void Promise.all([
      fetchJobs({ page_size: 100 }),
      fetchPlatformUsers(),
      fetchDepartments(),
    ]).then(([jobData, userData, departmentData]) => {
      setJobs(jobData.list);
      setOwners(userData
        .filter((user) => user.role === 'hr')
        .map((user) => ({ value: user.user_id, label: user.name })));
      setDepartments(departmentData.map((item) => ({ value: item.dept_id, label: item.name })));
    });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const totalHeadcount = useMemo(
    () => report.rows.reduce((total, item) => total + item.headcount, 0),
    [report.rows],
  );

  const applyFilters = () => {
    setFilters({
      ...draftFilters,
      date_from: dateRange?.[0].format('YYYY-MM-DD'),
      date_to: dateRange?.[1].format('YYYY-MM-DD'),
    });
  };

  const resetFilters = () => {
    setDateRange(null);
    setDraftFilters({});
    setFilters({});
  };

  const columns: TableColumnsType<JobProgressReport['rows'][number]> = [
    { title: '职位', dataIndex: 'job_name', fixed: 'left', width: 160 },
    { title: '招聘HR', dataIndex: 'owner_name', width: 100 },
    { title: '部门', dataIndex: 'dept_name', width: 130 },
    { title: '城市', dataIndex: 'location', width: 100, render: (value) => value || '-' },
    { title: '类型', dataIndex: 'job_type', width: 80, render: (value) => JOB_TYPE_TEXT[value] || value || '-' },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (value) => <Tag color={value === 'recruiting' ? 'green' : 'default'}>{JOB_STATUS_TEXT[value] || value}</Tag>,
    },
    { title: '招聘目标', dataIndex: 'headcount', width: 90, render: (value) => `${value}人` },
    { title: '接收简历', dataIndex: 'received', width: 90, render: (value) => `${value}人` },
    { title: '推荐简历', dataIndex: 'recommended', width: 90, render: (value) => `${value}人` },
    { title: '安排面试', dataIndex: 'scheduled', width: 90, render: (value) => `${value}人` },
    { title: '进行面试', dataIndex: 'interviewed', width: 90, render: (value) => `${value}人` },
    { title: 'Offer', dataIndex: 'offered', width: 80, render: (value) => `${value}人` },
    { title: '待入职', dataIndex: 'pending_onboard', width: 80, render: (value) => `${value}人` },
    { title: '入职', dataIndex: 'onboarded', width: 70, render: (value) => `${value}人` },
    { title: '完成率', dataIndex: 'completion_rate', width: 90, render: (value) => `${value}%` },
  ];

  const ranking = (key: string) => report.rankings[key] || [];

  return (
    <div className="job-progress-page">
      <div className="job-progress-heading">
        <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate('/reports')}>返回</Button>
        <h2>HR进展</h2>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
      </div>

      <section className="job-progress-toolbar">
        <DatePicker.RangePicker
          value={dateRange}
          onChange={(value) => setDateRange(value as [Dayjs, Dayjs] | null)}
        />
        <Select
          allowClear showSearch optionFilterProp="label" placeholder="招聘职位" value={draftFilters.job_id}
          options={jobs.map((job) => ({ value: job.id, label: job.name }))}
          onChange={(value) => setDraftFilters((current) => ({ ...current, job_id: value }))}
        />
        <Select
          allowClear showSearch optionFilterProp="label" placeholder="招聘HR" value={draftFilters.owner_id}
          options={owners}
          onChange={(value) => setDraftFilters((current) => ({ ...current, owner_id: value }))}
        />
        <Select
          allowClear showSearch optionFilterProp="label" placeholder="所属部门" value={draftFilters.dept_id}
          options={departments}
          onChange={(value) => setDraftFilters((current) => ({ ...current, dept_id: value }))}
        />
        <Select
          allowClear placeholder="职位状态" value={draftFilters.job_status}
          options={Object.entries(JOB_STATUS_TEXT).map(([value, label]) => ({ value, label }))}
          onChange={(value) => setDraftFilters((current) => ({ ...current, job_status: value }))}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={applyFilters}>查询</Button>
        <Button onClick={resetFilters}>重置</Button>
      </section>

      <Spin spinning={loading}>
        <div className="job-progress-metrics">
          {METRIC_CARDS.map((item) => (
            <section className="job-progress-metric" key={item.key}>
              <span>{item.label}</span>
              <div>
                <strong>{report.summary[item.key]}</strong>
                <small>{item.unit}{item.key !== 'received' && totalHeadcount > 0 ? ` / ${totalHeadcount}人` : ''}</small>
              </div>
            </section>
          ))}
        </div>

        <div className="job-progress-panels">
          <RankPanel title="职位简历量排名" rows={ranking('job_resumes')} />
          <RankPanel title="各部门入职分布" rows={ranking('department_onboarded')} />
          <RankPanel title="HR推荐简历排名" rows={ranking('hr_recommended')} />
          <RankPanel title="HR发出Offer排名" rows={ranking('hr_offers')} />
          <RankPanel title="招聘目标完成情况" rows={ranking('job_completion')} suffix="%" />
          <RankPanel title="职位入职人数排名" rows={ranking('job_onboarded')} />
        </div>

        <section className="job-progress-table-panel">
          <h3>职位招聘进度表</h3>
          <Table
            rowKey="job_id"
            size="small"
            columns={columns}
            dataSource={report.rows}
            scroll={{ x: 1500 }}
            pagination={false}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" /> }}
          />
        </section>
      </Spin>
    </div>
  );
}
