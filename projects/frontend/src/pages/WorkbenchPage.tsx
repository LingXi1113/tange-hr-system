import {
  CalendarOutlined,
  LeftOutlined,
  RightOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Empty, Input, Spin, Tag } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { fetchCandidates } from '@/services/candidate';
import type { CandidateRow } from '@/services/candidate';
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
  const [searchResults, setSearchResults] = useState<CandidateRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchCompleted, setSearchCompleted] = useState(false);
  const searchBoxRef = useRef<HTMLDivElement>(null);
  const searchRequestRef = useRef(0);
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
