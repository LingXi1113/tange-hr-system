import {
  CalendarOutlined,
  LeftOutlined,
  RightOutlined,
  SearchOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { Alert, Avatar, Button, Empty, Input, Spin, Tag } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { WorkbenchPriorities } from '@/components/WorkbenchPriorities';
import { fetchNotifications } from '@/services/notification';
import type { NotificationItem } from '@/services/notification';
import { PageLoading } from '@/components/PageLoading';
import { fetchCandidates } from '@/services/candidate';
import type { CandidateRow } from '@/services/candidate';
import { fetchDashboardSummary } from '@/services/dashboard';
import type { DashboardSummary } from '@/services/dashboard';
import { fetchInterviews } from '@/services/interview';
import type { Interview } from '@/services/interview';
import { useCurrentUser } from '@/services/user';
import { subscribeBusinessDataChanged } from '@/utils/businessDataEvents';

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
  const [summaryError, setSummaryError] = useState(false);
  const [scheduleError, setScheduleError] = useState(false);
  const [reminders, setReminders] = useState<NotificationItem[]>([]);
  const [reminderTotal, setReminderTotal] = useState<number | null>(null);
  const [reminderLoading, setReminderLoading] = useState(true);
  const [reminderError, setReminderError] = useState(false);
  const reminderRequestRef = useRef(0);
  const canViewTeam = user?.role === 'hr' || user?.role === 'super_admin';
  const [scheduleLoading, setScheduleLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [searchResults, setSearchResults] = useState<CandidateRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchCompleted, setSearchCompleted] = useState(false);
  const searchBoxRef = useRef<HTMLDivElement>(null);
  const searchRequestRef = useRef(0);
  const summaryRequestRef = useRef(0);
  const scheduleRequestRef = useRef(0);
  const [weekStart, setWeekStart] = useState(() => mondayOf(dayjs()));
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [visibleKinds, setVisibleKinds] = useState<Set<ScheduleKind>>(
    () => new Set(SCHEDULE_KINDS.map((item) => item.key)),
  );

  const loadSummary = useCallback(async (showLoading = false) => {
    const requestId = ++summaryRequestRef.current;
    if (showLoading) setLoading(true);
    try {
      const data = await fetchDashboardSummary();
      if (requestId === summaryRequestRef.current) { setSummary(data); setSummaryError(false); }
    } catch {
      if (requestId === summaryRequestRef.current) setSummaryError(true);
    } finally {
      if (requestId === summaryRequestRef.current) setLoading(false);
    }
  }, []);

  const loadReminders = useCallback(async () => {
    const requestId = ++reminderRequestRef.current;
    setReminderLoading(true);
    try {
      const data = await fetchNotifications({ status: 'unread', scene_group: 'deadline', page: 1, page_size: 3 });
      if (requestId === reminderRequestRef.current) {
        setReminders(data.list); setReminderTotal(data.total); setReminderError(false);
      }
    } catch {
      if (requestId === reminderRequestRef.current) setReminderError(true);
    } finally {
      if (requestId === reminderRequestRef.current) setReminderLoading(false);
    }
  }, []);
  useEffect(() => {
    void loadReminders();
    return () => { reminderRequestRef.current += 1; };
  }, [loadReminders]);

  const loadSchedule = useCallback(async () => {
    const requestId = ++scheduleRequestRef.current;
    setScheduleLoading(true);
    setScheduleError(false);
    try {
      const data = await fetchInterviews({
        date_from: weekStart.format('YYYY-MM-DD'),
        date_to: weekStart.add(6, 'day').format('YYYY-MM-DD'),
        page: 1,
        page_size: 100,
      });
      if (requestId === scheduleRequestRef.current) {
        setInterviews(data.list.filter((item) => ACTIVE_INTERVIEW_STATUSES.has(item.status)));
      }
    } catch {
      if (requestId === scheduleRequestRef.current) { setInterviews([]); setScheduleError(true); }
    } finally {
      if (requestId === scheduleRequestRef.current) setScheduleLoading(false);
    }
  }, [weekStart]);

  useEffect(() => {
    void loadSummary(true);
    return () => { summaryRequestRef.current += 1; };
  }, [loadSummary]);

  useEffect(() => {
    void loadSchedule();
    return () => { scheduleRequestRef.current += 1; };
  }, [loadSchedule]);

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

  const search = useCallback(async (rawKeyword: string) => {
    const value = rawKeyword.trim();
    if (!value) {
      setSearchResults([]);
      setSearchCompleted(false);
      setSearchOpen(false);
      return;
    }
    const requestId = ++searchRequestRef.current;
    setSearchLoading(true);
    setSearchOpen(true);
    try {
      const data = await fetchCandidates({ keyword: value, page: 1, page_size: 6 });
      if (requestId === searchRequestRef.current) {
        setSearchResults(data.list);
        setSearchCompleted(true);
      }
    } catch {
      if (requestId === searchRequestRef.current) {
        setSearchResults([]);
        setSearchCompleted(true);
      }
    } finally {
      if (requestId === searchRequestRef.current) setSearchLoading(false);
    }
  }, []);

  useEffect(() => {
    const value = keyword.trim();
    if (!value) {
      searchRequestRef.current += 1;
      setSearchResults([]);
      setSearchCompleted(false);
      setSearchLoading(false);
      setSearchOpen(false);
      return undefined;
    }
    const timer = window.setTimeout(() => { void search(value); }, 300);
    return () => window.clearTimeout(timer);
  }, [keyword, search]);

  useEffect(() => {
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!searchBoxRef.current?.contains(event.target as Node)) setSearchOpen(false);
    };
    document.addEventListener('mousedown', closeOnOutsideClick);
    return () => document.removeEventListener('mousedown', closeOnOutsideClick);
  }, []);

  useEffect(() => {
    let refreshTimer: number | undefined;
    const refreshWorkbench = () => {
      void loadSummary();
      void loadSchedule();
      void loadReminders();
      if (keyword.trim()) void search(keyword);
    };
    const queueRefresh = () => {
      if (refreshTimer) window.clearTimeout(refreshTimer);
      refreshTimer = window.setTimeout(refreshWorkbench, 150);
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') queueRefresh();
    };

    const unsubscribe = subscribeBusinessDataChanged(queueRefresh);
    window.addEventListener('focus', queueRefresh);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    const pollTimer = window.setInterval(() => {
      if (document.visibilityState === 'visible') refreshWorkbench();
    }, 30_000);

    return () => {
      unsubscribe();
      window.removeEventListener('focus', queueRefresh);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.clearInterval(pollTimer);
      if (refreshTimer) window.clearTimeout(refreshTimer);
    };
  }, [keyword, loadSchedule, loadSummary, loadReminders, search]);

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
      <div className="workbench-page-heading">
        <div><h1>招聘工作台</h1><p>{user?.name}，先处理待办，再查看招聘进展与面试日程。</p></div>
        <div><span>统计更新：{summary?.generated_at || '尚未更新'}</span>
          <Button aria-label="刷新工作台" icon={<ReloadOutlined />} onClick={() => { void loadSummary(); void loadSchedule(); void loadReminders(); }}>刷新工作台</Button>
        </div>
      </div>
      {summaryError && <Alert style={{ marginBottom: 16 }} type="warning" showIcon
        message={summary ? '工作台刷新失败，当前显示上次成功的数据' : '工作台统计加载失败，请重试'}
        action={<Button size="small" onClick={() => void loadSummary()}>重试</Button>} />}
      {canViewTeam && <WorkbenchPriorities summary={summary} reminders={reminders}
        reminderTotal={reminderTotal} reminderLoading={reminderLoading} reminderError={reminderError}
        onNavigate={navigate} onRetry={() => void loadReminders()} />}
      {!canViewTeam && <Alert style={{ marginBottom: 16 }} type="info" message="团队待办由招聘 HR 统一跟进"
        action={<Button onClick={() => navigate('/tasks')}>查看我的任务</Button>} />}
      <div className="workbench-top-actions">
        <div className="workbench-search-box" ref={searchBoxRef}>
          <Input
            value={keyword}
            allowClear
            placeholder="通过姓名、手机号、邮箱、公司、任职职位、学校搜索"
            onChange={(event) => {
              setKeyword(event.target.value);
              setSearchResults([]);
              setSearchCompleted(false);
            }}
            onFocus={() => { if (keyword.trim()) setSearchOpen(true); }}
            onPressEnter={() => { void search(keyword); }}
            onKeyDown={(event) => { if (event.key === 'Escape') setSearchOpen(false); }}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={() => { void search(keyword); }} aria-label="搜索" />
          {searchOpen && keyword.trim() && (
            <div className="workbench-search-dropdown">
              <div className="workbench-search-dropdown-head">
                <strong>候选人</strong>
                <span>搜索“{keyword.trim()}”</span>
              </div>
              <Spin spinning={searchLoading}>
                <div className="workbench-search-results">
                  {!searchLoading && searchCompleted && searchResults.length === 0 ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未找到匹配的候选人" />
                  ) : searchResults.map((candidate) => (
                    <button
                      type="button"
                      className="workbench-search-candidate"
                      key={candidate.id}
                      onClick={() => {
                        setSearchOpen(false);
                        navigate(`/candidates/${candidate.id}`);
                      }}
                    >
                      <Avatar size={42}>{candidate.name.slice(0, 1)}</Avatar>
                      <span className="workbench-search-candidate-main">
                        <span className="workbench-search-candidate-title">
                          <strong>{candidate.name}</strong>
                          <span>{candidate.gender || '未知'}{candidate.age ? ` · ${candidate.age}岁` : ''}</span>
                          {candidate.latest_application?.process_state_label && (
                            <Tag color="blue">{candidate.latest_application.process_state_label}</Tag>
                          )}
                        </span>
                        <span className="workbench-search-candidate-line">
                          {candidate.work_summary?.company || '暂无公司经历'}
                          {candidate.work_summary?.position ? ` · ${candidate.work_summary.position}` : ''}
                          {candidate.work_summary?.start || candidate.work_summary?.end
                            ? ` · ${candidate.work_summary.start || ''} 至 ${candidate.work_summary.end || '至今'}` : ''}
                        </span>
                        <span className="workbench-search-candidate-line is-secondary">
                          {candidate.latest_application?.job_name || '未分配职位'}
                          {' · '}{candidate.education_summary?.school || '院校未填写'}
                          {candidate.highest_education ? ` · ${candidate.highest_education}` : ''}
                        </span>
                      </span>
                      <span className="workbench-search-candidate-enter">查看详情</span>
                    </button>
                  ))}
                </div>
              </Spin>
              {searchCompleted && searchResults.length > 0 && (
                <button
                  type="button"
                  className="workbench-search-all"
                  onClick={() => navigate(`/candidates?keyword=${encodeURIComponent(keyword.trim())}`)}
                >
                  查看全部“{keyword.trim()}”的候选人
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {!summary ? <Empty description="工作台数据暂不可用" /> : (
        <>
          {canViewTeam && <details className="workbench-overview">
          <summary>招聘阶段概览 <span>查看初筛、业务推荐、面试和录用统计</span></summary>
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

          </details>}
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
              <div className="workbench-schedule-controls">
                <Button onClick={() => setWeekStart(mondayOf(dayjs()))}>回到本周</Button>
                <Button icon={<CalendarOutlined />} onClick={() => navigate('/interviews')}>全部日程</Button>
              </div>
            </header>

            {scheduleError && <Alert type="warning" message="面试日程加载失败，请重试" showIcon
              action={<Button size="small" onClick={() => void loadSchedule()}>重试</Button>} />}
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
                              onClick={() => navigate(`/interviews?interview_id=${interview.id}`)}
                            >
                              <strong>{interview.start_at.slice(11, 16)} {interview.candidate_name}</strong>
                              <span>
                                {interview.job_name} · {interview.round}
                                {interview.process_state_label ? ` · ${interview.process_state_label}` : ''}
                              </span>
                            </button>
                          );
                        })}
                    </div>
                  );
                })}
                <div />
                {!scheduleLoading && !scheduleError && visibleInterviews.length === 0 && (
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
