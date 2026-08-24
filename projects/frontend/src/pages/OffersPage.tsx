import { PlusOutlined, UploadOutlined } from '@ant-design/icons';
import {
  Button, Checkbox, DatePicker, Descriptions, Drawer, Form, Input, Modal, Popconfirm,
  Select, Space, Table, Tag, Upload,
} from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { fetchCandidates } from '@/services/candidate';
import { fetchJobs } from '@/services/job';
import {
  OFFER_STATUS_COLOR, OFFER_STATUS_TEXT,
  fetchOffers, offerAction, offerDownloadUrl, offerPreviewUrl, saveOffer, uploadOfferFile,
} from '@/services/offer';
import type { Offer } from '@/services/offer';
import { downloadProtectedFile, http, openProtectedFile, unwrap } from '@/services/http';
import { addToPool } from '@/services/talentPool';
import { msg } from '@/utils/message';

// 允许创建 Offer 的应聘记录阶段（与后端门禁一致）
const OFFER_ALLOWED_STAGES = ['interview_passed', 'offer_pending'];

interface AppOption {
  id: number;
  job_id: number;
  job_name: string;
  current_stage: string;
  status: string;
}

type ReasonAction = 'reject' | 'withdraw' | 'expire';

const REASON_ACTION_TEXT: Record<ReasonAction, string> = {
  reject: '拒绝', withdraw: '撤回', expire: '过期',
};

export function OffersPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [list, setList] = useState<Offer[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<{ status: string; job_id?: number; page: number }>({ status: '', page: 1 });

  const [jobs, setJobs] = useState<{ id: number; name: string }[]>([]);
  const [candidates, setCandidates] = useState<{ id: number; name: string }[]>([]);
  const [appOptions, setAppOptions] = useState<AppOption[]>([]);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const [detailTarget, setDetailTarget] = useState<Offer | null>(null);
  const [reasonTarget, setReasonTarget] = useState<{ offer: Offer; action: ReasonAction } | null>(null);
  const [reasonText, setReasonText] = useState('');
  const [reasonSaving, setReasonSaving] = useState(false);
  const [poolOnReject, setPoolOnReject] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchOffers({
        status: filters.status || undefined,
        job_id: filters.job_id || undefined,
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
    fetchJobs({ page_size: 100 }).then((d) => setJobs(d.list.map((j) => ({ id: j.id, name: j.name }))));
    fetchCandidates({ page_size: 100 }).then((d) => setCandidates(d.list.map((c) => ({ id: c.id, name: c.name }))));
  }, []);

  async function loadAppOptions(candidateId: number) {
    const resp = await http.get(`/api/candidates/${candidateId}/applications`);
    const apps = unwrap<AppOption[]>(resp);
    setAppOptions(apps.filter((a) =>
      a.status === 'in_progress' && OFFER_ALLOWED_STAGES.includes(a.current_stage)));
  }

  async function openEditor(record: Offer | null, presetCandidateId?: number) {
    setEditingId(record?.id ?? null);
    if (record) {
      await loadAppOptions(record.candidate_id);
      form.setFieldsValue({
        ...record,
        onboard_date: record.onboard_date ? dayjs(record.onboard_date) : null,
        valid_until: record.valid_until ? dayjs(record.valid_until) : null,
      });
    } else {
      form.resetFields();
      setAppOptions([]);
      if (presetCandidateId) {
        form.setFieldsValue({ candidate_id: presetCandidateId });
        await loadAppOptions(presetCandidateId);
      }
    }
    setDrawerOpen(true);
  }

  // 候选人详情入口：#/offers?candidate=<id>&new=1
  useEffect(() => {
    const candidateId = searchParams.get('candidate');
    if (searchParams.get('new') === '1' && candidateId) {
      void openEditor(null, Number(candidateId));
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSave() {
    const values = await form.validateFields();
    const payload = {
      ...values,
      onboard_date: (values.onboard_date as Dayjs).format('YYYY-MM-DD'),
      valid_until: (values.valid_until as Dayjs).format('YYYY-MM-DD'),
    };
    setSaving(true);
    try {
      await saveOffer(editingId, payload);
      msg.success(editingId ? 'Offer 草稿已更新' : 'Offer 草稿已创建');
      setDrawerOpen(false);
      void load();
    } catch {
      // 后端错误（1001/1003/1004/1006/1007 等）已由拦截器提示，避免未捕获 Promise
      void load();
    } finally {
      setSaving(false);
    }
  }

  async function doAction(offer: Offer, action: string, label: string) {
    try {
      await offerAction(offer.id, { action, version: offer.version });
      msg.success(`已${label}`);
      void load();
    } catch {
      // 后端错误码（1001/1003/1004/1006/1007 等）已由 http 拦截器统一提示；
      // 乐观锁冲突时刷新列表获取最新 version
      void load();
    }
  }

  async function submitReason() {
    if (!reasonTarget) return;
    if (!reasonText.trim()) {
      msg.error(`${REASON_ACTION_TEXT[reasonTarget.action]}必须填写原因`);
      return;
    }
    setReasonSaving(true);
    try {
      await offerAction(reasonTarget.offer.id, {
        action: reasonTarget.action,
        version: reasonTarget.offer.version,
        reason: reasonText.trim(),
      });
      msg.success(`已${REASON_ACTION_TEXT[reasonTarget.action]}`);
      if (reasonTarget.action === 'reject' && poolOnReject) {
        try {
          await addToPool({
            candidate_id: reasonTarget.offer.candidate_id,
            source: 'offer_rejected',
            reason: reasonText.trim(),
          });
          msg.success('候选人已加入人才库');
        } catch {
          /* 已在库中或失败：拦截器已提示 */
        }
      }
      setReasonTarget(null);
      setReasonText('');
      setPoolOnReject(false);
      void load();
    } catch {
      void load();
    } finally {
      setReasonSaving(false);
    }
  }

  const columns = [
    {
      title: '候选人', dataIndex: 'candidate_name', width: 100,
      render: (v: string, r: Offer) => <a onClick={() => setDetailTarget(r)}>{v}</a>,
    },
    { title: '职位', dataIndex: 'job_name', width: 140 },
    { title: '入职岗位', dataIndex: 'position', width: 130 },
    { title: '薪资', dataIndex: 'salary', width: 100 },
    { title: '入职日期', dataIndex: 'onboard_date', width: 110 },
    { title: '有效期至', dataIndex: 'valid_until', width: 110 },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => <Tag color={OFFER_STATUS_COLOR[v]}>{OFFER_STATUS_TEXT[v] ?? v}</Tag>,
    },
    {
      title: '文件', dataIndex: 'file', width: 80,
      render: (f: Offer['file']) => (f ? <Tag color="success">已上传</Tag> : <Tag>未上传</Tag>),
    },
    {
      title: '操作', width: 290, fixed: 'right' as const,
      render: (_: unknown, r: Offer) => (
        <Space size={2} wrap>
          {r.status === 'draft' && (
            <>
              <Button size="small" type="link" onClick={() => void openEditor(r)}>编辑</Button>
              <Popconfirm title="提交后进入待发送？" onConfirm={() => void doAction(r, 'submit', '提交')}>
                <Button size="small" type="link">提交</Button>
              </Popconfirm>
            </>
          )}
          {r.status === 'pending_send' && (
            <Popconfirm
              title="发送后候选人进入 Offer 中阶段？"
              onConfirm={() => void doAction(r, 'send', '发送')}
            >
              <Button size="small" type="link">发送</Button>
            </Popconfirm>
          )}
          {r.status === 'sent' && (
            <>
              <Popconfirm
                title="确认候选人已接受？候选人将进入待入职"
                onConfirm={() => void doAction(r, 'accept', '接受')}
              >
                <Button size="small" type="link">接受</Button>
              </Popconfirm>
              <Button size="small" type="link" danger
                onClick={() => { setReasonTarget({ offer: r, action: 'reject' }); setReasonText(''); }}>
                拒绝
              </Button>
              <Button size="small" type="link"
                onClick={() => { setReasonTarget({ offer: r, action: 'expire' }); setReasonText(''); }}>
                过期
              </Button>
            </>
          )}
          {(r.status === 'pending_send' || r.status === 'sent') && (
            <Button size="small" type="link" danger
              onClick={() => { setReasonTarget({ offer: r, action: 'withdraw' }); setReasonText(''); }}>
              撤回
            </Button>
          )}
          {(r.status === 'draft' || r.status === 'pending_send') && (
            <Upload
              showUploadList={false} maxCount={1}
              beforeUpload={async (file) => {
                try {
                  await uploadOfferFile(r.id, file as File);
                  msg.success('Offer 文件已上传');
                  void load();
                } catch { /* 错误已由拦截器提示 */ }
                return false;
              }}
            >
              <Button size="small" type="link" icon={<UploadOutlined />}>上传文件</Button>
            </Upload>
          )}
          {r.file && (
            <>
              <Button size="small" type="link" onClick={() => void openProtectedFile(offerPreviewUrl(r.id))}>
                预览
              </Button>
              <Button size="small" type="link" onClick={() => void downloadProtectedFile(offerDownloadUrl(r.id), `offer-${r.id}.pdf`)}>
                下载
              </Button>
            </>
          )}
          <Button size="small" type="link" onClick={() => setDetailTarget(r)}>详情</Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">Offer管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => void openEditor(null)}>
          新建 Offer
        </Button>
      </div>
      <div className="hrats-block">
        <Space style={{ marginBottom: 12 }} wrap>
          <Select
            placeholder="状态" allowClear style={{ width: 140 }}
            value={filters.status || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, status: v ?? '', page: 1 }))}
            options={Object.entries(OFFER_STATUS_TEXT).map(([value, label]) => ({ value, label }))}
          />
          <Select
            placeholder="职位" allowClear showSearch optionFilterProp="label" style={{ width: 220 }}
            value={filters.job_id}
            onChange={(v) => setFilters((f) => ({ ...f, job_id: v, page: 1 }))}
            options={jobs.map((j) => ({ value: j.id, label: j.name }))}
          />
        </Space>
        {loading ? <PageLoading /> : (
          <Table
            rowKey="id" size="middle" columns={columns} dataSource={list} scroll={{ x: 1300 }}
            pagination={{
              current: filters.page, pageSize: 10, total,
              onChange: (page) => setFilters((f) => ({ ...f, page })),
            }}
          />
        )}
      </div>

      {/* 新建/编辑草稿 */}
      <Drawer
        title={editingId ? '编辑 Offer（草稿）' : '新建 Offer'} width={600} forceRender
        open={drawerOpen} onClose={() => setDrawerOpen(false)}
        extra={<Button type="primary" loading={saving} onClick={() => void handleSave()}>保存草稿</Button>}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="candidate_id" label="候选人" rules={[{ required: true, message: '必填' }]}>
            <Select
              showSearch optionFilterProp="label" placeholder="选择候选人"
              options={candidates.map((c) => ({ value: c.id, label: c.name }))}
              onChange={(v) => {
                form.setFieldsValue({ application_id: undefined });
                void loadAppOptions(v);
              }}
            />
          </Form.Item>
          <Form.Item name="version" hidden><Input /></Form.Item>
          <Form.Item
            name="application_id" label="应聘记录（职位联动，仅面试通过/Offer中阶段可选）"
            rules={[{ required: true, message: '必填' }]}
          >
            <Select
              placeholder="先选择候选人"
              options={appOptions.map((a) => ({
                value: a.id, label: `${a.job_name} · ${a.current_stage}`,
              }))}
            />
          </Form.Item>
          <Space style={{ width: '100%' }} styles={{ item: { width: '50%' } }}>
            <Form.Item name="dept" label="入职部门" rules={[{ required: true, message: '必填' }]} style={{ width: '100%' }}>
              <Input />
            </Form.Item>
            <Form.Item name="position" label="入职岗位" rules={[{ required: true, message: '必填' }]} style={{ width: '100%' }}>
              <Input />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%' }} styles={{ item: { width: '50%' } }}>
            <Form.Item name="onboard_date" label="入职日期" rules={[{ required: true, message: '必填' }]} style={{ width: '100%' }}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="valid_until" label="Offer 有效期" rules={[{ required: true, message: '必填' }]} style={{ width: '100%' }}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%' }} styles={{ item: { width: '50%' } }}>
            <Form.Item name="salary" label="薪资" rules={[{ required: true, message: '必填' }]} style={{ width: '100%' }}>
              <Input placeholder="例如：30k-45k" />
            </Form.Item>
            <Form.Item name="location" label="工作地点" style={{ width: '100%' }}>
              <Input />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%' }} styles={{ item: { width: '50%' } }}>
            <Form.Item name="probation" label="试用期" style={{ width: '100%' }}>
              <Input placeholder="例如：3个月" />
            </Form.Item>
            <Form.Item name="contract_term" label="合同期限" style={{ width: '100%' }}>
              <Input placeholder="例如：3年" />
            </Form.Item>
          </Space>
          <Form.Item name="benefits" label="福利">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Drawer>

      {/* 详情抽屉 */}
      <Drawer
        title={`Offer 详情：${detailTarget?.candidate_name ?? ''}`} width={560}
        open={!!detailTarget} onClose={() => setDetailTarget(null)}
      >
        {detailTarget && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="状态">
              <Tag color={OFFER_STATUS_COLOR[detailTarget.status]}>
                {OFFER_STATUS_TEXT[detailTarget.status]}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="职位">{detailTarget.job_name}</Descriptions.Item>
            <Descriptions.Item label="入职部门">{detailTarget.dept || '-'}</Descriptions.Item>
            <Descriptions.Item label="入职岗位">{detailTarget.position || '-'}</Descriptions.Item>
            <Descriptions.Item label="入职日期">{detailTarget.onboard_date || '-'}</Descriptions.Item>
            <Descriptions.Item label="工作地点">{detailTarget.location || '-'}</Descriptions.Item>
            <Descriptions.Item label="薪资">{detailTarget.salary || '-'}</Descriptions.Item>
            <Descriptions.Item label="试用期">{detailTarget.probation || '-'}</Descriptions.Item>
            <Descriptions.Item label="合同期限">{detailTarget.contract_term || '-'}</Descriptions.Item>
            <Descriptions.Item label="福利">{detailTarget.benefits || '-'}</Descriptions.Item>
            <Descriptions.Item label="有效期至">{detailTarget.valid_until || '-'}</Descriptions.Item>
            <Descriptions.Item label="备注">{detailTarget.remark || '-'}</Descriptions.Item>
            <Descriptions.Item label="发送时间">{detailTarget.sent_at || '-'}</Descriptions.Item>
            <Descriptions.Item label="响应时间">{detailTarget.responded_at || '-'}</Descriptions.Item>
            <Descriptions.Item label="原因">{detailTarget.response_reason || '-'}</Descriptions.Item>
            <Descriptions.Item label="Offer 文件">
              {detailTarget.file ? (
                <Space>
                  {detailTarget.file.originalName}
                  <Button size="small" type="link" onClick={() => void openProtectedFile(offerPreviewUrl(detailTarget.id))}>预览</Button>
                  <Button size="small" type="link" onClick={() => void downloadProtectedFile(offerDownloadUrl(detailTarget.id), `offer-${detailTarget.id}.pdf`)}>下载</Button>
                </Space>
              ) : '未上传'}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>

      {/* 拒绝/撤回/过期 原因弹窗 */}
      <Modal
        title={reasonTarget
          ? `${REASON_ACTION_TEXT[reasonTarget.action]} Offer：${reasonTarget.offer.candidate_name}`
          : ''}
        open={!!reasonTarget}
        onCancel={() => setReasonTarget(null)}
        onOk={() => void submitReason()}
        okText="确认" okButtonProps={{ danger: reasonTarget?.action !== 'expire', loading: reasonSaving }}
      >
        <p style={{ color: 'rgba(23,26,29,0.6)' }}>
          原因将记录到操作日志，且不可撤销，请谨慎操作。
        </p>
        <Input.TextArea
          rows={3} placeholder="必填原因"
          value={reasonText} onChange={(e) => setReasonText(e.target.value)}
        />
        {reasonTarget?.action === 'reject' && (
          <Checkbox
            style={{ marginTop: 8 }}
            checked={poolOnReject}
            onChange={(e) => setPoolOnReject(e.target.checked)}
          >
            同时将候选人加入人才库
          </Checkbox>
        )}
      </Modal>
    </div>
  );
}
