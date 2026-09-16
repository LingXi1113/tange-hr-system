import {
  ArrowLeftOutlined,
  DownloadOutlined,
  ExpandOutlined,
  ReloadOutlined,
  SearchOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { Button, DatePicker, Empty, Select, Spin, Table } from 'antd';
import type { Dayjs } from 'dayjs';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { fetchJobs } from '@/services/job';
import { fetchStageFunnelReport } from '@/services/report';
import type { ReportFilters, StageFunnelReport } from '@/services/report';
import { fetchRequirements } from '@/services/requirement';
import { fetchPlatformUsers } from '@/services/system';
import { fetchPipelineTemplates } from '@/services/template';

const EMPTY_REPORT: StageFunnelReport = {
  total: 0,
  stage_funnel: [],
  interview_funnel: [],
  current_stages: [],
};

interface FunnelRow {
  name: string;
  count: number;
  previous_rate: number;
  overall_rate: number;
}

function FunnelGraphic({ rows }: { rows: FunnelRow[] }) {
  const max = Math.max(...rows.map((item) => item.count), 0);
  if (max <= 0) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />;

  return (
    <div className="stage-funnel-graphic">
      {rows.map((item, index) => (
        <div className="stage-funnel-level" key={`${item.name}-${index}`}>
          <div
            className="stage-funnel-shape"
            style={{
              width: `${Math.max(item.count / max * 100, 24)}%`,
              opacity: Math.max(1 - index * 0.055, 0.55),
            }}
          >
            <strong>{item.name}</strong>
            <span>{item.count}人</span>
          </div>
          <small>环节转化率 {item.previous_rate}% · 总转化率 {item.overall_rate}%</small>
        </div>
      ))}
    </div>
  );
}

function CurrentStageChart({ rows }: { rows: StageFunnelReport['current_stages'] }) {
  const visibleRows = rows.filter((item) => item.count > 0);
  const max = Math.max(...visibleRows.map((item) => item.count), 0);
  if (max <= 0) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />;

  return (
    <div className="stage-current-chart">
      {visibleRows.map((item) => (
        <div className="stage-current-row" key={item.stage_key}>
          <span>{item.name}</span>
          <div><i style={{ width: `${Math.max(item.count / max * 100, 2)}%` }} /></div>
          <strong>{item.count}人</strong>
        </div>
      ))}
    </div>
  );
}

export function StageFunnelReportPage() {
  const navigate = useNavigate();
  const stagePanelRef = useRef<HTMLElement>(null);
  const [report, setReport] = useState<StageFunnelReport>(EMPTY_REPORT);
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [draftFilters, setDraftFilters] = useState<ReportFilters>({});
  const [filters, setFilters] = useState<ReportFilters>({});
  const [templates, setTemplates] = useState<{ value: number; label: string }[]>([]);
  const [owners, setOwners] = useState<{ value: string; label: string }[]>([]);
  const [jobs, setJobs] = useState<{ value: number; label: string }[]>([]);
  const [requirements, setRequirements] = useState<{ value: number; label: string }[]>([]);
  const [showDetail, setShowDetail] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setReport(await fetchStageFunnelReport(filters));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void Promise.all([
      fetchPipelineTemplates(1, 100),
      fetchPlatformUsers(),
      fetchJobs({ page_size: 100 }),
      fetchRequirements({ page_size: 100 }),
    ]).then(([templateData, userData, jobData, requirementData]) => {
      setTemplates(templateData.list.map((item) => ({ value: item.id, label: item.name })));
      setOwners(userData
        .filter((item) => item.role === 'hr')
        .map((item) => ({ value: item.user_id, label: item.name })));
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

  const downloadDetail = () => {
    const header = '阶段,人数,环节转化率,总转化率\n';
    const body = report.stage_funnel
      .map((item) => `${item.name},${item.count},${item.previous_rate}%,${item.overall_rate}%`)
      .join('\n');
    const url = URL.createObjectURL(new Blob([`\ufeff${header}${body}`], { type: 'text/csv;charset=utf-8' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = '阶段转化漏斗.csv';
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="stage-funnel-page">
      <div className="stage-funnel-heading">
        <Button type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate('/reports')}>返回</Button>
        <h2>阶段转化漏斗</h2>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
      </div>

      <section className="stage-funnel-toolbar">
        <Select
          allowClear placeholder="招聘流程" value={draftFilters.template_id} options={templates}
          onChange={(value) => setDraftFilters((current) => ({ ...current, template_id: value }))}
        />
        <DatePicker.RangePicker
          value={dateRange}
          placeholder={['操作开始时间', '操作结束时间']}
          onChange={(value) => setDateRange(value as [Dayjs, Dayjs] | null)}
        />
        <Select
          allowClear showSearch optionFilterProp="label" placeholder="职位负责人"
          value={draftFilters.owner_id} options={owners}
          onChange={(value) => setDraftFilters((current) => ({ ...current, owner_id: value }))}
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
        <section className="stage-funnel-panel is-primary" ref={stagePanelRef}>
          <div className="stage-funnel-panel-head">
            <h3>阶段转换漏斗</h3>
            <div>
              <Button type="text" size="small" icon={<UnorderedListOutlined />} onClick={() => setShowDetail((value) => !value)}>明细</Button>
              <Button type="text" size="small" icon={<DownloadOutlined />} onClick={downloadDetail}>下载</Button>
              <Button type="text" size="small" icon={<ExpandOutlined />} onClick={() => void stagePanelRef.current?.requestFullscreen()}>放大</Button>
            </div>
          </div>
          <FunnelGraphic rows={report.stage_funnel} />
          {showDetail && (
            <Table
              className="stage-funnel-detail"
              rowKey="stage_key"
              size="small"
              pagination={false}
              dataSource={report.stage_funnel}
              columns={[
                { title: '阶段', dataIndex: 'name' },
                { title: '人数', dataIndex: 'count' },
                { title: '环节转化率', dataIndex: 'previous_rate', render: (value) => `${value}%` },
                { title: '总转化率', dataIndex: 'overall_rate', render: (value) => `${value}%` },
              ]}
            />
          )}
        </section>

        <section className="stage-funnel-panel">
          <div className="stage-funnel-panel-head"><h3>面试轮次漏斗</h3></div>
          <FunnelGraphic rows={report.interview_funnel} />
        </section>

        <section className="stage-funnel-panel">
          <div className="stage-funnel-panel-head"><h3>阶段当前简历数</h3></div>
          <CurrentStageChart rows={report.current_stages} />
        </section>
      </Spin>
    </div>
  );
}
