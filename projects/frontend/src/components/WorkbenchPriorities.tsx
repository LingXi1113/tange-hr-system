import { ArrowRightOutlined, BellOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { Alert, Button, Empty, Tag } from 'antd';
import type { DashboardSummary } from '@/services/dashboard';
import type { NotificationItem } from '@/services/notification';

export function WorkbenchPriorities({ summary, reminders, reminderTotal, reminderLoading, reminderError, onNavigate, onRetry }: {
  summary: DashboardSummary | null;
  reminders: NotificationItem[];
  reminderTotal: number | null;
  reminderLoading: boolean;
  reminderError: boolean;
  onNavigate: (route: string) => void;
  onRetry: () => void;
}) {
  const metric = (group: string, key: string) =>
    summary?.workbench_metrics?.find((item) => item.key === group)?.items.find((item) => item.key === key);
  const screening = metric('screening', 'unprocessed');
  const schedule = metric('interview', 'waiting_schedule');
  const feedback = metric('interview', 'feedback');
  const approval = metric('hiring', 'pending_approval');
  const tasks = [
    { key: 'screen', title: '待初筛', item: screening, unit: '人', hint: '尚未处理的有效初筛候选人' },
    { key: 'schedule', title: '待安排面试', item: schedule, unit: '人', hint: '进入面试阶段、等待约面的候选人' },
    { key: 'feedback', title: '待面试反馈', item: feedback, unit: '场', hint: '等待提交面试评价的场次' },
    { key: 'approval', title: '待跟进审批', item: approval, unit: '份', hint: '团队待审批 Offer，按当前节点跟进' },
    { key: 'deadline', title: '未读到期提醒', unit: '条', hint: '当前账号收到的 Offer、审批、需求和阶段到期提醒',
      item: reminderTotal === null ? undefined : { count: reminderTotal, route: '/notifications?status=unread&scene_group=deadline' } },
  ];
  return (
    <section className="workbench-priorities" aria-label="优先处理">
      <div className="workbench-section-heading">
        <div><h2>优先处理</h2><p>团队待办按业务状态统计，不限于今天创建；到期提醒仅属于当前账号。</p></div>
        <Tag color="blue">招聘协作</Tag>
      </div>
      <div className="workbench-priority-grid">
        {tasks.map((task) => (
          <button type="button" key={task.key} className="workbench-priority-card"
            data-testid={'priority-' + task.key}
            disabled={!task.item || (task.key === 'deadline' && reminderError)}
            onClick={() => task.item && onNavigate(task.item.route)}>
            <span className="workbench-priority-title">{task.title}<ArrowRightOutlined /></span>
            <span className="workbench-priority-number"><strong>{task.item?.count ?? '—'}</strong><small>{task.unit}</small></span>
            <span className="workbench-priority-hint">{task.hint}</span>
            <span className="workbench-priority-action">{!task.item ? '等待数据' : task.item.count ? '查看并处理' : '暂无待办，可查看列表'}</span>
          </button>
        ))}
      </div>
      <div className="workbench-attention">
        <div className="workbench-section-heading">
          <div><h3><BellOutlined /> 到期与逾期提醒</h3><p>提醒数量不等于实时待办数量；业务处理后，可在通知中心标记已读。</p></div>
          <Button onClick={() => onNavigate('/notifications?status=unread&scene_group=deadline')}>查看全部提醒</Button>
        </div>
        {reminderError ? <Alert type="warning" showIcon message="到期提醒暂时无法加载"
          action={<Button size="small" onClick={onRetry}>重试</Button>} /> :
          reminderLoading && reminderTotal === null ? <p role="status">正在加载提醒…</p> :
          !reminders.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<span><CheckCircleOutlined /> 暂无未读到期提醒</span>} /> :
          <div className="workbench-attention-list">{reminders.map((item) => (
            <button type="button" key={item.id} onClick={() => onNavigate(item.route || '/notifications?status=unread&scene_group=deadline')}>
              <span><strong>{item.title}</strong><span>{item.content}</span></span>
              <small>提醒生成于 {item.created_at}</small><ArrowRightOutlined />
            </button>
          ))}</div>}
      </div>
    </section>
  );
}
