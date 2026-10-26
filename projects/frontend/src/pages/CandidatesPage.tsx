import { BankOutlined, BookOutlined, DeleteOutlined, LockOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import {
  Alert, Avatar, Button, Checkbox, Drawer, Empty, Form, Input, InputNumber, Modal, Pagination,
  Popconfirm, Select, Space, Tag, Tooltip, Upload,
} from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { saveCandidateWithReview } from '@/components/CandidateDuplicateReview';
import {
  deleteCandidate, fetchCandidates, importCandidates,
  parseResume, parseResumeUpload, uploadResume,
} from '@/services/candidate';
import type { CandidateClassificationSummary, CandidateRow } from '@/services/candidate';
import { fetchJobs } from '@/services/job';
import type { Job } from '@/services/job';
import { runScreening } from '@/services/screening';
import { useCurrentUser } from '@/services/user';
import { msg } from '@/utils/message';
import { downloadProtectedFile } from '@/services/http';
import { useBusinessRefresh } from '@/utils/useBusinessRefresh';

const SOURCE_TEXT: Record<string, string> = {
  manual: '手动录入', website: '官网投递', referral: '内部推荐',
  headhunt: '猎头', job_site: '招聘网站', campus: '校园招聘', import: '批量导入',
};

const RESUME_AUTOFILL_FIELDS = [
  'name', 'gender', 'phone', 'email', 'age', 'highest_education', 'major',
  'education', 'work_experience',
];

// 接口保存阶段编码，候选人页面统一展示业务中文名称。
const STAGE_TEXT: Record<string, string> = {
  new_resume: '简历初筛', pending_screen: '简历初筛', hr_screen_passed: '人力筛选',
  business_screen: '业务筛选', pending_interview: '待面试', interviewing: '面试中',
  interview_1: '一面', interview_2: '二面', interview_3: '三面', hrbp_interview: 'HRBP确认', hr_interview: '人力面',
  interview_passed: '面试阶段', offer_approval: '最终筛选', offer_pending: '录用通知', offer: '录用通知',
  pending_onboard: '待入职', onboarded: '已入职', eliminated: '已淘汰', abandoned: '已放弃',
  talent_pool: '人才库', written_test: '笔试', assessment: '测评', background_check: '背调',
  re_interview: '复试', custom: '自定义阶段',
};

function stageText(stage: string | undefined) {
  return STAGE_TEXT[stage ?? ''] ?? '其他阶段';
}

const CANDIDATE_STAGE_TABS = [
  { key: '', label: '全部候选人' },
  { key: 'pending_screen', label: '简历初筛' },
  { key: 'business_screen', label: '业务复筛' },
  { key: 'interview_1', label: '一面（业务）' },
  { key: 'interview_2', label: '二面（业务）' },
  { key: 'interview_3', label: '终面（业务）' },
  { key: 'hrbp_interview', label: 'HRBP面试' },
  { key: 'offer_approval', label: '录用审批' },
  { key: 'offer_pending', label: 'Offer' },
  { key: 'pending_onboard', label: '待入职' },
  { key: 'onboarded', label: '已入职' },
];

const EDUCATION_OPTIONS = ['初中', '高中', '中专', '大专', '本科', '硕士', '博士']
  .map((value) => ({ value, label: value }));

const SOURCE_FILTER_OPTIONS = [
  { value: 'manual', label: '手动录入' },
  { value: 'website', label: '官网投递' },
  { value: 'referral', label: '内部推荐' },
  { value: 'headhunt', label: '猎头' },
  { value: 'job_site', label: '招聘网站' },
  { value: 'campus', label: '校园招聘' },
  { value: 'import', label: '批量导入' },
];

const EMPTY_WORKBENCH_FILTERS = {
  assigned: '',
  unassigned: '',
  unprocessed: '',
  source_group: '',
  recommendation_status: '',
  action_state: '',
};

function filtersFromSearch(searchParams: URLSearchParams) {
  return {
    keyword: searchParams.get('keyword') ?? '',
    stage: searchParams.get('stage') ?? '',
    source: searchParams.get('source') ?? '',
    job_id: searchParams.get('job_id') ?? '',
    job_dept_id: searchParams.get('job_dept_id') ?? '',
    highest_education: searchParams.get('highest_education') ?? '',
    category: searchParams.get('category') ?? '',
    locked: searchParams.get('locked') ?? '',
    assigned: searchParams.get('assigned') ?? '',
    unassigned: searchParams.get('unassigned') ?? '',
    unprocessed: searchParams.get('unprocessed') ?? '',
    source_group: searchParams.get('source_group') ?? '',
    recommendation_status: searchParams.get('recommendation_status') ?? '',
    action_state: searchParams.get('action_state') ?? '',
    page: 1,
  };
}

export function CandidatesPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useCurrentUser();
  const canManage = user?.role === 'hr';
  const [list, setList] = useState<CandidateRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState(() => filtersFromSearch(searchParams));
  const previousSearch = useRef(searchParams.toString());
  useEffect(() => {
    if (previousSearch.current === searchParams.toString()) return;
    previousSearch.current = searchParams.toString();
    setFilters(filtersFromSearch(searchParams));
  }, [searchParams]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createLinkHandled, setCreateLinkHandled] = useState(false);
  const [form] = Form.useForm();
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeParsing, setResumeParsing] = useState(false);
  const [resumeParse, setResumeParse] = useState<Awaited<ReturnType<typeof parseResumeUpload>> | null>(null);
  const resumeParseRequestId = useRef(0);
  const resumeFormSnapshot = useRef<Record<string, unknown> | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [classification, setClassification] = useState<CandidateClassificationSummary | null>(null);
  const [loadError, setLoadError] = useState('');
  const listRequestId = useRef(0);

  const load = useCallback(async (silent = false) => {
    const requestId = ++listRequestId.current;
    setLoadError('');
    if (!silent) setLoading(true);
    try {
      const data = await fetchCandidates({
        keyword: filters.keyword || undefined,
        stage: filters.stage || undefined,
        source: filters.source || undefined,
        job_id: filters.job_id || undefined,
        job_dept_id: filters.job_dept_id || undefined,
        highest_education: filters.highest_education || undefined,
        category: filters.category || undefined,
        locked: filters.locked || undefined,
        assigned: filters.assigned || undefined,
        unassigned: filters.unassigned || undefined,
        unprocessed: filters.unprocessed || undefined,
        source_group: filters.source_group || undefined,
        recommendation_status: filters.recommendation_status || undefined,
        action_state: filters.action_state || undefined,
        include_summary: '1',
        page: filters.page, page_size: 10,
      });
      if (requestId !== listRequestId.current) return;
      setList(data.list);
      setTotal(data.total);
      setClassification(data.classification ?? null);
    } catch {
      if (requestId === listRequestId.current) {
        setLoadError('候选人数据加载失败，请重试');
        setClassification(null);
        setList([]);
        setTotal(0);
      }
    } finally {
      if (requestId === listRequestId.current) setLoading(false);
    }
  }, [filters]);
  const refresh = useCallback(() => load(true), [load]);
  useBusinessRefresh(refresh);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load(true);
    }, 15000);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (jobs.length) return;
    void fetchJobs({ page_size: 100 }).then((data) => setJobs(data.list));
  }, [jobs.length]);

  const jobCategories = useMemo(() => Array.from(
    new Map(
      jobs
        .filter((job) => job.dept_id && job.dept_name)
        .map((job) => [job.dept_id, { value: job.dept_id, label: job.dept_name }]),
    ).values(),
  ), [jobs]);

  const workbenchFilterLabel = useMemo(() => {
    if (filters.unassigned === '1') return '待分配（未关联职位）';
    if (filters.unprocessed === '1') return '未处理（已关联职位、等待初筛）';
    if (filters.assigned === '1' && filters.stage === 'pending_screen') return '未处理（已分配职位）';
    if (filters.source) return `来源渠道：${SOURCE_TEXT[filters.source] ?? filters.source}`;
    if (filters.source_group === 'talent_recommendation') return '人才推荐';
    if (filters.recommendation_status === 'pending') return '推荐待反馈';
    if (filters.recommendation_status === 'passed') return '推荐通过';
    if (filters.recommendation_status === 'failed') return '推荐不通过';
    if (filters.action_state === 'awaiting_interview_schedule') return '待安排面试';
    return '';
  }, [filters.action_state, filters.assigned, filters.recommendation_status,
    filters.source_group, filters.stage, filters.unassigned, filters.unprocessed]);

  useEffect(() => {
    if (!canManage || createLinkHandled || searchParams.get('create') !== '1') return;
    form.resetFields();
    setResumeFile(null);
    setResumeParse(null);
    setDrawerOpen(true);
    setCreateLinkHandled(true);
  }, [canManage, createLinkHandled, form, searchParams]);

  function closeCreateDrawer() {
    resumeParseRequestId.current += 1;
    resumeFormSnapshot.current = null;
    setDrawerOpen(false);
    setResumeFile(null);
    setResumeParse(null);
    setResumeParsing(false);
    form.resetFields();
  }

  function restoreFormBeforeResume() {
    const snapshot = resumeFormSnapshot.current ?? {};
    form.setFieldsValue(Object.fromEntries(
      RESUME_AUTOFILL_FIELDS.map((field) => [field, snapshot[field]]),
    ));
  }

  function removeSelectedResume() {
    resumeParseRequestId.current += 1;
    restoreFormBeforeResume();
    resumeFormSnapshot.current = null;
    setResumeFile(null);
    setResumeParse(null);
    setResumeParsing(false);
    msg.success('已移除当前简历，可重新选择文件');
  }

  async function attachResume(candidateId: number, jobId: number) {
    if (!resumeFile) return;
    try {
      const uploaded = await uploadResume(resumeFile, candidateId, jobId);
      const parsed = await parseResume(uploaded.attachment_id);
      if (parsed.parse_status === 'system') {
        msg.success('候选人已创建，简历已上传并解析');
      } else {
        msg.warning('候选人已创建，简历已上传，但未识别出基础信息');
      }
    } catch {
      msg.warning('候选人已创建，但简历附件上传失败，可在详情页重新上传');
    }
  }

  async function handleResumeParse(file: File) {
    if (!resumeFile) {
      resumeFormSnapshot.current = form.getFieldsValue(RESUME_AUTOFILL_FIELDS);
    } else {
      restoreFormBeforeResume();
    }
    const requestId = resumeParseRequestId.current + 1;
    resumeParseRequestId.current = requestId;
    setResumeFile(file);
    setResumeParse(null);
    setResumeParsing(true);
    try {
      const result = await parseResumeUpload(file);
      if (resumeParseRequestId.current !== requestId) return;
      setResumeParse(result);
      if (result.parse_status === 'system') {
        const current = form.getFieldsValue(true);
        form.setFieldsValue({
          name: result.fields.name || current.name,
          gender: result.fields.gender || current.gender,
          phone: result.fields.phone || current.phone,
          email: result.fields.email || current.email,
          age: result.fields.age ?? current.age,
          highest_education: result.fields.highest_education || current.highest_education,
          major: result.fields.major || current.major,
          education: result.fields.education || current.education || [],
          work_experience: result.fields.work_experience || current.work_experience || [],
        });
        msg.success('简历解析完成，请核对自动填充的信息');
      } else {
        msg.warning('未能识别出基础信息，请手工填写');
      }
    } catch {
      if (resumeParseRequestId.current !== requestId) return;
      msg.error('简历解析失败，请确认文件为可读取的 PDF 或 DOCX');
    } finally {
      if (resumeParseRequestId.current === requestId) setResumeParsing(false);
    }
  }

  async function handleCreate() {
    if (creating || resumeParsing) return;
    setCreating(true);
    try {
      await performCreate();
    } finally {
      setCreating(false);
    }
  }

  async function performCreate() {
    const values = await form.validateFields();
    const payload = {
      ...values,
      job_id: Number(values.job_id),
      gender: values.gender || resumeParse?.fields.gender || '',
      age: values.age ?? resumeParse?.fields.age ?? null,
      highest_education: values.highest_education || resumeParse?.fields.highest_education || '',
      major: values.major || resumeParse?.fields.major || '',
      education: values.education?.length ? values.education : resumeParse?.fields.education ?? [],
      work_experience: values.work_experience?.length ? values.work_experience : resumeParse?.fields.work_experience ?? [],
    };
    const result = await saveCandidateWithReview(null, payload);
    if (!result) return;
    if (result.candidate?.id) {
      await attachResume(result.candidate.id, Number(values.job_id));
      const application = result.application;
      if (application && resumeFile) {
        try {
          await runScreening(application.id);
          msg.success('候选人已创建，并生成智能匹配结果');
        } catch {
          msg.warning('候选人已创建，但智能匹配暂未完成，可在详情页重新分析');
        }
      }
    }
    msg.success(result.merged ? '已合并到已有候选人主档' : '候选人已创建');
    closeCreateDrawer();
    void load();
  }

  function openCreateDrawer() {
    resumeParseRequestId.current += 1;
    resumeFormSnapshot.current = null;
    form.resetFields();
    setResumeFile(null);
    setResumeParse(null);
    setResumeParsing(false);
    setDrawerOpen(true);
  }

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">候选人</h2>
        <Space>
          {canManage && <Button icon={<UploadOutlined />} onClick={() => void downloadProtectedFile('/api/candidates/import-template', 'candidate_template.csv')}>导入模板</Button>}
          {canManage && <Button onClick={() => void downloadProtectedFile('/api/candidates/export', 'candidates.csv')}>导出</Button>}
          {canManage && <Button type="primary" icon={<PlusOutlined />} onClick={openCreateDrawer}>
            新增候选人
          </Button>}
        </Space>
      </div>
      <section className="candidate-stage-classifier">
        <div className="candidate-stage-main">
          <div className="candidate-stage-scroll">
            {CANDIDATE_STAGE_TABS.map((stage) => (
              <button
                type="button"
                key={stage.key}
                className={filters.stage === stage.key ? 'is-active' : ''}
                onClick={() => setFilters((current) => ({
                  ...current, ...EMPTY_WORKBENCH_FILTERS,
                  stage: stage.key, category: '', page: 1,
                }))}
              >
                <span>{stage.label}</span>
              </button>
            ))}
          </div>
          <div className="candidate-stage-actions">
            <button
              type="button"
              className={`candidate-unassigned${filters.unassigned === '1' ? ' is-active' : ''}`}
              onClick={() => setFilters((current) => ({
                ...current, ...EMPTY_WORKBENCH_FILTERS,
                category: '', unassigned: '1', page: 1,
              }))}
            >
              待分配 <strong>{loading ? '…' : classification?.unassigned ?? '—'}</strong>
            </button>
          </div>
        </div>
        <div className="candidate-stage-subtabs">
          <button
            type="button"
            className={filters.unprocessed === '1' ? 'is-active' : ''}
            onClick={() => setFilters((current) => ({
              ...current, ...EMPTY_WORKBENCH_FILTERS,
              category: '', unprocessed: '1', page: 1,
            }))}
          >
            未处理 <strong>{loading ? '…' : classification?.categories.unprocessed ?? '—'}</strong>
          </button>
          <button
            type="button"
            className={filters.category === 'pending' ? 'is-active' : ''}
            onClick={() => setFilters((current) => ({
              ...current, ...EMPTY_WORKBENCH_FILTERS,
              category: 'pending', page: 1,
            }))}
          >
            待定 <strong>{loading ? '…' : classification?.categories.pending ?? '—'}</strong>
          </button>
          <button
            type="button"
            className={filters.category === 'recommended' || filters.source_group === 'talent_recommendation' ? 'is-active' : ''}
            onClick={() => setFilters((current) => ({
              ...current, ...EMPTY_WORKBENCH_FILTERS,
              category: 'recommended', page: 1,
            }))}
          >
            人才推荐 <strong>{loading ? '…' : classification?.categories.recommended ?? '—'}</strong>
          </button>
        </div>
        <div style={{ marginTop: 8, color: '#8c8c8c', fontSize: 12 }}
          title="各子分类可能重叠，不是全部候选人的互斥分组；点击后的数字与列表总人数对应。">
          统计范围：{CANDIDATE_STAGE_TABS.find((stage) => stage.key === filters.stage)?.label || '当前阶段'}及当前筛选条件，按候选人去重
        </div>
      </section>
      {!loading && !classification && <Alert
        type="warning" showIcon style={{ marginBottom: 12 }}
        message={loadError || '统计接口尚未更新，请重启后端加载新版本后刷新页面'}
      />}
      <div className="hrats-block">
        <div className="candidate-filter-toolbar">
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="应聘职位"
            value={filters.job_id || undefined}
            options={jobs.map((job) => ({ value: String(job.id), label: job.name }))}
            onChange={(value) => setFilters((current) => ({
              ...current, job_id: value ?? '', page: 1,
            }))}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="职位分类"
            value={filters.job_dept_id || undefined}
            options={jobCategories}
            onChange={(value) => setFilters((current) => ({
              ...current, job_dept_id: value ?? '', page: 1,
            }))}
          />
          <Select
            allowClear
            placeholder="最高学历"
            value={filters.highest_education || undefined}
            options={EDUCATION_OPTIONS}
            onChange={(value) => setFilters((current) => ({
              ...current, highest_education: value ?? '', page: 1,
            }))}
          />
          <Select
            allowClear
            placeholder="来源渠道"
            value={filters.source || undefined}
            options={SOURCE_FILTER_OPTIONS}
            onChange={(value) => setFilters((current) => ({
              ...current, source: value ?? '', source_group: '', page: 1,
            }))}
          />
          <Tooltip title="更多筛选">
            <Button
              className={showAdvancedFilters ? 'is-active' : ''}
              icon={<PlusOutlined />}
              onClick={() => setShowAdvancedFilters((value) => !value)}
            />
          </Tooltip>
          {showAdvancedFilters && (
            <Select
              placeholder="锁定状态"
              allowClear
              value={filters.locked || undefined}
              onChange={(value) => setFilters((current) => ({
                ...current, locked: value ?? '', page: 1,
              }))}
              options={[{ value: '1', label: '锁定中' }]}
            />
          )}
        </div>
        {workbenchFilterLabel && (
          <Space style={{ marginBottom: 12 }} wrap>
            <span>当前子分类：</span>
            <Tag
              color="blue"
              closable
              onClose={(event) => {
                event.preventDefault();
                setFilters((current) => ({
                  ...current, ...EMPTY_WORKBENCH_FILTERS, source: '', page: 1,
                }));
              }}
            >
              {workbenchFilterLabel}
            </Tag>
          </Space>
        )}
        <Space style={{ marginBottom: 12 }} wrap>
          <Input.Search
            key={filters.keyword}
            defaultValue={filters.keyword}
            placeholder="姓名/手机/邮箱" allowClear style={{ width: 220 }}
            onSearch={(v) => setFilters((f) => ({
              ...f, keyword: v, page: 1,
            }))}
          />
        </Space>
        {loading ? <PageLoading /> : (
          <>
            <div className="candidate-card-select-all">
              <Checkbox
                indeterminate={selectedIds.length > 0 && list.some((item) => !selectedIds.includes(item.id))}
                checked={list.length > 0 && list.every((item) => selectedIds.includes(item.id))}
                onChange={(event) => {
                  const pageIds = list.map((item) => item.id);
                  setSelectedIds((current) => event.target.checked
                    ? Array.from(new Set([...current, ...pageIds]))
                    : current.filter((id) => !pageIds.includes(id)));
                }}
              >
                全选本页
              </Checkbox>
              <span>共 {total} 位候选人</span>
            </div>
            <div className="candidate-profile-list">
              {list.length === 0 ? <Empty description="暂无候选人" /> : list.map((record) => {
                const tags = (record.tags || '').split(/[,，]/).map((item) => item.trim()).filter(Boolean).slice(0, 3);
                const work = record.work_summary || {};
                const education = record.education_summary || {};
                const lockOwnerId = record.lock?.owner_id || record.owner_id;
                const lockedByOther = Boolean(lockOwnerId && user?.role === 'hr' && lockOwnerId !== user.user_id);
                return (
                  <article
                    className="candidate-profile-card"
                    key={record.id}
                    onClick={() => navigate(`/candidates/${record.id}${record.application_id ? `?application_id=${record.application_id}` : ''}`)}
                  >
                    <div className="candidate-card-checkbox" onClick={(event) => event.stopPropagation()}>
                      <Checkbox
                        checked={selectedIds.includes(record.id)}
                        onChange={(event) => setSelectedIds((current) => event.target.checked
                          ? Array.from(new Set([...current, record.id]))
                          : current.filter((id) => id !== record.id))}
                      />
                    </div>
                    <Avatar className="candidate-card-avatar" size={58}>
                      {record.name?.slice(0, 1) || '候'}
                    </Avatar>
                    <div className="candidate-card-main">
                      <div className="candidate-card-name-row">
                        <strong>{record.name}</strong>
                        {record.lock && (
                          <Tooltip title={`锁定中：${record.lock.start_at} ~ ${record.lock.end_at}`}>
                            <Tag icon={<LockOutlined />} color="error">已锁定</Tag>
                          </Tooltip>
                        )}
                        {tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}
                      </div>
                      <div className="candidate-card-brief">
                        <span>{record.gender || '未知'}</span><i />
                        <span>{record.age ? `${record.age}岁` : '年龄未知'}</span><i />
                        <span>{record.city || '城市未填写'}</span>
                      </div>
                      <div className="candidate-card-history">
                        <div className="candidate-history-work">
                          <BankOutlined />
                          <span className="candidate-history-date">{work.start || '时间未填写'} 至 {work.end || '至今'}</span>
                          <strong>{work.company || '暂无工作经历'}</strong>
                        </div>
                        <div className="candidate-history-education">
                          <BookOutlined />
                          <span className="candidate-history-date">{education.graduate_at || '时间未填写'}</span>
                          <strong>{education.degree || record.highest_education || '学历未填写'}</strong>
                          <span>{education.school || '学校未填写'}</span>
                        </div>
                      </div>
                    </div>
                    <div className="candidate-card-side">
                      <Tag color="blue">{stageText(record.current_stage)}</Tag>
                      {record.latest_application?.process_state_label && (
                        <Tag color={record.latest_application.process_state_key === 'interview_evaluated' ? 'success' : 'gold'}>
                          {record.latest_application.process_state_label}
                        </Tag>
                      )}
                      {record.latest_application?.screening_score != null && (
                        <Tag color={(record.latest_application.screening_review_decision || record.latest_application.screening_decision) === 'pass' ? 'success' : 'gold'}>
                          智能匹配 {record.latest_application.screening_score}%
                        </Tag>
                      )}
                      <span>{record.latest_application?.job_name || '待分配职位'}</span>
                      <span>招聘 HR：{record.owner_name || '未分配'}</span>
                      <span>
                        当前处理：{record.latest_application?.current_handler_name
                          || (record.latest_application?.process_state_role === 'hr' ? record.owner_name : '')
                          || '按当前阶段处理'}
                      </span>
                      <span>来源：{(SOURCE_TEXT[record.source] ?? record.source) || '-'}</span>
                    </div>
                    {canManage && (
                      <div className="candidate-card-actions" onClick={(event) => event.stopPropagation()}>
                        <Popconfirm
                          title="删除候选人？将彻底删除其资料、附件及全部招聘关联数据"
                          disabled={lockedByOther}
                          onConfirm={async () => {
                            await deleteCandidate(record.id);
                            msg.success('候选人及关联数据已彻底删除');
                            setSelectedIds((current) => current.filter((id) => id !== record.id));
                            void load();
                          }}
                        >
                          <Button type="text" danger icon={<DeleteOutlined />} disabled={lockedByOther} />
                        </Popconfirm>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
            {total > 10 && (
              <Pagination
                className="candidate-card-pagination"
                current={filters.page}
                pageSize={10}
                total={total}
                showSizeChanger={false}
                onChange={(page) => setFilters((current) => ({ ...current, page }))}
              />
            )}
          </>
        )}
      </div>

      <Drawer
        title="新增候选人" width={480} open={drawerOpen}
        forceRender onClose={closeCreateDrawer}
        closable={!creating} maskClosable={!creating} keyboard={!creating}
        extra={(
          <Space>
            <Button disabled={creating} onClick={closeCreateDrawer}>取消</Button>
            <Button type="primary" loading={creating} disabled={resumeParsing} onClick={() => void handleCreate()}>保存</Button>
          </Space>
        )}
      >
        <Form form={form} layout="vertical" disabled={creating}>
          <Form.Item
            name="job_id" label="应聘职位"
            rules={[{ required: true, message: '请选择应聘职位后再保存' }]}
          >
            <Select
              allowClear showSearch optionFilterProp="label"
              placeholder="请选择应聘职位（必选）"
              options={jobs.map((job) => ({ value: job.id, label: job.name }))}
            />
          </Form.Item>
          <Form.Item label="新增方式">
            <Space wrap>
              <Upload
                accept=".pdf,.docx,.jpg,.jpeg,.png" showUploadList={false}
                beforeUpload={(file) => {
                  void handleResumeParse(file as File);
                  return false;
                }}
              >
                <Button icon={<UploadOutlined />} loading={resumeParsing}>
                  上传简历并解析
                </Button>
              </Upload>
              <Upload
                accept=".csv,.xlsx"
                showUploadList={false}
                beforeUpload={async (file) => {
                  try {
                    await form.validateFields(['job_id']);
                  } catch {
                    msg.warning('请先选择应聘职位后再批量导入');
                    return false;
                  }
                  const result = await importCandidates(file as File, Number(form.getFieldValue('job_id')));
                  let confirmed = 0;
                  let merged = 0;
                  for (const row of result.duplicates) {
                    if (!row.payload || !row.review) continue;
                    const saved = await saveCandidateWithReview(null, row.payload, row.review);
                    if (saved) {
                      confirmed += 1;
                      if (saved.merged) merged += 1;
                    }
                  }
                  closeCreateDrawer();
                  Modal.info({
                    title: '批量导入结果',
                    content: `新建 ${result.success_count + confirmed - merged} 条；合并 ${merged} 条；未确认 ${result.duplicates.length - confirmed} 条（未保存，可重新导入）；失败 ${result.errors.length} 条`,
                  });
                  void load();
                  return false;
                }}
              >
                <Button>批量导入名单</Button>
              </Upload>
            </Space>
            {resumeFile && (
              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ color: 'rgba(23,26,29,0.65)', overflowWrap: 'anywhere' }}>
                  已选择：{resumeFile.name}
                </span>
                <Popconfirm
                  title="删除当前简历？"
                  description="将清除该简历的解析结果和自动填入内容"
                  okText="删除"
                  cancelText="取消"
                  onConfirm={removeSelectedResume}
                >
                  <Button type="link" danger size="small" icon={<DeleteOutlined />} disabled={resumeParsing}>
                    删除简历
                  </Button>
                </Popconfirm>
              </div>
            )}
            {resumeParse && (
              <Alert
                style={{ marginTop: 8 }}
                type={resumeParse.parse_status === 'system' ? 'success' : 'warning'}
                showIcon
                message={resumeParse.message}
                description={(
                  <div>
                    <div>{'\u6027\u522b'}：{resumeParse.fields.gender || '-'}</div>
                    <div>姓名：{resumeParse.fields.name || '-'}；手机：{resumeParse.fields.phone || '-'}；邮箱：{resumeParse.fields.email || '-'}</div>
                    <div>年龄：{resumeParse.fields.age ? `${resumeParse.fields.age} 岁` : '-'}；最高学历：{resumeParse.fields.highest_education || '-'}；专业：{resumeParse.fields.major || '-'}</div>
                    <div style={{ marginTop: 4 }}>教育经历：{resumeParse.fields.education?.length || 0} 条（保存后可在候选人详情中维护）</div>
                    <div style={{ marginTop: 4 }}>{'\u5DE5\u4F5C\u7ECF\u5386'}：{resumeParse.fields.work_experience?.length || 0} 条（保存后可在候选人详情中维护）</div>
                    {resumeParse.fields._parse_meta && (
                      <div style={{ marginTop: 8 }}>
                        解析方式：{{ text: '文本规则', ocr: '本地 OCR', 'text+ai': '文本规则 + AI', 'ocr+ai': 'OCR + AI', failed: '未识别' }[resumeParse.fields._parse_meta.method] ?? resumeParse.fields._parse_meta.method}
                        ；置信度：{resumeParse.fields._parse_meta.confidence}%
                        {resumeParse.fields._parse_meta.warnings.map((warning) => (
                          <div key={warning} style={{ color: '#ad6800' }}>请核对：{warning}</div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              />
            )}
          </Form.Item>
          <Form.Item name="name" label="姓名" rules={[{ required: true, message: '必填' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="gender" label="性别">
            <Select allowClear options={[{ value: '男', label: '男' }, { value: '女', label: '女' }]} />
          </Form.Item>
          <Form.Item name="phone" label="手机号">
            <Input />
          </Form.Item>
          <Form.Item name="email" label="邮箱">
            <Input />
          </Form.Item>
          <Form.Item name="age" label="年龄">
            <InputNumber min={16} max={75} precision={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="highest_education" label="最高学历">
            <Select allowClear options={['初中', '高中', '中专', '大专', '本科', '硕士', '博士'].map((value) => ({ value, label: value }))} />
          </Form.Item>
          <Form.Item name="major" label="专业">
            <Input />
          </Form.Item>
          <Form.Item name="tags" label="标签（逗号分隔）">
            <Input />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Drawer>

    </div>
  );
}
