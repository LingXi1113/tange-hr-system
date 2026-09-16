import { ArrowLeftOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, DatePicker, Empty, Select, Spin } from 'antd';
import type { Dayjs } from 'dayjs';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { fetchJobs } from '@/services/job';
import { fetchChannelEffectReport } from '@/services/report';
import type { ChannelEffectReport, ReportFilters } from '@/services/report';
import { fetchRequirements } from '@/services/requirement';
import { fetchDepartments } from '@/services/system';
import { fetchPipelineTemplates } from '@/services/template';

const SOURCE_TEXT: Record<string, string> = {
  website: '官网投递',
  job_site: '招聘网站',
  campus: '校园招聘',
  referral: '内部推荐',
  headhunt: '猎头',
  manual: '手动录入',
  unknown: '其他',
};

const CHART_COLORS = ['#59b4ee', '#62d2ac', '#f7bd55', '#818cf8', '#f28c8c', '#92c5de', '#b7a6e6'];

const EMPTY_REPORT: ChannelEffectReport = {
  summary: {
    active_channels: 0,
    applications: 0,
    offers: 0,
    pending_onboard: 0,
    onboarded: 0,
    onboarding_cycle: 0,
  },
  rows: [],
  attrition: [],
};

interface RankingPanelProps {
  title: string;
  rows: { name: string; value: number }[];
  suffix?: string;
  className?: string;
}

function RankingPanel({ title, rows, suffix = '人', className = '' }: RankingPanelProps) {
  const visibleRows = [...rows].sort((a, b) => b.value - a.value).slice(0, 8);
  const max = Math.max(...visibleRows.map((item) => item.value), 0);
  return (
    <section className={`channel-effect-panel ${className}`}>
      <h3>{title}</h3>
      {max <= 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
      ) : (
        <div className="channel-effect-ranking">
          {visibleRows.map((item) => (
            <div className="channel-effect-ranking-row" key={item.name}>
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

function SourceDonut({ rows }: { rows: ChannelEffectReport['rows'] }) {
  const total = rows.reduce((sum, row) => sum + row.applications, 0);
  const segments = useMemo(() => {
    let offset = 0;
    return rows.map((row, index) => {
      const percent = total ? row.applications / total * 100 : 0;
      const segment = {
        ...row,
        label: SOURCE_TEXT[row.source] || row.source,
        color: CHART_COLORS[index % CHART_COLORS.length],
        start: offset,
        end: offset + percent,
        percent,
      };
      offset += percent;
      return segment;
    });
  }, [rows, total]);
  const background = segments.length
    ? `conic-gradient(${segments.map((item) => `${item.color} ${item.start}% ${item.end}%`).join(', ')})`
    : '#edf1f5';

  return (
    <section className="channel-effect-panel">
      <h3>接收简历来源</h3>
      {total <= 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
      ) : (
        <div className="channel-effect-donut-wrap">
          <div className="channel-effect-donut" style={{ background }}>
            <div><strong>{total}</strong><span>接收简历</span></div>
          </div>
          <div className="channel-effect-legend">
            {segments.map((item) => (
              <div key={item.source}>
                <i style={{ background: item.color }} />
                <span>{item.label}</span>
                <strong>{item.applications}人（{item.percent.toFixed(1)}%）</strong>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export function ChannelEffectReportPage() {
  const navigate = useNavigate();
  const [report, setReport] = useState<ChannelEffectReport>(EMPTY_REPORT);
  const [operationRange, setOperationRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [draftFilters, setDraftFilters] = useState<ReportFilters>({});
  const [filters, setFilters] = useState<ReportFilters>({});
  const [templates, setTemplates] = useState<{ value: number; label: string }[]>([]);
  const [requirements, setRequirements] = useState<{ value: number; label: string }[]>([]);
  const [jobs, setJobs] = useState<{ value: number; label: string }[]>([]);
  const [departments, setDepartments] = useState<{ value: string; label: string }[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setReport(await fetchChannelEffectReport(filters));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void Promise.all([
      fetchPipelineTemplates(1, 100),
      fetchRequirements({ page_size: 100 }),
      fetchJobs({ page_size: 100 }),
      fetchDepartments(),
    ]).then(([templateData, requirementData, jobData, departmentData]) => {
      setTemplates(templateData.list.map((item) => ({ value: item.id, label: item.name })));
      setRequirements(requirementData.list.map((item) => ({ value: item.id, label: item.name })));
      setJobs(jobData.list.map((item) => ({ value: item.id, label: item.name })));
      setDepartments(departmentData.map((item) => ({ value: item.dept_id, label: item.name })));
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
    });
  };

  const resetFilters = () => {
    setOperationRange(null);
    setDraftFilters({});
    setFilters({});
  };

  const sourceRows = report.rows.map((row) => ({
    name: SOURCE_TEXT[row.source] || row.source,
    value: row.offers,
  }));
  const onboardRows = report.rows.map((row) => ({
    name: SOURCE_TEXT[row.source] || row.source,
    value: row.onboarded,
  }));
  const hiringRateRows = report.rows.map((row) => ({
    name: SOURCE_TEXT[row.source] || row.source,
    value: row.onboard_rate,
  }));

  const metrics = [
    { label: '活跃渠道数', value: report.summary.active_channels, suffix: '个' },
    { label: '接收简历数', value: report.summary.applications, suffix: '人' },
    { label: 'Offer', value: report.summary.offers, suffix: '人' },
    { label: '待入职', value: report.summary.pending_onboard, suffix: '人' },
    { label: '入职', value: report.summary.onboarded, suffix: '人' },
    { label: '入职周期', value: report.summary.onboarding_cycle, suffix: '天' },
  ];

  return (
    <div className="channel-effect-page">
      <div className="channel-effect-heading">
        <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate('/reports')}>返回</Button>
        <h2>招聘渠道效果</h2>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
      </div>

      <section className="channel-effect-toolbar">
        <DatePicker.RangePicker
          value={operationRange}
          placeholder={['操作开始时间', '操作结束时间']}
          onChange={(value) => setOperationRange(value as [Dayjs, Dayjs] | null)}
        />
        <Select
          allowClear placeholder="招聘流程" value={draftFilters.template_id} options={templates}
          onChange={(value) => setDraftFilters((current) => ({ ...current, template_id: value }))}
        />
        <Select
          allowClear showSearch optionFilterProp="label" placeholder="需求名称"
          value={draftFilters.requirement_id} options={requirements}
          onChange={(value) => setDraftFilters((current) => ({ ...current, requirement_id: value }))}
        />
        <Select
          allowClear showSearch optionFilterProp="label" placeholder="职位名称"
          value={draftFilters.job_id} options={jobs}
          onChange={(value) => setDraftFilters((current) => ({ ...current, job_id: value }))}
        />
        <Select
          allowClear showSearch optionFilterProp="label" placeholder="职位所属部门"
          value={draftFilters.dept_id} options={departments}
          onChange={(value) => setDraftFilters((current) => ({ ...current, dept_id: value }))}
        />
        <Select
          allowClear placeholder="投递门户方案" value={draftFilters.source}
          options={Object.entries(SOURCE_TEXT).filter(([value]) => value !== 'unknown').map(([value, label]) => ({ value, label }))}
          onChange={(value) => setDraftFilters((current) => ({ ...current, source: value }))}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={applyFilters}>查询</Button>
        <Button onClick={resetFilters}>重置</Button>
      </section>

      <Spin spinning={loading}>
        <div className="channel-effect-metrics">
          {metrics.map((item) => (
            <section className="channel-effect-metric" key={item.label}>
              <span>{item.label}</span>
              <div><strong>{item.value}</strong><small>{item.suffix}</small></div>
            </section>
          ))}
        </div>

        <div className="channel-effect-grid">
          <SourceDonut rows={report.rows} />
          <RankingPanel title="Offer数量排名" rows={sourceRows} />
          <RankingPanel title="入职人数分布" rows={onboardRows} />
          <RankingPanel title="聘用率排名" rows={hiringRateRows} suffix="%" />
          <RankingPanel title="入职人员流失情况" rows={report.attrition} className="is-wide" />
        </div>
      </Spin>
    </div>
  );
}
