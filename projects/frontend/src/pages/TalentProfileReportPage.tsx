import {
  ArrowLeftOutlined,
  DownloadOutlined,
  ExpandOutlined,
  ReloadOutlined,
  SearchOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { Button, DatePicker, Empty, Select, Spin } from 'antd';
import type { Dayjs } from 'dayjs';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { fetchJobs } from '@/services/job';
import { fetchTalentProfileReport } from '@/services/report';
import type { ReportFilters, TalentProfileReport } from '@/services/report';
import { fetchRequirements } from '@/services/requirement';
import { fetchDepartments } from '@/services/system';
import { fetchPipelineTemplates } from '@/services/template';

type DistributionRow = { name: string; value: number };

const EMPTY_REPORT: TalentProfileReport = {
  total: 0,
  gender: [],
  work_experience: [],
  age: [],
  highest_education: [],
  channel_type: [],
  graduation_school: [],
  latest_employer: [],
  profession: [],
};

const PIE_COLORS = ['#62d2ac', '#59b4ee', '#ffc65b', '#ff7d7d', '#c9bbfa', '#b9e9dd', '#a5cdf0', '#ff9d59'];

function DonutPanel({ title, rows }: { title: string; rows: DistributionRow[] }) {
  const ref = useRef<HTMLElement>(null);
  const total = rows.reduce((sum, item) => sum + item.value, 0);
  const segments = useMemo(() => {
    let offset = 0;
    return rows.map((item, index) => {
      const percent = total ? item.value / total * 100 : 0;
      const segment = {
        ...item,
        color: PIE_COLORS[index % PIE_COLORS.length],
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

  const download = () => {
    const body = rows.map((item) => `${item.name},${item.value}`).join('\n');
    const url = URL.createObjectURL(new Blob([`\ufeff分类,人数\n${body}`], { type: 'text/csv;charset=utf-8' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${title}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="talent-profile-panel" ref={ref}>
      <div className="talent-profile-panel-head">
        <h3>{title}</h3>
        <div>
          <Button type="text" size="small" icon={<UnorderedListOutlined />} onClick={download}>明细</Button>
          <Button type="text" size="small" icon={<DownloadOutlined />} onClick={download}>下载</Button>
          <Button type="text" size="small" icon={<ExpandOutlined />} onClick={() => void ref.current?.requestFullscreen()}>放大</Button>
        </div>
      </div>
      {total <= 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
      ) : (
        <div className="talent-profile-donut-wrap">
          <div className="talent-profile-donut" style={{ background }}>
            <div><strong>{total}</strong><span>候选人</span></div>
          </div>
          <div className="talent-profile-legend">
            {segments.map((item) => (
              <div key={item.name}>
                <i style={{ background: item.color }} />
                <span>{item.name}</span>
                <strong>{item.value}（{item.percent.toFixed(2)}%）</strong>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function BarPanel({ title, rows }: { title: string; rows: DistributionRow[] }) {
  const max = Math.max(...rows.map((item) => item.value), 0);
  return (
    <section className="talent-profile-panel talent-profile-school-panel">
      <div className="talent-profile-panel-head"><h3>{title}</h3></div>
      {max <= 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
      ) : (
        <div className="talent-profile-school-chart">
          {rows.slice(0, 20).map((item) => (
            <div className="talent-profile-school-row" key={item.name}>
              <span title={item.name}>{item.name}</span>
              <div><i style={{ width: `${Math.max(item.value / max * 100, 2)}%` }} /></div>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function TalentProfileReportPage() {
  const navigate = useNavigate();
  const [report, setReport] = useState<TalentProfileReport>(EMPTY_REPORT);
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null);
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
      setReport(await fetchTalentProfileReport(filters));
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
      date_from: dateRange?.[0].format('YYYY-MM-DD'),
      date_to: dateRange?.[1].format('YYYY-MM-DD'),
    });
  };

  const resetFilters = () => {
    setDateRange(null);
    setDraftFilters({});
    setFilters({});
  };

  return (
    <div className="talent-profile-page">
      <div className="talent-profile-heading">
        <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate('/reports')}>返回</Button>
        <h2>人才画像</h2>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
      </div>

      <section className="talent-profile-toolbar">
        <DatePicker.RangePicker
          value={dateRange}
          placeholder={['投递开始时间', '投递结束时间']}
          onChange={(value) => setDateRange(value as [Dayjs, Dayjs] | null)}
        />
        <Select allowClear placeholder="招聘流程" value={draftFilters.template_id} options={templates}
          onChange={(value) => setDraftFilters((current) => ({ ...current, template_id: value }))} />
        <Select allowClear showSearch optionFilterProp="label" placeholder="需求名称"
          value={draftFilters.requirement_id} options={requirements}
          onChange={(value) => setDraftFilters((current) => ({ ...current, requirement_id: value }))} />
        <Select allowClear showSearch optionFilterProp="label" placeholder="职位名称"
          value={draftFilters.job_id} options={jobs}
          onChange={(value) => setDraftFilters((current) => ({ ...current, job_id: value }))} />
        <Select allowClear showSearch optionFilterProp="label" placeholder="来源渠道"
          value={draftFilters.source}
          options={[
            { value: 'website', label: '官网投递' }, { value: 'job_site', label: '招聘网站' },
            { value: 'campus', label: '校园招聘' }, { value: 'referral', label: '内部推荐' },
            { value: 'headhunt', label: '猎头' }, { value: 'manual', label: '手动录入' },
          ]}
          onChange={(value) => setDraftFilters((current) => ({ ...current, source: value }))} />
        <Select allowClear placeholder="简历状态" value={draftFilters.resume_status}
          options={[{ value: 'active', label: '有效' }, { value: 'archived', label: '已归档' }]}
          onChange={(value) => setDraftFilters((current) => ({ ...current, resume_status: value }))} />
        <Select allowClear showSearch optionFilterProp="label" placeholder="猎头供应商"
          value={draftFilters.headhunter_supplier}
          options={[]}
          onChange={(value) => setDraftFilters((current) => ({ ...current, headhunter_supplier: value }))} />
        <Select allowClear placeholder="投递门户方案" value={draftFilters.portal_plan}
          options={[{ value: 'default', label: '默认方案' }]}
          onChange={(value) => setDraftFilters((current) => ({ ...current, portal_plan: value }))} />
        <Button type="primary" icon={<SearchOutlined />} onClick={applyFilters}>查询</Button>
        <Button onClick={resetFilters}>重置</Button>
      </section>

      <Spin spinning={loading}>
        <div className="talent-profile-grid">
          <DonutPanel title="性别分布" rows={report.gender} />
          <DonutPanel title="工作经验分布" rows={report.work_experience} />
          <DonutPanel title="年龄分布" rows={report.age} />
          <DonutPanel title="最高学历分布" rows={report.highest_education} />
          <DonutPanel title="渠道类型分布" rows={report.channel_type} />
          <BarPanel title="毕业院校" rows={report.graduation_school} />
          <BarPanel title="最新受聘公司分布" rows={report.latest_employer} />
          <BarPanel title="专业分布" rows={report.profession} />
        </div>
      </Spin>
    </div>
  );
}
