import {
  CalendarOutlined,
  LeftOutlined,
  RightOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { Button, Empty, Input, Spin } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { fetchDashboardSummary } from '@/services/dashboard';
import type { DashboardSummary } from '@/services/dashboard';
import { fetchInterviews } from '@/services/interview';
import type { Interview } from '@/services/interview';
import { useCurrentUser } from '@/services/user';

const WEEKDAY_TEXT = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const ACTIVE_INTERVIEW_STATUSES = new Set(['pending', 'invited', 'confirmed', 'rescheduled']);

type ScheduleKind = 'mine' | 'others' | 'interviewer';

const SCHEDULE_KINDS: { key: ScheduleKind; label: string; color: string }[] = [
  { key: 'mine', label: '我安排的', color: '#9f8df1' },
  { key: 'others', label: 'TA安排的', color: '#f6ad63' },
  { key: 'interviewer', label: '待我面试', color: '#65d4ad' },
];

function mondayOf(value: Dayjs) {
  return value.startOf('day').subtract((value.day() + 6) % 7, 'day');
}

function interviewKind(interview: Interview, userId: string): ScheduleKind {
  if (interview.interviewer_id === userId) return 'interviewer';
  if (interview.created_by === userId) return 'mine';
  return 'others';
}

export function WorkbenchPage() {
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [scheduleLoading, setScheduleLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [weekStart, setWeekStart] = useState(() => mondayOf(dayjs()));
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [visibleKinds, setVisibleKinds] = useState<Set<ScheduleKind>>(
    () => new Set(SCHEDULE_KINDS.map((item) => item.key)),
  );

  useEffect(() => {
    let mounted = true;
    void fetchDashboardSummary()
      .then((data) => { if (mounted) setSummary(data); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    let mounted = true;
    setScheduleLoading(true);
    void fetchInterviews({
      date_from: weekStart.format('YYYY-MM-DD'),
      date_to: weekStart.add(6, 'day').format('YYYY-MM-DD'),
      page: 1,
      page_size: 100,
    }).then((data) => {
      if (mounted) {
        setInterviews(data.list.filter((item) => ACTIVE_INTERVIEW_STATUSES.has(item.status)));
      }
    }).catch(() => {
      if (mounted) setInterviews([]);
    }).finally(() => {
      if (mounted) setScheduleLoading(false);
    });
    return () => { mounted = false; };
  }, [weekStart]);

  const weekDates = useMemo(
    () => Array.from({ length: 7 }, (_, index) => weekStart.add(index, 'day')),
    [weekStart],
  );
  const visibleInterviews = useMemo(() => interviews.filter((item) => (
    visibleKinds.has(interviewKind(item, user?.user_id ?? ''))
  )), [interviews, user?.user_id, visibleKinds]);
  const interviewsByDate = useMemo(() => visibleInterviews.reduce<Record<string, Interview[]>>((groups, item) => {
    const key = item.start_at.slice(0, 10);
    (groups[key] ??= []).push(item);
    return groups;
  }, {}), [visibleInterviews]);

  const search = () => {
    const value = keyword.trim();
    navigate(value ? `/candidates?keyword=${encodeURIComponent(value)}` : '/candidates');
  };

  const toggleKind = (kind: ScheduleKind) => {
    setVisibleKinds((current) => {
      const next = new Set(current);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  };

  if (loading) return <PageLoading tip="正在加载工作台…" />;

  return (
    <div className="workbench-page">
      <div className="workbench-top-actions">
        <div className="workbench-search-box">
          <Input
            value={keyword}
            allowClear
            placeholder="通过姓名、手机号、邮箱、公司、任职职位、学校搜索"
            onChange={(event) => setKeyword(event.target.value)}
            onPressEnter={search}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={search} aria-label="搜索" />
        </div>
      </div>

      {!summary ? <Empty description="工作台数据暂不可用" /> : (
        <>
          <div className="workbench-metric-grid">
            {(summary.workbench_metrics ?? []).map((group) => (
              <section className="workbench-metric-group" key={group.key}>
                <h3><i />{group.title}</h3>
                <div className="workbench-metric-items">
                  {group.items.map((item) => (
                    <button type="button" key={item.key} onClick={() => navigate(item.route)}>
                      <strong>{item.count}</strong>
                      <span>{item.label}</span>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>

          <section className="workbench-schedule">
            <header className="workbench-schedule-head">
              <div className="workbench-schedule-title">
                <h3><i />面试日程</h3>
                <div className="workbench-schedule-kinds">
                  {SCHEDULE_KINDS.map((item) => (
                    <button
                      type="button"
                      key={item.key}
                      className={visibleKinds.has(item.key) ? 'is-active' : ''}
                      onClick={() => toggleKind(item.key)}
                    >
                      <i style={{ background: item.color }} />{item.label}
                    </button>
                  ))}
                </div>
              </div>
              <Button icon={<CalendarOutlined />} onClick={() => navigate('/interviews')}>全部日程</Button>
            </header>

            <Spin spinning={scheduleLoading}>
              <div className="workbench-week">
                <button type="button" className="workbench-week-arrow" onClick={() => setWeekStart((value) => value.subtract(7, 'day'))} aria-label="上一周">
                  <LeftOutlined />
                </button>
                {weekDates.map((date, index) => {
                  const isToday = date.isSame(dayjs(), 'day');
                  return (
                    <div className={`workbench-week-day${isToday ? ' is-today' : ''}`} key={date.format('YYYY-MM-DD')}>
                      <span>{WEEKDAY_TEXT[index]}</span>
                      <strong>{date.date()}</strong>
                    </div>
                  );
                })}
                <button type="button" className="workbench-week-arrow" onClick={() => setWeekStart((value) => value.add(7, 'day'))} aria-label="下一周">
                  <RightOutlined />
                </button>
              </div>

              <div className="workbench-week-events">
                <div />
                {weekDates.map((date) => {
                  const dateKey = date.format('YYYY-MM-DD');
                  return (
                    <div className="workbench-day-events" key={dateKey}>
                      {(interviewsByDate[dateKey] ?? [])
                        .sort((left, right) => left.start_at.localeCompare(right.start_at))
                        .map((interview) => {
                          const kind = interviewKind(interview, user?.user_id ?? '');
                          const color = SCHEDULE_KINDS.find((item) => item.key === kind)?.color;
                          return (
                            <button
                              type="button"
                              className="workbench-interview-event"
                              key={interview.id}
                              style={{ borderLeftColor: color }}
                              onClick={() => navigate('/interviews')}
                            >
                              <strong>{interview.start_at.slice(11, 16)} {interview.candidate_name}</strong>
                              <span>{interview.job_name} · {interview.round}</span>
                            </button>
                          );
                        })}
                    </div>
                  );
                })}
                <div />
                {!scheduleLoading && visibleInterviews.length === 0 && (
                  <div className="workbench-schedule-empty">
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无日程安排" />
                  </div>
                )}
              </div>
            </Spin>
          </section>
        </>
      )}
    </div>
  );
}
