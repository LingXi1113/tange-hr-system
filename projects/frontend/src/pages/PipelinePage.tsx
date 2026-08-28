import { DownloadOutlined, LockOutlined } from '@ant-design/icons';
import { Button, Checkbox, Empty, Input, Modal, Select, Space, Tag, Tooltip } from 'antd';
import { useCallback, useEffect, useState } from 'react';

import { PageLoading } from '@/components/PageLoading';
import { eliminateApplication, fetchBoard, moveApplication } from '@/services/pipeline';
import type { BoardCard, BoardColumn } from '@/services/pipeline';
import { fetchJobs } from '@/services/job';
import { addToPool } from '@/services/talentPool';
import { useCurrentUser } from '@/services/user';
import { msg } from '@/utils/message';

const APPLICATION_STATUS_TEXT: Record<string, string> = {
  in_progress: '进行中', pending_onboard: '待入职', onboarded: '已入职', eliminated: '已淘汰',
};

function csvCell(value: unknown) {
  return `"${String(value ?? '').replace(/"/g, '""')}"`;
}

export function PipelinePage() {
  const { user } = useCurrentUser();
  const canManage = user?.role === 'hr';
  const [jobs, setJobs] = useState<{ id: number; name: string }[]>([]);
  const [jobId, setJobId] = useState<number | null>(null);
  const [columns, setColumns] = useState<BoardColumn[]>([]);
  const [cards, setCards] = useState<BoardCard[]>([]);
  const [loading, setLoading] = useState(false);
  const [moveTarget, setMoveTarget] = useState<BoardCard | null>(null);
  const [moveStage, setMoveStage] = useState('');
  const [moveReason, setMoveReason] = useState('');
  const selectedJob = jobs.find((job) => job.id === jobId);

  function exportCurrentBoard() {
    if (!selectedJob || !columns.length) return;
    const rows: unknown[][] = [[
      '职位', '阶段', '候选人', '状态', '负责人', '进入阶段时间', '停留时间',
      '锁定开始时间', '锁定结束时间', '淘汰原因',
    ]];
    columns.forEach((column) => {
      const columnCards = cards.filter((card) => card.current_stage === column.stage_key);
      if (!columnCards.length) {
        rows.push([selectedJob.name, column.name, '', '暂无候选人', '', '', '', '', '', '']);
        return;
      }
      columnCards.forEach((card) => {
        rows.push([
          selectedJob.name,
          column.name,
          card.candidate_name,
          APPLICATION_STATUS_TEXT[card.status] ?? card.status,
          card.owner_name,
          card.stage_entered_at,
          card.stay,
          card.lock?.start_at ?? '',
          card.lock?.end_at ?? '',
          card.eliminate_reason,
        ]);
      });
    });
    const csv = `\uFEFF${rows.map((row) => row.map(csvCell).join(',')).join('\r\n')}`;
    const objectUrl = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = `${selectedJob.name}-招聘流程.csv`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    msg.success('当前职位招聘流程已导出');
  }

  useEffect(() => {
    fetchJobs({ page_size: 100 }).then((data) => {
      setJobs(data.list.map((j) => ({ id: j.id, name: j.name })));
      if (data.list.length && jobId == null) setJobId(data.list[0].id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadBoard = useCallback(async () => {
    if (!jobId) return;
    setLoading(true);
    try {
      const data = await fetchBoard({ job_id: jobId });
      setColumns(data.columns);
      setCards(data.cards);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void loadBoard();
  }, [loadBoard]);

  async function confirmMove() {
    if (!moveTarget) return;
    if (!moveStage) {
      msg.error('请选择目标阶段');
      return;
    }
    if (!moveReason.trim()) {
      msg.error('请填写移动原因');
      return;
    }
    await moveApplication(moveTarget.id, {
      to_stage: moveStage, reason: moveReason, version: moveTarget.version,
    });
    msg.success('已流转阶段');
    setMoveTarget(null);
    setMoveStage('');
    setMoveReason('');
    void loadBoard();
  }

  function confirmEliminate(card: BoardCard) {
    let reason = '';
    const opts = { toPool: false };
    Modal.confirm({
      title: `淘汰 ${card.candidate_name}？`,
      content: (
        <div>
          <Input.TextArea
            rows={3} placeholder="必填淘汰原因"
            onChange={(e) => { reason = e.target.value; }}
          />
          <Checkbox
            style={{ marginTop: 8 }}
            onChange={(e) => { opts.toPool = e.target.checked; }}
          >
            同时加入人才库
          </Checkbox>
        </div>
      ),
      okText: '确认淘汰',
      okButtonProps: { danger: true },
      onOk: async () => {
        if (!reason.trim()) {
          msg.error('必须填写淘汰原因');
          throw new Error('reason required');
        }
        await eliminateApplication(card.id, reason, card.version);
        if (opts.toPool) {
          try {
            await addToPool({
              candidate_id: card.candidate_id,
              source: 'elimination_added',
              reason: reason.trim(),
            });
            msg.success('已淘汰并加入人才库');
          } catch {
            msg.success('已淘汰（加入人才库失败：可能已在库中）');
          }
        } else {
          msg.success('已淘汰');
        }
        void loadBoard();
      },
    });
  }

  return (
    <div>
      <div className="page-head pipeline-board-head">
        <h2 className="page-title">招聘流程看板</h2>
        {selectedJob && <div className="pipeline-board-job">职位：{selectedJob.name}</div>}
        <Select
          style={{ width: 260 }} placeholder="选择职位" showSearch optionFilterProp="label"
          value={jobId ?? undefined}
          onChange={(v) => setJobId(v)}
          options={jobs.map((j) => ({ value: j.id, label: j.name }))}
        />
        <Button
          icon={<DownloadOutlined />}
          disabled={!jobId || loading || !columns.length}
          onClick={exportCurrentBoard}
        >
          导出当前职位
        </Button>
      </div>
      <div className="hrats-block">
        {loading ? (
          <PageLoading />
        ) : !columns.length ? (
          <Empty description="请先选择职位" />
        ) : (
          <div className="hrates-board">
            {columns.map((col) => {
              const colCards = cards.filter((c) => c.current_stage === col.stage_key);
              return (
                <div className="hrates-board-col" key={`${col.job_id}-${col.stage_key}`}>
                  <div className="col-head">
                    <span>{col.name}</span>
                    <span className="col-count">{colCards.length}</span>
                  </div>
                  {colCards.map((card) => (
                    <div className="hrates-card" key={card.id}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <strong>{card.candidate_name}</strong>
                        {card.lock && (
                          <Tooltip title={`锁定中：${card.lock.start_at} ~ ${card.lock.end_at}`}>
                            <LockOutlined style={{ color: '#FF5219' }} />
                          </Tooltip>
                        )}
                      </div>
                      <div style={{ color: 'rgba(23,26,29,0.5)', fontSize: 12, margin: '4px 0' }}>
                        {card.job_name} · 停留 {card.stay || '-'}
                      </div>
                      {card.status === 'in_progress' && canManage && (
                        <Space size={4}>
                          <Button
                            size="small" type="link" style={{ padding: 0 }}
                            onClick={() => {
                              setMoveTarget(card);
                              setMoveStage('');
                              setMoveReason('');
                            }}
                          >
                            推进
                          </Button>
                          <Button
                            size="small" type="link" danger style={{ padding: 0 }}
                            onClick={() => confirmEliminate(card)}
                          >
                            淘汰
                          </Button>
                        </Space>
                      )}
                      {card.status === 'eliminated' && (
                        <Tag color="default">已淘汰：{card.eliminate_reason || '-'}</Tag>
                      )}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <Modal
        title={moveTarget ? `推进 ${moveTarget.candidate_name}` : ''}
        open={!!moveTarget}
        onCancel={() => setMoveTarget(null)}
        onOk={() => void confirmMove()}
        okText="确认移动"
      >
        <p>
          当前阶段：<Tag>{moveTarget?.stage_name}</Tag>
        </p>
        <Select
          style={{ width: '100%', marginBottom: 12 }} placeholder="目标阶段"
          value={moveStage || undefined}
          onChange={setMoveStage}
          options={columns
            .filter((c) => c.stage_key !== moveTarget?.current_stage && c.stage_key !== 'eliminated')
            .map((c) => ({ value: c.stage_key, label: c.name }))}
        />
        <Input.TextArea
          rows={3} placeholder="必填移动原因（写入流转记录与操作日志）"
          value={moveReason} onChange={(e) => setMoveReason(e.target.value)}
        />
        <p style={{ marginTop: 8, color: 'rgba(23,26,29,0.6)', fontSize: 12 }}>
          离开当前阶段将结束该阶段锁定；进入新阶段按配置重新计时。
        </p>
      </Modal>
    </div>
  );
}
