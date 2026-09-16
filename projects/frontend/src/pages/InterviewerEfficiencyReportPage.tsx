import { ArrowLeftOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, DatePicker, Empty, Select, Spin } from 'antd';
import type { Dayjs } from 'dayjs';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { fetchJobs } from '@/services/job';
import { fetchInterviewerEfficiencyReport } from '@/services/report';
import type { InterviewerEfficiencyReport, ReportFilters } from '@/services/report';
import { fetchRequirements } from '@/services/requirement';
import { fetchDepartments, fetchPlatformUsers } from '@/services/system';
import { fetchPipelineTemplates } from '@/services/template';

const EMPTY_REPORT: InterviewerEfficiencyReport = {
  summary: {
    recommended: 0,
    feedback: 0,
    feedback_rate: 0,
    attended: 0,
    interview_feedback: 0,
    interview_feedback_rate: 0,
  },
  rows: [],
};

type EfficiencyRow = InterviewerEfficiencyReport['rows'][number];

interface LineSeries {
  key: keyof EfficiencyRow;
  label: string;
  color: string;
}

interface LineChartProps {
  rows: EfficiencyRow[];
  series: LineSeries[];
  suffix?: string;
  averageLine?: boolean;
}

function LineChart({ rows, series, suffix = '', averageLine = false }: LineChartProps) {
  const width = 1200;
  const height = 260;
  const padding = { top: 28, right: 50, bottom: 54, left: 46 };
  const values = rows.flatMap((row) => series.map((item) => Number(row[item.key]) || 0));
  const maxValue = Math.max(...values, 0);
  const chartMax = maxValue > 0 ? maxValue * 1.18 : 1;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const xOf = (index: number) => rows.length <= 1
    ? padding.left + plotWidth / 2
    : padding.left + index * plotWidth / (rows.length - 1);
  const yOf = (value: number) => padding.top + plotHeight - value / chartMax * plotHeight;
  const average = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;

  if (!rows.length || maxValue <= 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />;
  }

  return (
    <div className="interviewer-line-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img">
        {[0, 1, 2, 3, 4].map((line) => {
          const value = chartMax * (4 - line) / 4;
          const y = padding.top + line * plotHeight / 4;
          return (
            <g key={line}>
              <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} className="grid-line" />
              <text x={padding.left - 10} y={y + 4} textAnchor="end" className="axis-text">{value.toFixed(value < 10 ? 1 : 0)}</text>
            </g>
          );
        })}
        {averageLine && average > 0 && (
          <g>
            <line x1={padding.left} y1={yOf(average)} x2={width - padding.right} y2={yOf(average)} className="average-line" />
            <text x={width - padding.right} y={yOf(average) - 6} textAnchor="end" className="average-text">平均值 {average.toFixed(1)}{suffix}</text>
          </g>
        )}
        {series.map((item) => {
          const points = rows.map((row, index) => `${xOf(index)},${yOf(Number(row[item.key]) || 0)}`).join(' ');
          return (
            <g key={item.label}>
              <polyline points={points} fill="none" stroke={item.color} strokeWidth="2.2" />
              {rows.map((row, index) => {
                const value = Number(row[item.key]) || 0;
                return (
                  <g key={`${item.label}-${row.name}`}>
                    <circle cx={xOf(index)} cy={yOf(value)} r="3.5" fill={item.color} />
                    <text x={xOf(index)} y={yOf(value) - 8} textAnchor="middle" className="value-text">{value}{suffix}</text>
                  </g>
                );
              })}
            </g>
          );
        })}
        {rows.map((row, index) => (
          <text key={row.name} x={xOf(index)} y={height - 22} textAnchor="middle" className="axis-label">{row.name}</text>
        ))}
      </svg>
      <div className="interviewer-chart-legend">
        {series.map((item) => <span key={item.label}><i style={{ background: item.color }} />{item.label}</span>)}
      </div>
    </div>
  );
}

export function InterviewerEfficiencyReportPage() {
  const navigate = useNavigate();
  const [report, setReport] = useState<InterviewerEfficiencyReport>(EMPTY_REPORT);
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [draftFilters, setDraftFilters] = useState<ReportFilters>({});
  const [filters, setFilters] = useState<ReportFilters>({});
  const [interviewers, setInterviewers] = useState<{ value: string; label: string }[]>([]);
  const [departments, setDepartments] = useState<{ value: string; label: string }[]>([]);
  const [templates, setTemplates] = useState<{ value: number; label: string }[]>([]);
  const [jobs, setJobs] = useState<{ value: number; label: string }[]>([]);
  const [requirements, setRequirements] = useState<{ value: number; label: string }[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setReport(await fetchInterviewerEfficiencyReport(filters));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void Promise.all([
      fetchPlatformUsers(),
      fetchDepartments(),
      fetchPipelineTemplates(1, 100),
      fetchJobs({ page_size: 100 }),
      fetchRequirements({ page_size: 100 }),
    ]).then(([userData, departmentData, templateData, jobData, requirementData]) => {
      setInterviewers(userData.map((item) => ({ value: item.name, label: item.name })));
      setDepartments(departmentData.map((item) => ({ value: item.dept_id, label: item.name })));
      setTemplates(templateData.list.map((item) => ({ value: item.id, label: item.name })));
      setJobs(jobData.list.map((item) => ({ value: item.id, label: item.name })));
      setRequirements(requirementData.list.map((item) => ({ value: item.id, label: item.name })));
    });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

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

  const passRateRows = useMemo(
    () => [...report.rows].filter((item) => item.feedback > 0).sort((a, b) => b.pass_rate - a.pass_rate),
    [report.rows],
  );
  const responseRows = useMemo(
    () => [...report.rows].filter((item) => item.feedback_hours > 0).sort((a, b) => b.feedback_hours - a.feedback_hours),
    [report.rows],
  );

  const metrics = [
    { label: '推荐数量', value: report.summary.recommended, suffix: '次' },
    { label: '推荐反馈', value: report.summary.feedback, suffix: '次' },
    { label: '推荐反馈率', value: report.summary.feedback_rate, suffix: '%' },
    { label: '参加面试', value: report.summary.attended, suffix: '人' },
    { label: '面试反馈', value: report.summary.interview_feedback, suffix: '人' },
    { label: '面试反馈率', value: report.summary.interview_feedback_rate, suffix: '%' },
  ];

  return (
    <div className="interviewer-efficiency-page">
      <div className="interviewer-efficiency-heading">
        <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate('/reports')}>返回</Button>
        <h2>面试官效率</h2>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
      </div>

      <section className="interviewer-efficiency-toolbar">
        <DatePicker.RangePicker
          value={dateRange}
          placeholder={['操作开始时间', '操作结束时间']}
          onChange={(value) => setDateRange(value as [Dayjs, Dayjs] | null)}
        />
        <Select
          allowClear showSearch optionFilterProp="label" placeholder="面试官姓名"
          value={draftFilters.interviewer_name} options={interviewers}
          onChange={(value) => setDraftFilters((current) => ({ ...current, interviewer_name: value }))}
        />
        <Select
          allowClear showSearch optionFilterProp="label" placeholder="面试官部门"
          value={draftFilters.interviewer_dept} options={departments}
          onChange={(value) => setDraftFilters((current) => ({ ...current, interviewer_dept: value }))}
        />
        <Select
          allowClear placeholder="招聘流程" value={draftFilters.template_id} options={templates}
          onChange={(value) => setDraftFilters((current) => ({ ...current, template_id: value }))}
        />
        <Select
          allowClear showSearch optionFilterProp="label" placeholder="职位名称"
          value={draftFilters.job_id} options={jobs}
          onChange={(value) => setDraftFilters((current) => ({ ...current, job_id: value }))}
        />
        <Select
          allowClear showSearch optionFilterProp="label" placeholder="需求名称"
          value={draftFilters.requirement_id} options={requirements}
          onChange={(value) => setDraftFilters((current) => ({ ...current, requirement_id: value }))}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={applyFilters}>查询</Button>
        <Button onClick={resetFilters}>重置</Button>
      </section>

      <Spin spinning={loading}>
        <div className="interviewer-efficiency-metrics">
          {metrics.map((item, index) => (
            <section className={`interviewer-efficiency-metric${index === 0 ? ' is-active' : ''}`} key={item.label}>
              <span>{item.label}</span>
              <div><strong>{item.value}</strong><small>{item.suffix}</small></div>
            </section>
          ))}
        </div>

        <section className="interviewer-efficiency-panel">
          <h3>推荐数据分析</h3>
          <LineChart
            rows={report.rows}
            series={[
              { key: 'recommended', label: '推荐次数', color: '#58d4a9' },
              { key: 'passed', label: '推荐通过次数', color: '#55aaf2' },
              { key: 'failed', label: '推荐未通过次数', color: '#ff8a75' },
              { key: 'no_feedback', label: '推荐未反馈次数', color: '#f4b84f' },
            ]}
            suffix="次"
          />
        </section>

        <section className="interviewer-efficiency-panel">
          <h3>推荐通过率排名</h3>
          <LineChart
            rows={passRateRows}
            series={[{ key: 'pass_rate', label: '推荐通过率', color: '#58d4a9' }]}
            suffix="%"
            averageLine
          />
        </section>

        <section className="interviewer-efficiency-panel">
          <h3>推荐反馈时效</h3>
          <LineChart
            rows={responseRows}
            series={[{ key: 'feedback_hours', label: '推荐反馈时效', color: '#58d4a9' }]}
            suffix="小时"
            averageLine
          />
        </section>
      </Spin>
    </div>
  );
}
