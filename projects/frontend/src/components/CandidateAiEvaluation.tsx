import {
  CheckCircleFilled, ExclamationCircleFilled, QuestionCircleFilled, ReloadOutlined, RobotOutlined,
} from '@ant-design/icons';
import { Button, Empty, List, Modal, Progress, Rate, Space, Tag, Typography } from 'antd';
import { useState } from 'react';

import type { ScreeningDimension, ScreeningResult } from '@/services/screening';

interface CandidateAiEvaluationProps {
  jobName?: string;
  result: ScreeningResult | null;
  loading?: boolean;
  canEvaluate?: boolean;
  onEvaluate?: () => Promise<void>;
  onChooseJob?: () => void;
}

interface RequirementItem {
  key: string;
  label: string;
  status: 'matched' | 'partial' | 'missing';
  evidence: string;
}

const STATUS_VIEW = {
  matched: { text: '符合', color: 'success', icon: <CheckCircleFilled style={{ color: '#22a06b' }} /> },
  partial: { text: '部分符合', color: 'warning', icon: <ExclamationCircleFilled style={{ color: '#d99b1d' }} /> },
  missing: { text: '待确认', color: 'default', icon: <QuestionCircleFilled style={{ color: '#98a2b3' }} /> },
} as const;

function includesTerm(values: string[], term: string) {
  const normalized = term.trim().toLowerCase();
  return values.some((value) => {
    const current = value.toLowerCase();
    return current.includes(normalized) || normalized.includes(current);
  });
}

function findDimension(result: ScreeningResult, evaluator: string) {
  return result.dimensions.find((item) => item.evaluator === evaluator);
}

function dimensionEvidence(dimension: ScreeningDimension | undefined, fallback: string) {
  return dimension?.evidence.find(Boolean) || fallback;
}

function termRequirement(result: ScreeningResult, term: string, kind: string): RequirementItem {
  const dimension = result.dimensions.find((item) => (
    includesTerm(item.matched || [], term)
    || includesTerm(item.missing || [], term)
    || item.evidence.some((evidence) => evidence.toLowerCase().includes(term.toLowerCase()))
  ));
  const matched = includesTerm(result.matched_items, term)
    || Boolean(dimension && includesTerm(dimension.matched || [], term));
  const missing = result.missing_items.some((item) => item.toLowerCase().includes(term.toLowerCase()))
    || Boolean(dimension && includesTerm(dimension.missing || [], term));
  return {
    key: `${kind}-${term}`,
    label: term,
    status: matched ? 'matched' : missing ? 'missing' : 'partial',
    evidence: dimension?.evidence.find((item) => item.toLowerCase().includes(term.toLowerCase()))
      || (matched ? `简历中已识别到“${term}”相关经历。` : `当前结构化简历中尚未找到“${term}”的明确证据。`),
  };
}

function buildRequirements(result: ScreeningResult): RequirementItem[] {
  const items: RequirementItem[] = [];
  const education = findDimension(result, 'education');
  const experience = findDimension(result, 'experience');
  if (result.rules.min_education) {
    items.push({
      key: 'education',
      label: `${result.rules.min_education}及以上学历`,
      status: education?.status === 'matched' ? 'matched' : education?.status === 'partial' ? 'partial' : 'missing',
      evidence: dimensionEvidence(education, '当前简历未识别到可核验的学历信息。'),
    });
  }
  if (result.rules.min_work_years > 0) {
    items.push({
      key: 'experience',
      label: `相关工作经验不少于 ${result.rules.min_work_years} 年`,
      status: experience?.status === 'matched' ? 'matched' : experience?.status === 'partial' ? 'partial' : 'missing',
      evidence: dimensionEvidence(experience, '当前简历未识别到完整的工作时间。'),
    });
  }
  [...new Set([...(result.rules.hard_skills || []), ...(result.rules.required_skills || [])])]
    .forEach((term) => items.push(termRequirement(result, term, 'skill')));
  if (!items.length) {
    result.dimensions
      .filter((item) => item.status !== 'not_configured')
      .slice(0, 6)
      .forEach((dimension) => items.push({
        key: `dimension-${dimension.name}`,
        label: dimension.name,
        status: dimension.status === 'matched' ? 'matched' : dimension.status === 'partial' ? 'partial' : 'missing',
        evidence: dimensionEvidence(dimension, '当前简历证据不足，建议人工核实。'),
      }));
  }
  return items;
}

function decisionColor(result: ScreeningResult) {
  if (result.decision === 'pass') return 'success';
  if (result.decision === 'reject') return 'error';
  return 'warning';
}

function decisionText(result: ScreeningResult) {
  if (result.decision === 'pass') return '符合';
  if (result.decision === 'reject') return '不符合';
  if (result.decision === 'pending') return '待确认';
  return '信息不足';
}

export function CandidateAiEvaluation({
  jobName, result, loading = false, canEvaluate = false, onEvaluate, onChooseJob,
}: CandidateAiEvaluationProps) {
  const [open, setOpen] = useState(false);
  const requirements = result ? buildRequirements(result) : [];
  const starScore = result ? Math.round(result.score / 2) / 10 : 0;

  function openEvaluation() {
    setOpen(true);
    if (!result && jobName && canEvaluate && onEvaluate && !loading) {
      void onEvaluate();
    }
  }

  return (
    <>
      <Button
        size="small"
        onClick={openEvaluation}
        loading={loading}
        style={{
          height: 32, paddingInline: 10, borderColor: result ? '#b7ebc6' : '#d9d9d9',
          background: result ? '#f6ffed' : '#fafafa',
        }}
      >
        <Space size={5}>
          <RobotOutlined style={{ color: '#7c3aed' }} />
          <Typography.Text strong>AI评估</Typography.Text>
          {result ? (
            <>
              <Tag color={decisionColor(result)} style={{ marginInlineEnd: 0 }}>{decisionText(result)}</Tag>
              <Typography.Text>{starScore}分</Typography.Text>
            </>
          ) : (
            <Tag style={{ marginInlineEnd: 0 }}>{jobName ? '待评估' : '未分配职位'}</Tag>
          )}
        </Space>
      </Button>

      <Modal
        title={<Space><RobotOutlined style={{ color: '#7c3aed' }} />AI智能评估</Space>}
        open={open}
        onCancel={() => setOpen(false)}
        width={760}
        footer={[
          result && canEvaluate && onEvaluate ? (
            <Button key="rerun" icon={<ReloadOutlined />} loading={loading} onClick={() => void onEvaluate()}>
              再次评估
            </Button>
          ) : null,
          !jobName && onChooseJob ? (
            <Button key="choose" type="primary" onClick={() => { setOpen(false); onChooseJob(); }}>
              选择职位匹配
            </Button>
          ) : null,
          <Button key="close" type={result ? 'primary' : 'default'} onClick={() => setOpen(false)}>关闭</Button>,
        ].filter(Boolean)}
      >
        {!result ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={loading ? '正在根据岗位要求生成AI评估…' : jobName ? '尚未生成评估结果' : '请先为候选人分配职位或选择职位匹配'}
          >
            {jobName && canEvaluate && onEvaluate && !loading && (
              <Button type="primary" onClick={() => void onEvaluate()}>开始AI评估</Button>
            )}
          </Empty>
        ) : (
          <>
            <div style={{ border: '1px solid #eaecf0', borderRadius: 10, padding: 16, background: '#fcfcfd' }}>
              <Space align="start" size={24} wrap>
                <div style={{ minWidth: 112 }}>
                  <Typography.Text type="secondary">AI评估</Typography.Text>
                  <div style={{ marginTop: 6 }}>
                    <Tag color={decisionColor(result)} style={{ fontSize: 15, padding: '3px 10px' }}>
                      {decisionText(result)}
                    </Tag>
                  </div>
                </div>
                <div style={{ minWidth: 190 }}>
                  <Typography.Text type="secondary">匹配指数</Typography.Text>
                  <div style={{ marginTop: 4 }}>
                    <Rate disabled allowHalf value={starScore} style={{ color: '#ff9f1a', fontSize: 20 }} />
                    <Typography.Text strong style={{ marginLeft: 8 }}>{starScore} / 5</Typography.Text>
                  </div>
                </div>
                <div>
                  <Typography.Text type="secondary">匹配职位</Typography.Text>
                  <div style={{ marginTop: 6 }}><Tag color="blue">{result.job_name || jobName || '-'}</Tag></div>
                </div>
              </Space>
              <Typography.Paragraph style={{ margin: '14px 0 0' }}>{result.summary}</Typography.Paragraph>
            </div>

            <Typography.Title level={5} style={{ marginTop: 20, marginBottom: 6 }}>必选贴合项</Typography.Title>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 10 }}>
              根据该岗位设置的学历、工作年限、硬性技能和必备技能逐项核验。
            </Typography.Paragraph>
            <List
              bordered
              dataSource={requirements}
              locale={{ emptyText: '该岗位尚未配置必选项，建议先在职位设置中完善筛选要求' }}
              renderItem={(item) => {
                const status = STATUS_VIEW[item.status];
                return (
                  <List.Item style={{ alignItems: 'flex-start' }}>
                    <Space align="start" size={10} style={{ width: '100%' }}>
                      <span style={{ marginTop: 2 }}>{status.icon}</span>
                      <div style={{ flex: 1 }}>
                        <Space wrap>
                          <Typography.Text strong>{item.label}</Typography.Text>
                          <Tag color={status.color}>{status.text}</Tag>
                        </Space>
                        <Typography.Paragraph type="secondary" style={{ margin: '5px 0 0' }}>
                          证据：{item.evidence}
                        </Typography.Paragraph>
                      </div>
                    </Space>
                  </List.Item>
                );
              }}
            />

            <Typography.Title level={5} style={{ marginTop: 20, marginBottom: 10 }}>分项智能评估</Typography.Title>
            <div style={{ display: 'grid', gap: 10 }}>
              {result.dimensions.map((dimension) => (
                <div key={dimension.name}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                    <Typography.Text>{dimension.name}</Typography.Text>
                    <Typography.Text type="secondary">
                      {dimension.status === 'not_configured' ? '未配置' : `${dimension.score}/${dimension.max_score}`}
                    </Typography.Text>
                  </div>
                  <Progress
                    showInfo={false} size="small"
                    percent={dimension.status === 'not_configured' || !dimension.max_score
                      ? 0 : Math.round(dimension.score / dimension.max_score * 100)}
                    strokeColor={dimension.status === 'matched' ? '#22a06b' : dimension.status === 'missing' ? '#ff7875' : '#d99b1d'}
                  />
                </div>
              ))}
            </div>
            <Typography.Paragraph type="secondary" style={{ margin: '16px 0 0', fontSize: 12 }}>
              AI评估用于辅助筛选，不会自动推进或淘汰候选人，最终结论由HR确认。
            </Typography.Paragraph>
          </>
        )}
      </Modal>
    </>
  );
}
