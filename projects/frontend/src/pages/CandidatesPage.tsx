import { LockOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import {
  Alert, Button, Drawer, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Tooltip, Upload,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import {
  deleteCandidate, fetchCandidates, importCandidates, parseResume, parseResumeUpload, saveCandidate,
  uploadResume,
} from '@/services/candidate';
import type { CandidateRow } from '@/services/candidate';
import { fetchJobs } from '@/services/job';
import { assignJob } from '@/services/candidate';
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
  new_resume: '待筛选', pending_screen: '待筛选', hr_screen_passed: '人力筛选',
  business_screen: '业务筛选', pending_interview: '待面试', interviewing: '面试中',
  interview_1: '一面', interview_2: '二面', interview_3: '三面', hr_interview: '人力面',
  interview_passed: '面试通过', offer_approval: '最终筛选', offer_pending: '录用通知', offer: '录用通知',
  pending_onboard: '待入职', onboarded: '已入职', eliminated: '已淘汰', abandoned: '已放弃',
  talent_pool: '人才库', written_test: '笔试', assessment: '测评', background_check: '背调',
  re_interview: '复试', custom: '自定义阶段',
};

function stageText(stage: string | undefined) {
  return STAGE_TEXT[stage ?? ''] ?? '其他阶段';
}

export function CandidatesPage() {
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const canManage = user?.role === 'hr';
  const [list, setList] = useState<CandidateRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ keyword: '', stage: '', locked: '', page: 1 });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [form] = Form.useForm();
  const [jobs, setJobs] = useState<{ id: number; name: string }[]>([]);
  const [assignTarget, setAssignTarget] = useState<CandidateRow | null>(null);
  const [assignJobId, setAssignJobId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [batchPoolOpen, setBatchPoolOpen] = useState(false);
  const [batchPoolCategory, setBatchPoolCategory] = useState('');
  const [batchPoolReason, setBatchPoolReason] = useState('');
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeParsing, setResumeParsing] = useState(false);
  const [resumeParse, setResumeParse] = useState<Awaited<ReturnType<typeof parseResumeUpload>> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchCandidates({
        keyword: filters.keyword || undefined,
        stage: filters.stage || undefined,
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
    const payload = {
      ...values,
      gender: values.gender || resumeParse?.fields.gender || '',
      education: values.education?.length ? values.education : resumeParse?.fields.education ?? [],
      work_experience: values.work_experience?.length ? values.work_experience : resumeParse?.fields.work_experience ?? [],
    };
    const result = await saveCandidate(null, payload);
    if (result.duplicated && result.duplicates?.length) {
      Modal.confirm({
        title: '查重提示：已存在相似候选人',
        content: `匹配到：${result.duplicates.map((d) => `${d.name}（${d.phone}）`).join('、')}。继续使用已有候选人，或强制新建？`,
        okText: '使用已有',
        cancelText: '强制新建',
        onOk: () => {
          closeCreateDrawer();
          navigate(`/candidates/${result.duplicates![0].id}`);
        },
        onCancel: async () => {
          const forced = await saveCandidate(null, { ...payload, force: 1 });
          if (forced.candidate?.id) await attachResume(forced.candidate.id);
          msg.success('已新建候选人');
          closeCreateDrawer();
          void load();
        },
      });
      return;
    }
    if (result.candidate?.id) await attachResume(result.candidate.id);
    msg.success('候选人已创建');
    closeCreateDrawer();
    void load();
  }

  const columns = [
    {
      title: '\u9636\u6BB5', dataIndex: 'current_stage', width: 100,
      render: (v: string) => stageText(v),
    },
    { title: '姓名', dataIndex: 'name', render: (v: string, r: CandidateRow) => <a onClick={() => navigate(`/candidates/${r.id}`)}>{v}</a> },
    { title: '手机号', dataIndex: 'phone', width: 130 },
    { title: '邮箱', dataIndex: 'email', width: 180 },
    { title: '城市', dataIndex: 'city', width: 90 },
    { title: '来源', dataIndex: 'source', width: 100, render: (v: string) => SOURCE_TEXT[v] ?? v },
    {
      title: '最近应聘', dataIndex: 'latest_application', width: 200,
      render: (v: CandidateRow['latest_application']) =>
        v ? `${v.job_name} · ${stageText(v.current_stage)}` : '-',
    },
    {
      title: '锁定', dataIndex: 'lock', width: 80,
      render: (v: CandidateRow['lock']) =>
        v ? (
          <Tooltip title={`锁定中：${v.start_at} ~ ${v.end_at}`}>
            <Tag icon={<LockOutlined />} color="error">锁定</Tag>
          </Tooltip>
        ) : '-',
    },
    {
      title: '操作', width: 180, fixed: 'right' as const,
      render: (_: unknown, record: CandidateRow) => (
        <Space size={4}>
          {canManage && <Button
            size="small" type="link"
            onClick={async () => {
              if (!jobs.length) {
                setJobs((await fetchJobs({ status: 'recruiting', page_size: 100 })).list.map((j) => ({ id: j.id, name: j.name })));
              }
              setAssignJobId(null);
              setAssignTarget(record);
            }}
          >分配职位</Button>}
          {canManage && <Popconfirm
            title="删除候选人？将彻底删除其资料、附件及全部招聘关联数据"
            onConfirm={async () => {
              await deleteCandidate(record.id);
              msg.success('候选人及关联数据已彻底删除');
              void load();
            }}
          ><Button size="small" type="link" danger>删除</Button></Popconfirm>}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">候选人</h2>
        <Space>
          {canManage && <Button icon={<UploadOutlined />} onClick={() => void downloadProtectedFile('/api/candidates/import-template', 'candidate_template.csv')}>导入模板</Button>}
          {canManage && <Upload
            accept=".csv,.xlsx" showUploadList={false}
            beforeUpload={async (file) => {
              const result = await importCandidates(file as File);
              Modal.info({
                title: '导入结果',
                content: `成功 ${result.success_count} 条；查重跳过 ${result.duplicates.length} 条；失败 ${result.errors.length} 条`,
              });
              void load();
              return false;
            }}
          >
            <Button icon={<UploadOutlined />}>批量导入</Button>
          </Upload>}
          {canManage && <Button onClick={() => void downloadProtectedFile('/api/candidates/export', 'candidates.csv')}>导出</Button>}
          {canManage && <Button
            disabled={!selectedIds.length}
            onClick={() => setBatchPoolOpen(true)}
          >
            批量加入人才库
          </Button>}
          {canManage && <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setResumeFile(null); setResumeParse(null); setDrawerOpen(true); }}>
            新增候选人
          </Button>}
        </Space>
      </div>
      <div className="hrats-block">
        <Space style={{ marginBottom: 12 }} wrap>
          <Input.Search
            placeholder="姓名/手机/邮箱" allowClear style={{ width: 220 }}
            onSearch={(v) => setFilters((f) => ({ ...f, keyword: v, page: 1 }))}
          />
          <Select
            placeholder="当前阶段" allowClear style={{ width: 150 }}
            value={filters.stage || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, stage: v ?? '', page: 1 }))}
            options={[
              { value: 'new_resume', label: '新简历' }, { value: 'pending_screen', label: '待筛选' },
              { value: 'hr_screen_passed', label: '人力筛选' }, { value: 'pending_interview', label: '待面试' },
              { value: 'interviewing', label: '面试中' }, { value: 'interview_passed', label: '面试通过' },
              { value: 'offer_pending', label: '录用通知' }, { value: 'pending_onboard', label: '待入职' },
              { value: 'onboarded', label: '已入职' },
              { value: 'business_screen', label: '业务复筛(旧)' }, { value: 'interview_1', label: '一面(旧)' },
              { value: 'offer_approval', label: '录用审批(旧)' },
            ]}
          />
          <Select
            placeholder="锁定状态" allowClear style={{ width: 130 }}
            value={filters.locked || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, locked: v ?? '', page: 1 }))}
            options={[{ value: '1', label: '锁定中' }]}
          />
        </Space>
        {loading ? <PageLoading /> : (
          <Table
            rowKey="id" size="middle" columns={columns} dataSource={list} scroll={{ x: 1100 }}
            rowSelection={{
              selectedRowKeys: selectedIds,
              onChange: (keys) => setSelectedIds(keys.map(Number)),
            }}
            pagination={{
              current: filters.page, pageSize: 10, total,
              onChange: (page) => setFilters((f) => ({ ...f, page })),
            }}
          />
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
          <Form.Item name="gender" label="性别">
            <Select allowClear options={[{ value: '男', label: '男' }, { value: '女', label: '女' }]} />
          </Form.Item>
          <Form.Item name="phone" label="手机号">
            <Input />
          </Form.Item>
          <Form.Item name="email" label="邮箱">
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

      <Modal
        title={`为 ${assignTarget?.name ?? ''} 分配职位`}
        open={!!assignTarget}
        onCancel={() => setAssignTarget(null)}
        onOk={async () => {
          if (!assignTarget || !assignJobId) {
            msg.error('请选择职位');
            return;
          }
          await assignJob(assignTarget.id, assignJobId);
          msg.success('已创建应聘记录');
          setAssignTarget(null);
          void load();
        }}
      >
        <Select
          style={{ width: '100%' }} placeholder="选择招聘中的职位" showSearch optionFilterProp="label"
          value={assignJobId ?? undefined}
          onChange={(v) => setAssignJobId(v)}
          options={jobs.map((j) => ({ value: j.id, label: j.name }))}
        />
        <p style={{ marginTop: 8, color: 'rgba(23,26,29,0.6)' }}>
          锁定期内的候选人将被限制分配其他职位。
        </p>
      </Modal>
    </div>
  );
}
