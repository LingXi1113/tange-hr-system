import { BankOutlined, BookOutlined, DeleteOutlined, LockOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import {
  Alert, Avatar, Button, Checkbox, Drawer, Empty, Form, Input, InputNumber, Modal, Pagination,
  Popconfirm, Select, Space, Tag, Tooltip, Upload,
} from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import {
  assignJob, deleteCandidate, fetchCandidateClassificationSummary, fetchCandidates, importCandidates,
  parseResume, parseResumeUpload, saveCandidate, uploadResume,
} from '@/services/candidate';
import type { CandidateClassificationSummary, CandidateRow } from '@/services/candidate';
import { fetchJobs } from '@/services/job';
import type { Job } from '@/services/job';
import { addToPool } from '@/services/talentPool';
import { useCurrentUser } from '@/services/user';
import { msg } from '@/utils/message';
import { downloadProtectedFile } from '@/services/http';

const SOURCE_TEXT: Record<string, string> = {
  manual: '手动录入', website: '官网投递', referral: '内部推荐',
  headhunt: '猎头', job_site: '招聘网站', campus: '校园招聘', import: '批量导入',
};

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

export function CandidatesPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useCurrentUser();
  const canManage = user?.role === 'hr';
  const [list, setList] = useState<CandidateRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState(() => ({
    keyword: searchParams.get('keyword') ?? '',
    stage: searchParams.get('stage') ?? (searchParams.get('source') ? '' : 'pending_screen'),
    source: searchParams.get('source') ?? '',
    job_id: '',
    job_dept_id: '',
    highest_education: '',
    category: '',
    locked: '',
    page: 1,
  }));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [createLinkHandled, setCreateLinkHandled] = useState(false);
  const [form] = Form.useForm();
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [batchPoolOpen, setBatchPoolOpen] = useState(false);
  const [batchPoolCategory, setBatchPoolCategory] = useState('');
  const [batchPoolReason, setBatchPoolReason] = useState('');
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeParsing, setResumeParsing] = useState(false);
  const [resumeParse, setResumeParse] = useState<Awaited<ReturnType<typeof parseResumeUpload>> | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [classification, setClassification] = useState<CandidateClassificationSummary | null>(null);

  const loadClassification = useCallback(async () => {
    setClassification(await fetchCandidateClassificationSummary());
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
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
        page: filters.page, page_size: 10,
      });
      setList(data.list);
      setTotal(data.total);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void loadClassification();
  }, [loadClassification]);

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

  useEffect(() => {
    if (!canManage || createLinkHandled || searchParams.get('create') !== '1') return;
    form.resetFields();
    setResumeFile(null);
    setResumeParse(null);
    setDrawerOpen(true);
    setCreateLinkHandled(true);
  }, [canManage, createLinkHandled, form, searchParams]);

  function closeCreateDrawer() {
    setDrawerOpen(false);
    setResumeFile(null);
    setResumeParse(null);
    form.resetFields();
  }

  async function attachResume(candidateId: number) {
    if (!resumeFile) return;
    try {
      const uploaded = await uploadResume(resumeFile, candidateId);
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
    setResumeFile(file);
    setResumeParse(null);
    setResumeParsing(true);
    try {
      const result = await parseResumeUpload(file);
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
      msg.error('简历解析失败，请确认文件为可读取的 PDF 或 DOCX');
    } finally {
      setResumeParsing(false);
    }
  }

  async function handleCreate() {
    const values = await form.validateFields();
    const { job_id: selectedJobId, ...candidateValues } = values;
    const payload = {
      ...candidateValues,
      gender: values.gender || resumeParse?.fields.gender || '',
      age: values.age ?? resumeParse?.fields.age ?? null,
      highest_education: values.highest_education || resumeParse?.fields.highest_education || '',
      major: values.major || resumeParse?.fields.major || '',
      education: values.education?.length ? values.education : resumeParse?.fields.education ?? [],
      work_experience: values.work_experience?.length ? values.work_experience : resumeParse?.fields.work_experience ?? [],
    };
    const result = await saveCandidate(null, payload);
    if (result.duplicated && result.duplicates?.length) {
      Modal.confirm({
        title: '查重提示：候选人已存在',
        content: `匹配到：${result.duplicates.map((d) => `${d.name}（${d.phone}）`).join('、')}。同一候选人不能重复建档，请使用已有候选人。`,
        okText: '使用已有',
        cancelText: '取消',
        onOk: async () => {
          const existing = result.duplicates![0];
          const ownerId = existing.lock?.owner_id || existing.owner_id;
          if (ownerId && ownerId !== user?.user_id) {
            msg.error(`该候选人正在由 ${existing.lock?.owner_name || existing.owner_name || '其他 HR'} 处理，当前不能进入或操作`);
            return;
          }
          if (selectedJobId) await assignJob(existing.id, Number(selectedJobId));
          closeCreateDrawer();
          navigate(`/candidates/${existing.id}`);
        },
      });
      return;
    }
    if (result.candidate?.id) {
      if (selectedJobId) await assignJob(result.candidate.id, Number(selectedJobId));
      await attachResume(result.candidate.id);
    }
    msg.success('候选人已创建');
    closeCreateDrawer();
    void load();
    void loadClassification();
  }

  function openCreateDrawer() {
    form.resetFields();
    setResumeFile(null);
    setResumeParse(null);
    setDrawerOpen(true);
  }

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">候选人</h2>
        <Space>
          {canManage && <Button icon={<UploadOutlined />} onClick={() => void downloadProtectedFile('/api/candidates/import-template', 'candidate_template.csv')}>导入模板</Button>}
          {canManage && <Button onClick={() => void downloadProtectedFile('/api/candidates/export', 'candidates.csv')}>导出</Button>}
          {canManage && <Button
            disabled={!selectedIds.length}
            onClick={() => setBatchPoolOpen(true)}
          >
            批量加入人才库
          </Button>}
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
                className={filters.stage === stage.key && !filters.category ? 'is-active' : ''}
                onClick={() => setFilters((current) => ({
                  ...current, stage: stage.key, category: '', source: '', page: 1,
                }))}
              >
                <span>{stage.label}</span>
              </button>
            ))}
          </div>
          <div className="candidate-stage-actions">
            <button
              type="button"
              className="candidate-unassigned"
              onClick={() => setFilters((current) => ({
                ...current, stage: 'pending_screen', category: '', source: '', page: 1,
              }))}
            >
              待分配 <strong>{classification?.unassigned ?? 0}</strong>
            </button>
            {canManage && (
              <Upload
                accept=".csv,.xlsx"
                showUploadList={false}
                beforeUpload={async (file) => {
                  const result = await importCandidates(file as File);
                  Modal.info({
                    title: '导入结果',
                    content: `成功 ${result.success_count} 条；查重跳过 ${result.duplicates.length} 条；失败 ${result.errors.length} 条`,
                  });
                  void load();
                  void loadClassification();
                  return false;
                }}
              >
                <Button type="primary" icon={<PlusOutlined />}>导入简历</Button>
              </Upload>
            )}
          </div>
        </div>
        <div className="candidate-stage-subtabs">
          <button
            type="button"
            className={!filters.category && filters.stage === 'pending_screen' ? 'is-active' : ''}
            onClick={() => setFilters((current) => ({
              ...current, stage: 'pending_screen', category: '', source: '', page: 1,
            }))}
          >
            未处理 <strong>{classification?.categories.unprocessed ?? 0}</strong>
          </button>
          <button
            type="button"
            className={filters.category === 'pending' ? 'is-active' : ''}
            onClick={() => setFilters((current) => ({
              ...current, stage: '', category: 'pending', source: '', page: 1,
            }))}
          >
            待定 <strong>{classification?.categories.pending ?? 0}</strong>
          </button>
          <button
            type="button"
            className={filters.category === 'recommended' ? 'is-active' : ''}
            onClick={() => setFilters((current) => ({
              ...current, stage: '', category: 'recommended', source: '', page: 1,
            }))}
          >
            人才推荐 <strong>{classification?.categories.recommended ?? 0}</strong>
          </button>
        </div>
      </section>
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
              ...current, source: value ?? '', page: 1,
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
        <Space style={{ marginBottom: 12 }} wrap>
          <Input.Search
            placeholder="姓名/手机/邮箱" allowClear style={{ width: 220 }}
            onSearch={(v) => setFilters((f) => ({ ...f, keyword: v, page: 1 }))}
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
                    onClick={() => navigate(`/candidates/${record.id}`)}
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
                      <span>{record.latest_application?.job_name || '待分配职位'}</span>
                      <span>招聘 HR：{record.owner_name || '未分配'}</span>
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
                            void loadClassification();
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
        extra={<Button type="primary" onClick={() => void handleCreate()}>保存</Button>}
      >
        <Form form={form} layout="vertical">
          <Form.Item label="简历解析">
            <Upload
              accept=".pdf,.docx" showUploadList={false}
              beforeUpload={(file) => {
                void handleResumeParse(file as File);
                return false;
              }}
            >
              <Button icon={<UploadOutlined />} loading={resumeParsing}>
                上传 PDF/DOCX 并解析
              </Button>
            </Upload>
            {resumeFile && (
              <div style={{ marginTop: 8, color: 'rgba(23,26,29,0.65)' }}>
                已选择：{resumeFile.name}
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
                  </div>
                )}
              />
            )}
          </Form.Item>
          <Form.Item name="name" label="姓名" rules={[{ required: true, message: '必填' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="job_id" label="应聘职位（可选）">
            <Select
              allowClear showSearch optionFilterProp="label"
              placeholder="选择后保存时同时创建应聘记录"
              options={jobs.map((job) => ({ value: job.id, label: job.name }))}
            />
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

      <Modal
        title={`批量加入人才库（${selectedIds.length} 人）`}
        open={batchPoolOpen}
        onCancel={() => setBatchPoolOpen(false)}
        onOk={async () => {
          const res = await addToPool({
            candidate_ids: selectedIds,
            category: batchPoolCategory || undefined,
            reason: batchPoolReason || undefined,
            source: 'manual',
          });
          msg.success(`已加入 ${res.added.length} 人，重复跳过 ${res.duplicates.length} 人`);
          setBatchPoolOpen(false);
          setSelectedIds([]);
          setBatchPoolCategory('');
          setBatchPoolReason('');
        }}
      >
        <p>分类</p>
        <Select
          style={{ width: '100%', marginBottom: 12 }} allowClear placeholder="选择分类"
          value={batchPoolCategory || undefined}
          onChange={(v) => setBatchPoolCategory(v ?? '')}
          options={[
            { value: 'tech', label: '技术类' }, { value: 'product', label: '产品类' },
            { value: 'sales', label: '销售类' }, { value: 'general', label: '综合类' },
          ]}
        />
        <p>加入原因</p>
        <Input.TextArea rows={2} value={batchPoolReason} onChange={(e) => setBatchPoolReason(e.target.value)} />
      </Modal>

    </div>
  );
}
