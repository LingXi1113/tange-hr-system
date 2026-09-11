import { DeleteOutlined, EditOutlined, LockOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import {
  Avatar, Button, Card, Checkbox, Col, Descriptions, Dropdown, Empty, Form, Input, List, Modal, Radio, Row,
  Select, Segmented, Space, Table, Tag, Timeline, Typography, Upload,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import {
  assignBusinessScreener, assignJob, directInterview, enterNextInterview, fetchCandidate, fetchDeliveryAnalysis,
  fetchTransitions, parseResume,
  saveCandidate, uploadResume,
} from '@/services/candidate';
import { fetchInterviews, INTERVIEW_STATUS_TEXT } from '@/services/interview';
import type { Interview } from '@/services/interview';
import { fetchOffers, OFFER_STATUS_COLOR, OFFER_STATUS_TEXT } from '@/services/offer';
import type { Offer } from '@/services/offer';
import type { CandidateDetail, DeliveryAnalysis } from '@/services/candidate';
import { useCurrentUser } from '@/services/user';
import { msg } from '@/utils/message';
import { createProtectedFileUrl } from '@/services/http';
import { fetchPlatformUsers } from '@/services/system';
import type { PlatformUser } from '@/services/system';
import { fetchJobs } from '@/services/job';
import type { Job } from '@/services/job';
import { abandonApplication, moveApplication, restoreApplication } from '@/services/pipeline';
import { removeFromPool } from '@/services/talentPool';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorker;

const STAGE_TEXT: Record<string, string> = {
  // PRD v1.1 默认九阶段
  new_resume: '简历初筛', pending_screen: '简历初筛', hr_screen_passed: '业务复筛',
  pending_interview: '待面试', interviewing: '面试中', interview_passed: '面试阶段',
  offer_pending: '录用通知', pending_onboard: '待入职', onboarded: '已入职',
  // 终态
  eliminated: '淘汰', abandoned: '放弃', talent_pool: '人才库',
  // v1.0 旧阶段（兼容历史数据）
  business_screen: '业务复筛', interview_1: '一面', interview_2: '二面',
  interview_3: '三面', hrbp_interview: 'HRBP确认', hr_interview: '人力面', offer_approval: '最终筛选', offer: '录用通知',
  // 可选环节
  written_test: '笔试', assessment: '测评', background_check: '背调',
  re_interview: '复试', custom: '自定义',
};

function stageText(stage: string | undefined) {
  const labels: Record<string, string> = {
    ...STAGE_TEXT,
    hr_screen_passed: '业务复筛',
    offer_pending: '录用通知',
    offer: '录用通知',
    hr_interview: '人力面',
  };
  return labels[stage ?? ''] ?? '其他阶段';
}

const OPERATION_ACTION_TEXT: Record<string, string> = {
  create: '新建记录',
  update: '更新信息',
  upload: '上传文件',
  delete: '删除记录',
  assign_business_screener: '推荐业务复筛',
  recommend_business_screener: '推荐业务复筛',
  direct_interview: '直接进入面试',
  enter_second_interview: '进入二面',
  advance_interview_round: '推进下一轮面试',
  reschedule: '面试改期',
  feedback: '提交面试评价',
  complete: '完成面试',
  apply_conclusion_pass: '应用通过结论',
  apply_conclusion_fail: '应用未通过结论',
  eliminate: '淘汰候选人',
  abandon: '放弃候选人',
  status_reconcile: '修正流程状态',
  add: '加入人才库',
  add_auto: '自动加入人才库',
  activate: '激活人才库记录',
  remove: '移出人才库',
};

function operationActionText(action: string, kind: string) {
  if (kind === 'resume') return action;
  const moveMatch = action.match(/^move_(.+)_to_(.+)$/);
  if (moveMatch) {
    return `从${stageText(moveMatch[1])}推进到${stageText(moveMatch[2])}`;
  }
  return OPERATION_ACTION_TEXT[action] || '更新招聘流程';
}

const DEFAULT_STAGE_FLOW = [
  { key: 'pending_screen', label: '简历初筛' },
  { key: 'business_screen', label: '业务复筛' },
  { key: 'interview_1', label: '一面（业务）' },
  { key: 'interview_2', label: '二面（业务）' },
  { key: 'interview_3', label: '三面' },
  { key: 'hrbp_interview', label: 'HRBP确认' },
  { key: 'offer_approval', label: '最终筛选' },
] as const;

const DEFAULT_STAGE_ALIASES: Record<string, string> = {
  new_resume: 'pending_screen',
  hr_screen_passed: 'business_screen',
  pending_interview: 'interview_1',
  interviewing: 'interview_1',
  interview_passed: 'interview_1',
  offer_pending: 'offer_approval',
  pending_onboard: 'offer_approval',
  onboarded: 'offer_approval',
};

const INTERVIEW_STAGE_KEYS = new Set([
  'pending_interview', 'interviewing',
  'interview_1', 'interview_2', 'interview_3', 'hr_interview', 're_interview',
]);

const INTERVIEW_STAGE_ROUNDS: Record<string, string> = {
  interview_1: '一面', interview_2: '二面', interview_3: '三面',
  hr_interview: 'HR面试', re_interview: '复试',
};

type StageTransition = {
  from_stage: string;
  to_stage: string;
  reason: string;
  operator_name: string;
  created_at: string;
};

function stageFlowIndex(stageKey: string) {
  const normalized = DEFAULT_STAGE_ALIASES[stageKey] || stageKey;
  return DEFAULT_STAGE_FLOW.findIndex((stage) => stage.key === normalized);
}

function StageProgress({ currentStage, interviewRound, transitions }: {
  currentStage: string;
  interviewRound?: string;
  transitions: StageTransition[];
}) {
  const visibleInterviewStage = ['二面', '三面', 'HR面试', '终面'].includes(interviewRound ?? '')
    ? ({ 二面: 'interview_2', 三面: 'interview_3', HR面试: 'interview_3', 终面: 'interview_3' } as Record<string, string>)[interviewRound ?? '']
    : '';
  const visibleStage = visibleInterviewStage && ['interviewing', 'interview_passed'].includes(currentStage)
    ? visibleInterviewStage
    : currentStage;
  // 阶段条以当前阶段为准。历史流转只用于旧数据没有可识别当前阶段时的兜底，
  // 不能用历史最高阶段覆盖“恢复到简历初筛”等回退后的当前状态。
  const directIndex = stageFlowIndex(visibleStage);
  const historyIndexes = transitions
    .flatMap((item) => [item.from_stage, item.to_stage])
    .map(stageFlowIndex)
    .filter((index) => index >= 0);
  const isTerminated = ['abandoned', 'eliminated', 'talent_pool'].includes(currentStage);
  const currentIndex = isTerminated
    ? -1
    : directIndex >= 0
      ? directIndex
      : (historyIndexes.length ? Math.max(...historyIndexes) : -1);

  return (
    <div style={{ overflowX: 'auto', padding: '18px 8px 6px' }}>
      <div style={{ display: 'flex', minWidth: 680, alignItems: 'flex-start' }}>
        {DEFAULT_STAGE_FLOW.map((stage, index) => {
          const completed = index < currentIndex;
          const active = index === currentIndex;
          const leftDone = index > 0 && index <= currentIndex;
          const rightDone = index < currentIndex;
          return (
            <div key={stage.key} style={{ flex: 1, minWidth: 90, textAlign: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', height: 18 }}>
                {index > 0 && (
                  <div style={{ flex: 1, height: leftDone ? 4 : 1, background: leftDone ? '#d99b1d' : '#d9d9d9' }} />
                )}
                <div
                  title={active ? '\u5F53\u524D\u9636\u6BB5' : completed ? '\u5DF2\u5B8C\u6210' : '\u672A\u5F00\u59CB'}
                  style={{
                    width: active ? 16 : 14,
                    height: active ? 16 : 14,
                    borderRadius: '50%',
                    flex: '0 0 auto',
                    background: completed || active ? '#d99b1d' : '#fff',
                    border: `${active ? 3 : 2}px solid ${completed || active ? '#d99b1d' : '#c9c9c9'}`,
                    boxSizing: 'border-box',
                  }}
                />
                {index < DEFAULT_STAGE_FLOW.length - 1 && (
                  <div style={{ flex: 1, height: rightDone ? 4 : 1, background: rightDone ? '#d99b1d' : '#d9d9d9' }} />
                )}
              </div>
              <div style={{ marginTop: 9, color: active || completed ? '#262626' : '#9a9a9a', fontWeight: active ? 600 : 400, whiteSpace: 'nowrap' }}>
                {stage.label}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PdfImagePreview({ url }: { url: string }) {
  const [pages, setPages] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    const loadingTask = pdfjsLib.getDocument(url);
    setPages([]);
    setLoading(true);
    setFailed(false);

    loadingTask.promise.then(async (pdf) => {
      const renderedPages: string[] = [];
      for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
        const page = await pdf.getPage(pageNumber);
        const viewport = page.getViewport({ scale: 1.6 });
        const canvas = document.createElement('canvas');
        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);
        await page.render({
          canvasContext: canvas.getContext('2d')!,
          viewport,
        }).promise;
        renderedPages.push(canvas.toDataURL('image/png'));
      }
      await pdf.destroy();
      if (active) {
        setPages(renderedPages);
        setLoading(false);
      }
    }).catch(() => {
      if (active) {
        setFailed(true);
        setLoading(false);
      }
    });

    return () => {
      active = false;
      void loadingTask.destroy();
    };
  }, [url]);

  if (loading) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="正在生成简历图片" />;
  if (failed || !pages.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="简历图片生成失败" />;

  return (
    <div style={{ background: '#f5f5f5', padding: 12 }}>
      {pages.map((page, index) => (
        <img
          key={`${url}-${index + 1}`}
          src={page}
          alt={`简历第${index + 1}页`}
          style={{ display: 'block', width: '100%', maxWidth: 900, margin: '0 auto 12px', background: '#fff', boxShadow: '0 1px 4px rgba(0,0,0,.12)' }}
        />
      ))}
    </div>
  );
}

type ResumeFormValues = {
  version: number;
  name: string;
  gender: string;
  phone: string;
  email: string;
  city: string;
  tags: string;
  remark: string;
  education: CandidateDetail['education'];
  work_experience: CandidateDetail['work_experience'];
};

export function CandidateDetailPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const [detail, setDetail] = useState<CandidateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedAppId, setSelectedAppId] = useState<number | null>(null);
  const [transitions, setTransitions] = useState<StageTransition[]>([]);
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [businessUsers, setBusinessUsers] = useState<PlatformUser[]>([]);
  const [businessScreenerId, setBusinessScreenerId] = useState('');
  const [businessJobId, setBusinessJobId] = useState<number | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [businessAssignOpen, setBusinessAssignOpen] = useState(false);
  const [businessAssignSaving, setBusinessAssignSaving] = useState(false);
  const [offerJobOpen, setOfferJobOpen] = useState(false);
  const [offerJobId, setOfferJobId] = useState<number | null>(null);
  const [offerJobSaving, setOfferJobSaving] = useState(false);
  const [resumeEditOpen, setResumeEditOpen] = useState(false);
  const [deliveryAnalysisOpen, setDeliveryAnalysisOpen] = useState(false);
  const [deliveryAnalysisLoading, setDeliveryAnalysisLoading] = useState(false);
  const [deliveryAnalysis, setDeliveryAnalysis] = useState<DeliveryAnalysis | null>(null);
  const [screeningCategory, setScreeningCategory] = useState<'all' | 'recommendation' | 'interview' | 'offer'>('all');
  const [abandonOpen, setAbandonOpen] = useState(false);
  const [abandonReason, setAbandonReason] = useState('面试未通过');
  const [abandonToPool, setAbandonToPool] = useState(false);
  const [abandonSaving, setAbandonSaving] = useState(false);
  const [resumePreviews, setResumePreviews] = useState<Record<number, {
    fileName: string;
    url: string;
    mimeType: string;
  }>>({});
  const [resumeForm] = Form.useForm<ResumeFormValues>();

  const load = useCallback(async () => {
    if (!id) return;
    const data = await fetchCandidate(Number(id));
    setDetail(data);
    if (data.applications.length && selectedAppId == null) {
      setSelectedAppId(data.applications[0].id);
    }
  }, [id, selectedAppId]);

  useEffect(() => {
    setLoading(true);
    load().finally(() => setLoading(false));
  }, [load]);

  useEffect(() => {
    if (selectedAppId) {
      fetchTransitions(selectedAppId).then(setTransitions);
    }
  }, [selectedAppId]);

  useEffect(() => {
    // 面试不通过后应聘记录会进入人才库/终止阶段，但历史面试仍需保留展示。
    if (selectedAppId) {
      let active = true;
      setInterviews([]);
      fetchInterviews({ application_id: selectedAppId, page_size: 50 }).then((d) => {
        if (active) setInterviews(d.list);
      });
      return () => { active = false; };
    } else {
      setInterviews([]);
    }
  }, [detail, selectedAppId]);

  useEffect(() => {
    if (id) {
      fetchOffers({ candidate_id: Number(id), page_size: 50 }).then((d) => setOffers(d.list));
    }
  }, [id]);

  useEffect(() => {
    if (['hr', 'super_admin'].some((role) => user?.role === role || user?.roles?.includes(role))) {
      fetchPlatformUsers().then((users) => setBusinessUsers(
        users.filter((item) => item.role === 'business_screener'),
      ));
      fetchJobs({ page_size: 100 }).then((data) => setJobs(data.list));
    }
  }, [user?.role]);

  useEffect(() => {
    let active = true;
    const createdUrls: string[] = [];

    async function loadResumePreviews() {
      if (!detail?.attachments.length) {
        setResumePreviews({});
        return;
      }
      const entries = await Promise.all(detail.attachments.map(async (attachment) => {
        try {
          const preview = await createProtectedFileUrl(`/api/attachments/${attachment.id}`);
          createdUrls.push(preview.url);
          return [attachment.id, {
            fileName: attachment.file_name,
            url: preview.url,
            mimeType: preview.mimeType,
          }] as const;
        } catch {
          return null;
        }
      }));
      if (active) {
        setResumePreviews(Object.fromEntries(entries.filter((entry): entry is NonNullable<typeof entry> => entry !== null)));
      }
    }

    void loadResumePreviews();
    return () => {
      active = false;
      createdUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [detail?.attachments]);

  if (loading && !detail) return <PageLoading />;
  if (!detail) return <Empty description="候选人不存在" />;

  const lockOwnerId = detail.lock?.owner_id;
  const lockOwnerName = detail.lock?.owner_name;
  const lockedByOther = Boolean(
    detail.lock
      && user?.role === 'hr'
      && lockOwnerId
      && lockOwnerId !== user.user_id,
  );
  const canManage = !lockedByOther
    && ['hr', 'super_admin'].some((role) => user?.role === role || user?.roles?.includes(role));
  const canResume = ['hr', 'super_admin', 'business_screener', 'interviewer'].some(
    (role) => user?.role === role || user?.roles?.includes(role),
  ) && !lockedByOther;
  const candidate = detail;
  const selectedApplication = detail.applications.find((application) => application.id === selectedAppId)
    ?? detail.applications[0];
  const canScheduleInterview = Boolean(
    canManage
      && selectedApplication?.status === 'in_progress'
      && INTERVIEW_STAGE_KEYS.has(selectedApplication.current_stage),
  );
  const expectedInterviewRound = selectedApplication
    ? INTERVIEW_STAGE_ROUNDS[selectedApplication.current_stage]
      || selectedApplication.interview_round
      || (['pending_interview', 'interviewing'].includes(selectedApplication.current_stage) ? '一面' : '')
    : '';
  const currentInterview = interviews.find((interview) =>
    interview.round === expectedInterviewRound && interview.status !== 'cancelled');
  const interviewPassed = interviews.some((interview) => (
    interview.status === 'completed'
    && (interview.conclusion_action === 'pass' || interview.feedback_conclusion === 'pass')
  ));
  const canEnterSecondInterview = Boolean(
    canManage
      && selectedApplication
      && ['interview_passed', 'interviewing', 'interview_1'].includes(selectedApplication.current_stage)
      && !['二面', '三面', 'HR面试', '终面', '终面（HR）'].includes(selectedApplication.interview_round ?? ''),
  );
  const alreadyInSecondInterview = Boolean(
    selectedApplication?.current_stage === 'interviewing'
      && selectedApplication.interview_round === '二面',
  );
  const canEnterFinalInterview = Boolean(
    canManage
      && selectedApplication
      && (
        selectedApplication.current_stage === 'interview_2'
        || (selectedApplication.current_stage === 'interviewing'
          && selectedApplication.interview_round === '二面')
        || (selectedApplication.current_stage === 'interview_passed'
          && selectedApplication.interview_round === '二面')
      ),
  );
  const alreadyInFinalInterview = Boolean(
    selectedApplication?.current_stage === 'interview_3'
      || selectedApplication?.current_stage === 'hr_interview'
      || (selectedApplication?.current_stage === 'interviewing'
        && ['三面', 'HR面试', '终面'].includes(selectedApplication.interview_round ?? '')),
  );
  const alreadyInHrbpInterview = selectedApplication?.current_stage === 'hrbp_interview';
  const canSkipInterviewToOffer = Boolean(
    canManage && selectedApplication?.status === 'in_progress'
      && ![
        'offer_pending', 'offer_approval', 'offer', 'pending_onboard', 'onboarded',
        'eliminated', 'abandoned', 'talent_pool',
      ].includes(selectedApplication.current_stage),
  );
  const canEnterOfferApproval = Boolean(
    canManage && (!selectedApplication || canSkipInterviewToOffer),
  );
  const currentOffers = offers.filter((offer) => offer.application_id === selectedApplication?.id);
  const canCreateOffer = Boolean(
    canManage && interviewPassed
      && ['offer_pending', 'offer_approval'].includes(selectedApplication?.current_stage ?? '')
      && !currentOffers.some((offer) => ['draft', 'pending_send', 'sent'].includes(offer.status)),
  );
  // 流程入口对所有候选人阶段都展示，具体动作再按当前阶段和权限控制。
  const isBusinessScreener = user?.role === 'business_screener' || user?.roles?.includes('business_screener');
  const canApproveBusinessScreen = Boolean(
    isBusinessScreener
      && selectedApplication?.current_stage === 'business_screen'
      && selectedApplication.business_screener_id === user?.user_id,
  );
  const canShowFlowButton = Boolean(detail);
  const canArrangeFlow = Boolean(
    ['new_resume', 'pending_screen', 'hr_screen_passed', 'business_screen'].includes(selectedApplication?.current_stage ?? ''),
  );
  const canDirectInterview = Boolean(
    canManage && (!selectedApplication || canArrangeFlow)
      || canApproveBusinessScreen,
  );
  const canOfferFlowAction = canEnterOfferApproval;
  const canUseFlowButton = canDirectInterview || canEnterSecondInterview
    || canEnterFinalInterview || canOfferFlowAction || canCreateOffer;
  const flowPrimaryLabel = canApproveBusinessScreen
    ? '通过业务复筛'
    : canEnterFinalInterview
      ? '进入三面'
      : canEnterSecondInterview
        ? '进入二面（业务）'
        : alreadyInFinalInterview
          ? '三面进行中'
          : alreadyInSecondInterview
            ? '二面进行中'
            : alreadyInHrbpInterview
              ? '进入录用审批'
              : canDirectInterview
                ? '进入一面（业务）'
                : canCreateOffer
                  ? '创建 Offer'
                  : selectedApplication
                    ? `当前阶段：${stageText(selectedApplication.current_stage)}`
                    : '进入一面（业务）';
  const inInterviewStage = Boolean(
    selectedApplication && INTERVIEW_STAGE_KEYS.has(selectedApplication.current_stage),
  );
  const canAbandon = Boolean(
    canManage && selectedApplication
      && ['in_progress', 'pending_onboard'].includes(selectedApplication.status)
      && !['abandoned', 'eliminated', 'talent_pool', 'onboarded'].includes(selectedApplication.current_stage),
  );
  const currentApplicationStage = selectedApplication?.current_stage || detail.current_stage;
  const isInterrupted = ['abandoned', 'eliminated', 'talent_pool'].includes(currentApplicationStage);
  const hasHrPermission = ['hr', 'super_admin'].some(
    (role) => user?.role === role || user?.roles?.includes(role),
  );
  const canRestore = Boolean(isInterrupted && hasHrPermission);
  const isAbandoned = selectedApplication?.current_stage === 'abandoned'
    && selectedApplication.status === 'closed';
  const canRemoveFromPool = Boolean(canManage && isAbandoned && detail.talent_pool_entry);
  const flowActionItems = [
    ...(canManage ? [{ key: 'business', label: '推给业务复筛', disabled: !canArrangeFlow }] : []),
    { key: 'interview_1', label: '进入一面（业务）', disabled: !canDirectInterview },
    { key: 'interview_2', label: '进入二面（业务）', disabled: !canEnterSecondInterview },
    { key: 'final_interview', label: '进入三面', disabled: !canEnterFinalInterview },
    { key: 'hrbp_interview', label: 'HRBP确认', disabled: true },
    {
      key: 'offer_approval',
      label: '进入录用审批',
      disabled: !canOfferFlowAction,
    },
    { key: 'offer', label: '创建 Offer', disabled: !canCreateOffer },
    { key: 'restore', label: '恢复到流程', disabled: !canRestore },
    { key: 'pending_onboard', label: '进入待入职', disabled: true },
    { key: 'onboarded', label: '进入入职', disabled: true },
  ];

  async function handleRestore() {
    if (!selectedApplication || !canRestore) return;
    await restoreApplication(selectedApplication.id, selectedApplication.version);
    msg.success('流程已恢复到简历初筛，当前 HR 已成为负责人');
    await load();
    setTransitions(await fetchTransitions(selectedApplication.id));
  }

  async function handleRemoveFromPool() {
    const entry = detail?.talent_pool_entry;
    if (!entry || !canRemoveFromPool) return;
    await removeFromPool(entry.id);
    msg.success('已移除人才库');
    await load();
  }

  function openResumeEditor(values?: Partial<ResumeFormValues>) {
    resumeForm.setFieldsValue({
      version: candidate.version,
      name: candidate.name,
      gender: candidate.gender,
      phone: candidate.phone,
      email: candidate.email,
      city: candidate.city,
      tags: candidate.tags,
      remark: candidate.remark,
      education: candidate.education,
      work_experience: candidate.work_experience,
      ...values,
    });
    setResumeEditOpen(true);
  }

  async function saveResumeProfile() {
    const values = await resumeForm.validateFields();
    const result = await saveCandidate(candidate.id, values);
    if (result.duplicated) {
      msg.error('手机号或邮箱与其他候选人重复，请确认后再保存');
      return;
    }
    msg.success('候选人简历信息已保存');
    setResumeEditOpen(false);
    await load();
  }

  async function openDeliveryAnalysis() {
    setDeliveryAnalysisOpen(true);
    setDeliveryAnalysisLoading(true);
    try {
      setDeliveryAnalysis(await fetchDeliveryAnalysis(candidate.id));
    } finally {
      setDeliveryAnalysisLoading(false);
    }
  }

  async function handleAssignBusiness() {
    const screenerId = businessScreenerId || selectedApplication?.business_screener_id || '';
    if (!screenerId) {
      msg.error('请选择业务复筛人员');
      return;
    }
    if (!selectedApplication && !businessJobId) {
      msg.error('请先选择应聘职位');
      return;
    }
    if (selectedApplication && !canArrangeFlow) {
      msg.error(`当前阶段“${stageText(selectedApplication.current_stage)}”无法推荐给业务复筛`);
      return;
    }
    if (businessAssignSaving) return;
    setBusinessAssignSaving(true);
    try {
      const application = selectedApplication
        ?? await assignJob(Number(id), businessJobId!, 'business_recommendation');
      await assignBusinessScreener(application.id, screenerId, application.version);
      msg.success('已推送给业务复筛人员');
      setBusinessAssignOpen(false);
      setSelectedAppId(application.id);
      await load();
      setTransitions(await fetchTransitions(application.id));
    } finally {
      setBusinessAssignSaving(false);
    }
  }

  function openBusinessAssign() {
    setBusinessScreenerId(selectedApplication?.business_screener_id ?? '');
    setBusinessJobId(selectedApplication?.job_id ?? null);
    setBusinessAssignOpen(true);
  }

  async function handleDirectInterview() {
    if (!selectedApplication) {
      navigate(`/interviews?candidate_id=${id}&open=1`);
      return;
    }
    await directInterview(selectedApplication.id, selectedApplication.version);
    msg.success('已直接进入面试阶段，请安排面试');
    await load();
    setTransitions(await fetchTransitions(selectedApplication.id));
  }

  async function handleEnterSecondInterview() {
    if (!selectedApplication || !canEnterSecondInterview) {
      msg.warning('请先完成并通过一面评价');
      return;
    }
    await enterNextInterview(selectedApplication.id, selectedApplication.version);
    msg.success('已进入二面，请安排二面面试');
    await load();
    setTransitions(await fetchTransitions(selectedApplication.id));
  }

  async function handleEnterFinalInterview() {
    if (!selectedApplication || !canEnterFinalInterview) {
      if (alreadyInFinalInterview) {
        msg.info('候选人已进入三面，请点击“安排面试”');
      } else {
        msg.warning('请先完成并通过二面评价');
      }
      return;
    }
    await enterNextInterview(selectedApplication.id, selectedApplication.version);
    msg.success('已进入三面，请安排三面面试');
    await load();
    setTransitions(await fetchTransitions(selectedApplication.id));
  }

  async function handleEnterOfferApproval() {
    if (!selectedApplication || !canOfferFlowAction) {
      if (!canOfferFlowAction) {
        msg.warning('仅 HR 或超级管理员可以进入录用审批');
        return;
      }
      if (!jobs.length) {
        msg.error('暂无可用职位，请先维护职位信息');
        return;
      }
      setOfferJobId(jobs[0].id);
      setOfferJobOpen(true);
      return;
    }
    await moveApplication(selectedApplication.id, {
      to_stage: 'offer_approval',
      reason: 'HR进入录用审批',
      version: selectedApplication.version,
    });
    msg.success('已进入录用审批');
    await load();
    setTransitions(await fetchTransitions(selectedApplication.id));
  }

  async function confirmDirectOfferApproval() {
    if (!offerJobId || offerJobSaving) return;
    setOfferJobSaving(true);
    try {
      const application = await assignJob(Number(id), offerJobId, 'hr_direct_offer');
      const updated = await moveApplication(application.id, {
        to_stage: 'offer_pending',
        reason: 'HR跳过面试直接进入录用审批',
        version: application.version,
      });
      msg.success('已创建应聘记录并进入录用审批');
      setOfferJobOpen(false);
      setSelectedAppId(updated.id);
      await load();
      setTransitions(await fetchTransitions(updated.id));
    } finally {
      setOfferJobSaving(false);
    }
  }

  function handleArrangeInterview() {
    if (!selectedApplication || !canScheduleInterview) {
      msg.warning('当前阶段暂不能安排面试');
      return;
    }
    navigate(
      currentInterview
        ? `/interviews?interview_id=${currentInterview.id}&open=1`
        : `/interviews?candidate_id=${id}&application_id=${selectedApplication.id}&open=1`,
    );
  }

  async function handleAbandon() {
    if (!selectedApplication || !abandonReason || abandonSaving) return;
    setAbandonSaving(true);
    try {
      await abandonApplication(selectedApplication.id, abandonReason, selectedApplication.version, abandonToPool);
      msg.success(abandonToPool ? '候选人已放弃并加入人才库' : '候选人已放弃，流程已结束');
      setAbandonOpen(false);
      setAbandonToPool(false);
      await load();
      setTransitions(await fetchTransitions(selectedApplication.id));
    } finally {
      setAbandonSaving(false);
    }
  }

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">
          {detail.name}
          {detail.lock && (
            <Tag color="error" style={{ marginLeft: 8 }}>
              {detail.lock.stage_key === 'candidate_owner'
                ? `负责人锁定${lockOwnerName ? ` · ${lockOwnerName}` : ''}`
                : `锁定中 · ${detail.lock.start_at} ~ ${detail.lock.end_at}${lockOwnerName ? ` · 负责人：${lockOwnerName}` : ''}`}
            </Tag>
          )}
          {lockedByOther && (
            <Tag color="warning" style={{ marginLeft: 8 }}>
              当前仅可查看，不能操作
            </Tag>
          )}
        </h2>
        <Button onClick={() => navigate('/candidates')}>返回列表</Button>
      </div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row align="middle" justify="space-between" gutter={[16, 12]}>
          <Col flex="1 1 520px">
            <Space align="start" size={14}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <Avatar size={64} style={{ background: '#eef2f5', color: '#8a969f', fontSize: 28 }}>
                  {detail.name.slice(0, 1)}
                </Avatar>
                {detail.lock && (
                  <Tag color="error" icon={<LockOutlined />} style={{ margin: 0, fontSize: 12 }}>
                    已锁定
                  </Tag>
                )}
              </div>
              <div>
                <Typography.Title level={3} style={{ margin: 0 }}>{detail.name}</Typography.Title>
                <Typography.Text type="secondary">
                  {detail.gender || '未填写'}　·　{detail.city || '城市未填写'}　·　{detail.source || '来源未填写'}
                </Typography.Text>
                <div style={{ marginTop: 8 }}>
                  <Typography.Text>{detail.phone}</Typography.Text>
                  <Typography.Text type="secondary">　|　</Typography.Text>
                  <Typography.Text>{detail.email}</Typography.Text>
                  {selectedApplication?.business_screener_name && (
                    <Tag color="blue" style={{ marginLeft: 12 }}>
                      业务复筛：{selectedApplication.business_screener_name}
                    </Tag>
                  )}
                </div>
              </div>
            </Space>
          </Col>
        </Row>
      </Card>
      <Row gutter={16}>
        <Col xs={24} lg={15}>
          <Card
            title="基本信息" size="small" style={{ marginBottom: 16 }}
            extra={canManage || lockedByOther ? (
              <Button
                size="small" icon={<EditOutlined />} disabled={!canManage}
                onClick={() => openResumeEditor()}
              >
                编辑基本信息
              </Button>
            ) : null}
          >
            <Descriptions column={2} size="small">
              <Descriptions.Item label="性别">{detail.gender || '-'}</Descriptions.Item>
              <Descriptions.Item label="城市">{detail.city || '-'}</Descriptions.Item>
              <Descriptions.Item label="手机号">{detail.phone}</Descriptions.Item>
              <Descriptions.Item label="邮箱">{detail.email}</Descriptions.Item>
              <Descriptions.Item label="来源">{detail.source}</Descriptions.Item>
              <Descriptions.Item label="负责人">{detail.owner_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="教育经历" span={2}>
                {detail.education.length
                  ? detail.education.map((item) => [item.school, item.major, item.degree, item.graduate_at]
                    .filter(Boolean).join(' · ')).filter(Boolean).join('；')
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="标签" span={2}>{detail.tags || '-'}</Descriptions.Item>
              <Descriptions.Item label="备注" span={2}>{detail.remark || '-'}</Descriptions.Item>
            </Descriptions>
          </Card>
          <Card
            title="简历附件" size="small" style={{ marginBottom: 16 }}
            extra={(
              <Space>
                <Button size="small" type="primary" ghost onClick={() => void openDeliveryAnalysis()}>
                  投递分析
                </Button>
                {canResume ? (
                  <Upload
                    showUploadList={false} accept=".pdf,.docx,.doc,.jpg,.jpeg,.png"
                    beforeUpload={async (file) => {
                      const up = await uploadResume(file as File, detail.id);
                      msg.success('简历已上传');
                      const parsed = await parseResume(up.attachment_id);
                      if (parsed.parse_status === 'system') {
                        const fields = parsed.fields;
                        if (canManage) {
                          openResumeEditor({
                            name: fields.name || detail.name,
                            gender: fields.gender || detail.gender,
                            phone: fields.phone || detail.phone,
                            email: fields.email || detail.email,
                            education: fields.education?.length ? fields.education : detail.education,
                            work_experience: fields.work_experience?.length ? fields.work_experience : detail.work_experience,
                          });
                        } else {
                          Modal.info({
                            title: '解析结果',
                            content: <pre style={{ fontSize: 12 }}>{JSON.stringify(fields, null, 2)}</pre>,
                          });
                        }
                      } else {
                        msg.error(parsed.message);
                      }
                      void load();
                      return false;
                    }}
                  >
                    <Button size="small" icon={<UploadOutlined />}>上传简历</Button>
                  </Upload>
                ) : lockedByOther ? (
                  <Button size="small" icon={<UploadOutlined />} disabled>上传简历</Button>
                ) : null}
              </Space>
            )}
          >
            <List
              size="small"
              locale={{ emptyText: '暂无附件' }}
              dataSource={detail.attachments}
              renderItem={(a) => (
                <List.Item>
                  {a.file_name}
                  {a.parse_status === 'system' && <Tag color="success" style={{ marginLeft: 8 }}>系统解析</Tag>}
                  {a.parse_status === 'failed' && <Tag color="warning" style={{ marginLeft: 8 }}>解析失败·人工录入</Tag>}
                </List.Item>
              )}
            />
            {detail.attachments.map((attachment) => {
              const preview = resumePreviews[attachment.id];
              const isPdf = Boolean(preview && (
                preview.mimeType === 'application/pdf'
                || preview.fileName.toLowerCase().endsWith('.pdf')
              ));
              const isImage = Boolean(preview?.mimeType.startsWith('image/'));
              return (
                <div key={`resume-content-${attachment.id}`} style={{ marginTop: 16 }}>
                  <Typography.Title level={5} style={{ marginBottom: 8 }}>
                    简历内容
                  </Typography.Title>
                  {preview && isPdf ? (
                    <PdfImagePreview url={preview.url} />
                  ) : preview && isImage ? (
                    <div style={{ maxHeight: '900px', overflow: 'auto', textAlign: 'center', background: '#fafafa', padding: 12 }}>
                      <img src={preview.url} alt={preview.fileName} style={{ maxWidth: '100%' }} />
                    </div>
                  ) : preview ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该文件格式暂不支持直接展示" />
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="正在加载简历内容" />
                  )}
                </div>
              );
            })}
          </Card>
        </Col>
        <Col xs={24} lg={9}>
          <Card
            title="阶段流转记录" size="small" style={{ marginBottom: 16 }}
          >
            {canShowFlowButton && (
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
                <Space>
                  <Dropdown.Button
                  type="primary"
                  disabled={!canUseFlowButton && !canRestore}
                  menu={{
                    items: flowActionItems,
                    onClick: ({ key }) => {
                      if (key === 'business') openBusinessAssign();
                      if (key === 'interview_1') void handleDirectInterview();
                      if (key === 'interview_2') void handleEnterSecondInterview();
                      if (key === 'final_interview') void handleEnterFinalInterview();
                      if (key === 'offer_approval') void handleEnterOfferApproval();
                      if (key === 'restore') void handleRestore();
                      if (key === 'offer' && canCreateOffer) navigate(`/offers?new=1&candidate=${id}`);
                    },
                  }}
                  onClick={() => {
                    if (canEnterFinalInterview) {
                      void handleEnterFinalInterview();
                    } else if (canEnterSecondInterview) {
                      void handleEnterSecondInterview();
                    } else if (alreadyInFinalInterview) {
                      msg.info('候选人已进入三面，请点击“安排面试”');
                    } else if (alreadyInSecondInterview) {
                      msg.info('候选人已进入二面，请点击“安排面试”');
                    } else if (alreadyInHrbpInterview) {
                      void handleEnterOfferApproval();
                    } else if (canCreateOffer) {
                      navigate(`/offers?new=1&candidate=${id}`);
                    } else if (canRestore) {
                      void handleRestore();
                    } else {
                      void handleDirectInterview();
                    }
                  }}
                  >
                  {canRestore ? '恢复到流程' : flowPrimaryLabel}
                  </Dropdown.Button>
                  {inInterviewStage ? (
                    <Button
                      type="primary"
                      ghost
                      disabled={!canScheduleInterview}
                      onClick={handleArrangeInterview}
                    >
                      安排面试
                    </Button>
                  ) : canManage || lockedByOther ? (
                    <Button
                      type="primary"
                      ghost
                      disabled={!canManage}
                      onClick={openBusinessAssign}
                    >
                      推荐
                    </Button>
                  ) : null}
                  <Button danger ghost disabled={!canAbandon} onClick={() => setAbandonOpen(true)}>
                    放弃
                  </Button>
                  {detail.talent_pool_entry && isAbandoned && (
                    <Button danger ghost disabled={!canRemoveFromPool} onClick={() => void handleRemoveFromPool()}>
                      移除人才库
                    </Button>
                  )}
                </Space>
              </div>
            )}
            <StageProgress
              currentStage={selectedApplication?.current_stage ?? 'pending_screen'}
              interviewRound={selectedApplication?.interview_round}
              transitions={transitions}
            />
            {false && transitions.length ? (
              <Timeline
                items={transitions.map((t) => ({
                  children: `${STAGE_TEXT[t.from_stage] || t.from_stage || '进入流程'} → ${STAGE_TEXT[t.to_stage] || t.to_stage}｜${t.reason || '-'}｜${t.operator_name || '系统'} · ${t.created_at}`,
                }))}
              />
            ) : <Empty description="选择应聘记录查看流转" />}
          </Card>
          <Card
            title="面试记录（当前应聘记录）" size="small" style={{ marginBottom: 16 }}
            extra={canScheduleInterview || lockedByOther ? (
              <Button
                size="small" type="primary"
                disabled={!canScheduleInterview}
                onClick={() => navigate(
                  currentInterview
                    ? `/interviews?interview_id=${currentInterview.id}&open=1`
                    : `/interviews?candidate_id=${id}&application_id=${selectedApplication?.id}&open=1`,
                )}
              >
                {currentInterview ? '编辑面试' : '安排面试'}
              </Button>
            ) : null}
          >
            <Table
              rowKey="id" size="small" pagination={false} dataSource={interviews}
              locale={{ emptyText: '暂无面试安排' }}
              expandable={{
                expandedRowRender: (r) => (
                  <div style={{ padding: '4px 12px 8px' }}>
                    <Typography.Text strong>面试摘要</Typography.Text>
                    <div style={{ marginTop: 6, whiteSpace: 'pre-wrap' }}>
                      {r.summary?.trim() || '暂无摘要，可进入面试管理点击“编辑”填写。'}
                    </div>
                  </div>
                ),
              }}
              columns={[
                { title: '轮次', dataIndex: 'round', width: 70 },
                { title: '时间', dataIndex: 'start_at', width: 130 },
                { title: '面试官', dataIndex: 'interviewer_name', width: 80 },
                {
                  title: '面试摘要', dataIndex: 'summary', width: 220,
                  render: (v: string) => (
                    <Typography.Text ellipsis={{ tooltip: v }}>
                      {v?.trim() || '暂无摘要'}
                    </Typography.Text>
                  ),
                },
                {
                  title: '状态', dataIndex: 'status', width: 80,
                  render: (v: string, r: Interview) => (
                    <Space size={4} wrap>
                      <Tag>{INTERVIEW_STATUS_TEXT[v] ?? v}</Tag>
                      {r.feedback_conclusion === 'fail' && <Tag color="error">不通过</Tag>}
                      {r.feedback_conclusion === 'pass' && <Tag color="success">通过</Tag>}
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
          <Card
            title="Offer 记录" size="small" style={{ marginBottom: 16 }}
            extra={canManage || lockedByOther ? (
              <Button
                size="small" type="primary"
                disabled={!canManage}
                onClick={() => navigate(`/offers?new=1&candidate=${id}`)}
              >
                创建 Offer
              </Button>
            ) : null}
          >
            <Table
              rowKey="id" size="small" pagination={false} dataSource={interviewPassed ? currentOffers : []}
              locale={{ emptyText: '暂无 Offer 记录' }}
              columns={[
                { title: '职位', dataIndex: 'job_name' },
                { title: '薪资', dataIndex: 'salary', width: 90 },
                { title: '有效期', dataIndex: 'valid_until', width: 100 },
                {
                  title: '状态', dataIndex: 'status', width: 80,
                  render: (v: string) => (
                    <Tag color={OFFER_STATUS_COLOR[v]}>{OFFER_STATUS_TEXT[v] ?? v}</Tag>
                  ),
                },
              ]}
            />
          </Card>
          <Card title="筛选记录" size="small">
            <div style={{ marginBottom: 12 }}>
              <Segmented
                value={screeningCategory}
                onChange={(value) => setScreeningCategory(value as typeof screeningCategory)}
                options={[
                  { label: '全部', value: 'all' },
                  { label: '推荐相关', value: 'recommendation' },
                  { label: '面试相关', value: 'interview' },
                  { label: '录用相关', value: 'offer' },
                ]}
              />
            </div>
            <List
              size="small" locale={{ emptyText: '暂无筛选记录' }}
              dataSource={detail.screening_records
                .filter((record) => screeningCategory === 'all' || record.category === screeningCategory)
                .slice(0, 50)}
              renderItem={(l) => (
                <List.Item style={{ display: 'block', padding: '8px 0 12px' }}>
                  <div style={{
                    padding: '8px 12px', background: '#f5f6f8', borderRadius: 4,
                    display: 'flex', alignItems: 'center', gap: 8,
                  }}>
                    <Typography.Text strong>{l.operator_name || '系统'}</Typography.Text>
                    <Typography.Text>
                      {l.type === 'recommendation'
                        ? '推荐了候选人'
                        : ['interview', 'interview_reschedule'].includes(l.type)
                          ? l.title
                          : '推进了候选人'}
                    </Typography.Text>
                    <Typography.Text type="secondary" style={{ marginLeft: 'auto' }}>
                      {l.created_at}
                    </Typography.Text>
                  </div>
                  <div style={{
                    marginLeft: 16, padding: '8px 12px 2px',
                    borderLeft: '2px solid #d9dfe8',
                  }}>
                    {l.from_stage && l.to_stage && (
                      <Typography.Text strong>
                        {l.from_stage} → {l.to_stage}
                      </Typography.Text>
                    )}
                    <div style={{ marginTop: 4, color: '#667085' }}>
                      {l.detail || (l.type === 'recommendation' ? '已推荐给业务复筛人员' : '阶段已更新')}
                    </div>
                  </div>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>
      <Modal
        title={`投递分析：${detail.name}`}
        open={deliveryAnalysisOpen}
        width={1120}
        footer={null}
        destroyOnClose
        onCancel={() => setDeliveryAnalysisOpen(false)}
      >
        {deliveryAnalysisLoading ? (
          <PageLoading tip="正在加载投递分析" />
        ) : deliveryAnalysis ? (
          <>
            <Row gutter={[12, 12]} style={{ marginBottom: 18 }}>
              <Col xs={12} sm={6}>
                <Card size="small"><Typography.Title level={3} style={{ margin: 0 }}>{deliveryAnalysis.summary.total_deliveries}</Typography.Title><Typography.Text type="secondary">投递次数</Typography.Text></Card>
              </Col>
              <Col xs={12} sm={6}>
                <Card size="small"><Typography.Title level={3} style={{ margin: 0 }}>{deliveryAnalysis.summary.highest_stage}</Typography.Title><Typography.Text type="secondary">最高到达阶段</Typography.Text></Card>
              </Col>
              <Col xs={12} sm={6}>
                <Card size="small"><Typography.Title level={3} style={{ margin: 0 }}>{deliveryAnalysis.summary.passed_interviews}/{deliveryAnalysis.summary.evaluated_interviews}</Typography.Title><Typography.Text type="secondary">面试评价通过/已评价</Typography.Text></Card>
              </Col>
              <Col xs={12} sm={6}>
                <Card size="small"><Typography.Title level={3} style={{ margin: 0 }}>{deliveryAnalysis.summary.interview_pass_rate}%</Typography.Title><Typography.Text type="secondary">面试评价通过率</Typography.Text></Card>
              </Col>
            </Row>
            <Typography.Title level={5} style={{ margin: '8px 0 12px' }}>操作时间线</Typography.Title>
            <Table
              rowKey="id"
              size="small"
              pagination={false}
              scroll={{ x: 900 }}
              dataSource={deliveryAnalysis.activities}
              columns={[
                { title: '时间', dataIndex: 'created_at', width: 170 },
                { title: '类型', dataIndex: 'kind', width: 100, render: (value: string) => value === 'resume' ? '简历投递' : 'HR操作' },
                { title: '操作人', dataIndex: 'operator_name', width: 120 },
                {
                  title: '操作内容', dataIndex: 'title', width: 180,
                  render: (value: string, record) => operationActionText(value, record.kind),
                },
                { title: '详细说明', dataIndex: 'detail' },
                { title: '关联职位', dataIndex: 'job_name', width: 150, render: (value: string) => value || '-' },
              ]}
            />
          </>
        ) : <Empty description="暂无投递分析数据" />}
      </Modal>
      <Modal
        title="维护候选人简历"
        open={resumeEditOpen}
        width={820}
        onCancel={() => setResumeEditOpen(false)}
        onOk={() => void saveResumeProfile()}
        okText="保存"
        cancelText="取消"
      >
        <Form form={resumeForm} layout="vertical">
          <Form.Item name="version" hidden>
            <Input type="hidden" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="gender" label="性别">
                <Select allowClear options={[{ value: '男', label: '男' }, { value: '女', label: '女' }]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="phone" label="手机号">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="email" label="邮箱">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="city" label="城市">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="tags" label="标签（逗号分隔）">
                <Input />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="remark" label="备注">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="教育经历">
            <Form.List name="education">
              {(fields, { add, remove }) => (
                <>
                  {fields.map((field) => (
                    <Card key={field.key} size="small" style={{ marginBottom: 8 }}>
                      <Row gutter={8} align="middle">
                        <Col flex="1 1 180px">
                          <Form.Item {...field} name={[field.name, 'school']} label="学校"><Input /></Form.Item>
                        </Col>
                        <Col flex="1 1 140px">
                          <Form.Item {...field} name={[field.name, 'major']} label="专业"><Input /></Form.Item>
                        </Col>
                        <Col flex="0 1 110px">
                          <Form.Item {...field} name={[field.name, 'degree']} label="学历"><Input /></Form.Item>
                        </Col>
                        <Col flex="0 1 130px">
                          <Form.Item {...field} name={[field.name, 'graduate_at']} label="毕业时间"><Input /></Form.Item>
                        </Col>
                        <Col flex="0 0 32px">
                          <Button type="text" danger icon={<DeleteOutlined />} onClick={() => remove(field.name)} />
                        </Col>
                      </Row>
                    </Card>
                  ))}
                  <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({})}>新增教育经历</Button>
                </>
              )}
            </Form.List>
          </Form.Item>
          <Form.Item label="工作经历">
            <Form.List name="work_experience">
              {(fields, { add, remove }) => (
                <>
                  {fields.map((field) => (
                    <Card key={field.key} size="small" style={{ marginBottom: 8 }}>
                      <Row gutter={8} align="middle">
                        <Col flex="1 1 170px">
                          <Form.Item {...field} name={[field.name, 'company']} label="公司"><Input /></Form.Item>
                        </Col>
                        <Col flex="1 1 140px">
                          <Form.Item {...field} name={[field.name, 'position']} label="职位"><Input /></Form.Item>
                        </Col>
                        <Col flex="0 1 110px">
                          <Form.Item {...field} name={[field.name, 'start']} label="开始时间"><Input /></Form.Item>
                        </Col>
                        <Col flex="0 1 110px">
                          <Form.Item {...field} name={[field.name, 'end']} label="结束时间"><Input /></Form.Item>
                        </Col>
                        <Col flex="0 0 32px">
                          <Button type="text" danger icon={<DeleteOutlined />} onClick={() => remove(field.name)} />
                        </Col>
                        <Col span={24}>
                          <Form.Item {...field} name={[field.name, 'desc']} label="工作内容"><Input.TextArea rows={2} /></Form.Item>
                        </Col>
                      </Row>
                    </Card>
                  ))}
                  <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({})}>新增工作经历</Button>
                </>
              )}
            </Form.List>
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title="选择职位并进入录用审批"
        open={offerJobOpen}
        onCancel={() => setOfferJobOpen(false)}
        onOk={() => void confirmDirectOfferApproval()}
        okButtonProps={{
          disabled: !offerJobId,
          loading: offerJobSaving,
        }}
        okText="确认进入录用审批"
        cancelText="取消"
      >
        <Typography.Paragraph type="secondary">
          当前候选人还没有应聘记录。请选择职位，系统会先创建应聘记录，再直接进入录用审批。
        </Typography.Paragraph>
        <Select
          style={{ width: '100%' }}
          placeholder="请选择应聘职位"
          value={offerJobId ?? undefined}
          onChange={(value) => setOfferJobId(value ?? null)}
          options={jobs.map((job) => ({ value: job.id, label: job.name }))}
        />
      </Modal>
      <Modal
        title="选择业务复筛人员"
        open={businessAssignOpen}
        onCancel={() => setBusinessAssignOpen(false)}
        onOk={() => void handleAssignBusiness()}
        okButtonProps={{
          disabled: !(businessScreenerId || selectedApplication?.business_screener_id)
            || (!selectedApplication && !businessJobId),
          loading: businessAssignSaving,
        }}
        okText="确认推送"
        cancelText="取消"
      >
        <Typography.Paragraph type="secondary">
          推送后候选人进入“业务复筛”阶段，并由指定业务人员负责后续面试评价。
        </Typography.Paragraph>
        {!selectedApplication && (
          <Select
            style={{ width: '100%', marginBottom: 12 }}
            placeholder="请选择应聘职位"
            value={businessJobId ?? undefined}
            onChange={(value) => setBusinessJobId(value ?? null)}
            options={jobs.map((job) => ({ value: job.id, label: job.name }))}
          />
        )}
        <Select
          style={{ width: '100%' }}
          placeholder="请选择业务复筛人员"
          value={businessScreenerId || selectedApplication?.business_screener_id || undefined}
          onChange={(value) => setBusinessScreenerId(value ?? '')}
          options={businessUsers.map((item) => ({ value: item.user_id, label: `${item.name}（${item.dept_name}）` }))}
        />
      </Modal>
      <Modal
        title="放弃简历"
        open={abandonOpen}
        width={760}
        onCancel={() => setAbandonOpen(false)}
        onOk={() => void handleAbandon()}
        okText="确定"
        cancelText="取消"
        confirmLoading={abandonSaving}
        okButtonProps={{ disabled: !abandonReason }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, padding: '8px 0 20px' }}>
          <Avatar size={72}>{candidate.name?.slice(0, 1) || '候'}</Avatar>
          <div>
            <Typography.Title level={3} style={{ margin: 0 }}>{candidate.name}</Typography.Title>
            <Typography.Text type="secondary">
              {selectedApplication?.job_name || '当前应聘职位'}
              {'  ·  '}{candidate.phone || '-'} / {candidate.email || '-'}
            </Typography.Text>
          </div>
        </div>
        <Typography.Title level={5} style={{ marginBottom: 12 }}>放弃原因</Typography.Title>
        <Radio.Group
          value={abandonReason}
          onChange={(event) => setAbandonReason(event.target.value)}
          style={{ width: '100%', display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '14px 20px' }}
        >
          {[
            '面试未通过', '其他', '意向度低',
            '学历不达标', '接到其他offer', '工作地点',
            '工作时间', '综合条件不匹配', '薪酬不匹配',
            '候选人放弃', '无法联系', '职位关闭',
          ].map((reason) => <Radio key={reason} value={reason}>{reason}</Radio>)}
        </Radio.Group>
        <div style={{ marginTop: 24, paddingTop: 16, borderTop: '1px solid #f0f0f0' }}>
          <Checkbox checked={abandonToPool} onChange={(event) => setAbandonToPool(event.target.checked)}>
            把简历移到人才库
          </Checkbox>
        </div>
      </Modal>
    </div>
  );
}
