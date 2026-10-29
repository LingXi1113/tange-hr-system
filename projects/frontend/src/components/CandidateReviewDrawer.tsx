import { LeftOutlined, RightOutlined, ExportOutlined } from '@ant-design/icons';
import { Button, Drawer, Space, Typography } from 'antd';
import { useCallback, useState } from 'react';
import { CandidateDetailPage } from '@/pages/CandidateDetailPage';
import type { CandidateRow } from '@/services/candidate';

export function CandidateReviewDrawer({ queue, initialIndex, onClose }: {
  queue: CandidateRow[];
  initialIndex: number;
  onClose: () => void;
}) {
  const [index, setIndex] = useState(initialIndex);
  const [blocked, setBlocked] = useState(false);
  const setReviewBlocked = useCallback((value: boolean) => setBlocked(value), []);
  const current = queue[index];
  if (!current) return null;
  const detailUrl = '#/candidates/' + current.id
    + (current.application_id ? '?application_id=' + current.application_id : '');
  return (
    <Drawer
      open
      width="min(1440px, 96vw)"
      title={<Space wrap><span>候选人审阅</span>
        <Typography.Text type="secondary">当前页 {index + 1} / {queue.length}</Typography.Text>
      </Space>}
      onClose={onClose}
      closable={!blocked}
      maskClosable={false}
      keyboard={!blocked}
      className="candidate-review-drawer"
      extra={<Space wrap>
        <Button icon={<LeftOutlined />} disabled={blocked || index === 0}
          onClick={() => setIndex((value) => value - 1)}>上一位</Button>
        <Button icon={<RightOutlined />} disabled={blocked || index === queue.length - 1}
          onClick={() => setIndex((value) => value + 1)}>下一位</Button>
        <Button href={detailUrl} target="_blank" rel="noopener noreferrer"
          icon={<ExportOutlined />}>独立页面</Button>
      </Space>}
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
        {blocked ? '请先保存或取消当前操作，再切换候选人。'
          : '按打开时的当前页顺序审阅；关闭后保留列表条件和位置。翻页可继续审阅其他候选人。'}
      </Typography.Paragraph>
      <CandidateDetailPage key={String(current.id) + ':' + String(current.application_id ?? '')}
        candidateId={current.id} initialApplicationId={current.application_id ?? undefined}
        embedded onClose={() => { if (!blocked) onClose(); }}
        onReviewBlockedChange={setReviewBlocked} />
    </Drawer>
  );
}
