import { ArrowLeftOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, DatePicker, Empty, Select, Spin } from 'antd';
import type { Dayjs } from 'dayjs';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { fetchJobs, JOB_STATUS_TEXT } from '@/services/job';
import type { Job } from '@/services/job';
import { fetchJobProgressReport } from '@/services/report';
import type { JobProgressReport, ReportFilters } from '@/services/report';
import { fetchPlatformUsers } from '@/services/system';
import { fetchPipelineTemplates } from '@/services/template';

const EMPTY_REPORT: JobProgressReport = {
  summary: {
    received: 0, recommended: 0, scheduled: 0, interviewed: 0,
    offered: 0, pending_onboard: 0, onboarded: 0, regularized: 0,
    active_jobs: 0, completion_rate: 0, onboarding_cycle: 0,
  },
  rankings: {},
  rows: [],
};

interface ProgressPanelProps {
  title: string;
  rows: { name: string; value: number }[];
  suffix?: string;
}

function ProgressPanel({ title, rows, suffix = '人' }: ProgressPanelProps) {
  const visibleRows = [...rows].sort((a, b) => b.value - a.value).slice(0, 10);
  const max = Math.max(...visibleRows.map((item) => item.value), 0);

  return (
    <section className="position-progress-panel">
      <h3>{title}</h3>
      {max <= 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
      ) : (
        <div className="position-progress-chart">
          {visibleRows.map((item) => (
            <div className="position-progress-chart-row" key={item.name}>
              <span title={item.name}>{item.name}</span>
              <div><i style={{ width: `${Math.max(item.value / max * 100, 2)}%` }} /></div>
              <strong>{item.value}{suffix}</strong>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function PositionProgressReportPage() {
  const navigate = useNavigate();
  const [report, setReport] = useState<JobProgressReport>(EMPTY_REPORT);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [owners, setOwners] = useState<{ value: string; label: string }[]>([]);
  const [templates, setTemplates] = useState<{ value: number; label: string }[]>([]);
  const [operationRange, setOperationRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [jobRange, setJobRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [draftFilters, setDraftFilters] = useState<ReportFilters>({});
  const [filters, setFilters] = useState<ReportFilters>({});
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
      fetchPipelineTemplates(1, 100),
    ]).then(([jobData, userData, templateData]) => {
      setJobs(jobData.list);
      setOwners(userData
        .filter((user) => user.role === 'hr')
        .map((user) => ({ value: user.user_id, label: user.name })));
      setTemplates(templateData.list.map((item) => ({ value: item.id, label: item.name })));
    });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const applyFilters = () => {
    setFilters({
      ...draftFilters,
      date_from: operationRange?.[0].format('YYYY-MM-DD'),
      date_to: operationRange?.[1].format('YYYY-MM-DD'),
      job_date_from: jobRange?.[0].format('YYYY-MM-DD'),
      job_date_to: jobRange?.[1].format('YYYY-MM-DD'),
    });
  };

  const resetFilters = () => {
    setOperationRange(null);
    setJobRange(null);
    setDraftFilters({});
    setFilters({});
  };

  const ranking = (key: string) => report.rankings[key] || [];
  const metrics = [
    { label: '在招职位数', value: report.summary.active_jobs, suffix: '个' },
    { label: '入职周期', value: report.summary.onboarding_cycle, suffix: '天' },
    { label: '职位完成率', value: report.summary.completion_rate, suffix: '%' },
    { label: 'Offer', value: report.summary.offered, suffix: '人' },
    { label: '待入职', value: report.summary.pending_onboard, suffix: '人' },
    { label: '入职', value: report.summary.onboarded, suffix: '人' },
  ];

  return (
    <div className="position-progress-page">
      <div className="position-progress-heading">
        <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate('/reports')}>返回</Button>
        <h2>职位招聘进展</h2>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
      </div>

      <section className="position-progress-toolbar">
        <DatePicker.RangePicker
          value={operationRange}
          placeholder={['操作开始时间', '操作结束时间']}
          onChange={(value) => setOperationRange(value as [Dayjs, Dayjs] | null)}
        />
        <Select
          allowClear placeholder="招聘流程" value={draftFilters.template_id}
          options={templates}
          onChange={(value) => setDraftFilters((current) => ({ ...current, template_id: value }))}
        />
        <DatePicker.RangePicker
          value={jobRange}
          placeholder={['职位开始时间', '职位结束时间']}
          onChange={(value) => setJobRange(value as [Dayjs, Dayjs] | null)}
        />
        <Select
          allowClear showSearch optionFilterProp="label" placeholder="职位负责人" value={draftFilters.owner_id}
          options={owners}
          onChange={(value) => setDraftFilters((current) => ({ ...current, owner_id: value }))}
        />
        <Select
          allowClear showSearch optionFilterProp="label" placeholder="职位名称" value={draftFilters.job_id}
          options={jobs.map((job) => ({ value: job.id, label: job.name }))}
          onChange={(value) => setDraftFilters((current) => ({ ...current, job_id: value }))}
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
        <div className="position-progress-metrics">
          {metrics.map((item) => (
            <section className="position-progress-metric" key={item.label}>
              <span>{item.label}</span>
              <div><strong>{item.value}</strong><small>{item.suffix}</small></div>
            </section>
          ))}
        </div>

        <div className="position-progress-panels">
          <ProgressPanel title="职位入职周期" rows={ranking('job_onboarding_cycle')} suffix="天" />
          <ProgressPanel title="主/被动投递简历入职分布" rows={ranking('delivery_onboarded')} />
          <ProgressPanel title="接收简历来源" rows={ranking('resume_sources')} />
        </div>
      </Spin>
    </div>
  );
}
