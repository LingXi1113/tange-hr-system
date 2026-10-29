import { LeftOutlined, RightOutlined, ReloadOutlined } from '@ant-design/icons';
import { Alert, Button, DatePicker, Descriptions, Drawer, Empty, Segmented, Space, Spin, Tag, Typography } from 'antd';
import dayjs from 'dayjs';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchInterview, fetchInterviews, INTERVIEW_STATUS_TEXT, INTERVIEW_TYPE_TEXT } from '@/services/interview';
import type { Interview } from '@/services/interview';
import { useBusinessRefresh } from '@/utils/useBusinessRefresh';

const ACTIVE = new Set(['pending', 'invited', 'confirmed', 'rescheduled']);
type Filters = {
 status: string; round: string; interviewer: string; action_state: string;
 job_id?: number; status_group: string; candidate_id?: number; application_id?: number;
};
export function InterviewCalendar({ filters, canManage, userId, onEdit, onReschedule, onFeedback, onCandidate }: {
 filters: Filters; canManage: boolean; userId?: string;
 onEdit: (record: Interview) => void; onReschedule: (record: Interview) => void;
 onFeedback: (record: Interview) => void; onCandidate: (record: Interview) => void;
}) {
 const [anchor, setAnchor] = useState(() => dayjs().startOf('day'));
 const [mode, setMode] = useState<'week' | 'day'>('week');
 const [rows, setRows] = useState<Interview[]>([]);
 const [loading, setLoading] = useState(true);
 const [failed, setFailed] = useState(false);
 const [selectedId, setSelectedId] = useState<number | null>(null);
 const [detail, setDetail] = useState<Interview | null>(null);
 const [detailLoading, setDetailLoading] = useState(false);
 const [detailFailed, setDetailFailed] = useState(false);
 const listRequest = useRef(0), detailRequest = useRef(0);
 const from = (mode === 'day' ? anchor : anchor.subtract((anchor.day() + 6) % 7, 'day')).startOf('day');
 const fromKey = from.format('YYYY-MM-DD');
 const toKey = from.add(mode === 'day' ? 0 : 6, 'day').format('YYYY-MM-DD');
 const filterKey = JSON.stringify(filters);
 const load = useCallback(async () => {
  const requestId = ++listRequest.current;
  setLoading(true); setFailed(false);
  try {
   const result: Interview[] = [];
   let total = 0;
   for (let page = 1; page <= 10; page++) {
    const data = await fetchInterviews({ ...JSON.parse(filterKey), date_from: fromKey, date_to: toKey,
      date_range_mode: 'overlap', page, page_size: 100 });
    if (requestId !== listRequest.current) return;
    result.push(...data.list); total = data.total;
    if (result.length >= total) break;
    if (!data.list.length) throw new Error('Incomplete calendar data');
   }
   if (result.length < total) throw new Error('Too many interviews for this calendar range');
   if (requestId === listRequest.current) setRows([...new Map(result.map(row => [row.id, row])).values()]);
  } catch {
   if (requestId === listRequest.current) { setRows([]); setFailed(true); }
  } finally {
   if (requestId === listRequest.current) setLoading(false);
  }
 }, [fromKey, toKey, filterKey]);
 useEffect(() => { void load(); return () => { listRequest.current += 1; }; }, [load]);
 useBusinessRefresh(load);
 const loadDetail = useCallback(async () => {
  if (selectedId === null) return;
  const requestId = ++detailRequest.current;
  setDetail(null); setDetailLoading(true); setDetailFailed(false);
  try {
   const data = await fetchInterview(selectedId);
   if (requestId === detailRequest.current) setDetail(data);
  } catch { if (requestId === detailRequest.current) setDetailFailed(true); }
  finally { if (requestId === detailRequest.current) setDetailLoading(false); }
 }, [selectedId]);
 useEffect(() => { void loadDetail(); return () => { detailRequest.current += 1; }; }, [loadDetail]);
 useBusinessRefresh(loadDetail);
 const conflicts = useMemo(() => {
  const ids = new Set<number>();
  const active = rows.filter(row => ACTIVE.has(row.status) && !row.application_archived);
  for (let i=0; i<active.length; i++) for(let j=i+1;j<active.length;j++) {
   const a=active[i], b=active[j];
   if ((a.candidate_id === b.candidate_id || (a.interviewer_id && a.interviewer_id === b.interviewer_id))
    && dayjs(a.start_at).isBefore(dayjs(b.end_at)) && dayjs(b.start_at).isBefore(dayjs(a.end_at))) {
    ids.add(a.id);ids.add(b.id);
   }
  }
  return ids;
 }, [rows]);
 const days = Array.from({length: mode === 'day' ? 1 : 7},(_,i)=>from.add(i,'day'));
 const visible = !failed && !loading;
 return <section className="interview-calendar" aria-label="面试日历">
  <div className="interview-calendar-toolbar">
   <Space wrap>
    <Segmented value={mode} options={[{label:'周视图',value:'week'},{label:'日视图',value:'day'}]}
      onChange={value=>setMode(value as 'week'|'day')} />
    <Button aria-label="上一时段" icon={<LeftOutlined />} onClick={()=>setAnchor(value=>value.subtract(mode==='day'?1:7,'day'))} />
    <Button onClick={()=>setAnchor(dayjs().startOf('day'))}>今天</Button>
    <Button aria-label="下一时段" icon={<RightOutlined />} onClick={()=>setAnchor(value=>value.add(mode==='day'?1:7,'day'))} />
    <DatePicker aria-label="选择日历日期" value={anchor} allowClear={false} onChange={value=>{if(value)setAnchor(value.startOf('day'));}} />
   </Space>
   <Space><Typography.Text>{fromKey} 至 {toKey}</Typography.Text>
    <Button aria-label="刷新日历" icon={<ReloadOutlined />} onClick={()=>void load()}>刷新</Button></Space>
  </div>
  <Typography.Paragraph type="secondary">
   使用页面上方条件筛选；按开始时间排列。跨天面试会显示在覆盖的每一天，取消和归档记录以灰色标记。
   日历仅包含系统内面试，不代表企业日历全部空闲时间。
  </Typography.Paragraph>
  {failed && <Alert showIcon type="error" message="日历加载失败或范围过大，请重试或缩小日期及筛选范围"
   action={<Button onClick={()=>void load()}>重试</Button>} />}
  {visible && conflicts.size > 0 && <Alert showIcon type="warning" style={{marginBottom:12}}
    message={'当前结果中有 '+conflicts.size+' 场面试存在时间重叠，请核对候选人及面试官安排'} />}
  <Spin spinning={loading}>
   <div className="interview-calendar-scroll">
    <div className={'interview-calendar-grid '+(mode==='day'?'is-day':'')}>
     {days.map(date=>{
      const events=visible?rows.filter(row=>dayjs(row.start_at).isBefore(date.add(1,'day'))&&dayjs(row.end_at).isAfter(date))
       .sort((a,b)=>a.start_at.localeCompare(b.start_at)||a.id-b.id):[];
      return <section className={'interview-calendar-day'+(date.isSame(dayjs(),'day')?' is-today':'')} key={date.format('YYYY-MM-DD')}>
       <h3>{['周日','周一','周二','周三','周四','周五','周六'][date.day()]} <span>{date.format('MM-DD')}</span></h3>
       <div className="interview-calendar-events">
        {events.map(row=><button type="button" data-testid={'calendar-event-'+row.id} key={row.id}
         className={'interview-calendar-event'+(row.status==='cancelled'||row.application_archived?' is-muted':'')}
         onClick={()=>setSelectedId(row.id)}>
         <strong>{row.start_at.slice(0,10)!==row.end_at.slice(0,10)?row.start_at.slice(5,10)+' ':''}{row.start_at.slice(11,16)}—{row.end_at.slice(0,10)!==row.start_at.slice(0,10)?row.end_at.slice(5,10)+' ':''}{row.end_at.slice(11,16)}</strong>
         <span>{row.candidate_name} · {row.round}</span><span>{row.job_name}</span>
         <span>面试官：{row.interviewer_name || '未指定'}</span>
         <Tag>{row.application_archived?'原投递已归档':INTERVIEW_STATUS_TEXT[row.status]||row.status}</Tag>
         {conflicts.has(row.id)&&<Tag color="error">时间重叠</Tag>}
        </button>)}
        {visible&&!events.length&&<span className="interview-calendar-no-events">暂无面试</span>}
       </div>
      </section>;
     })}
    </div>
   </div>
   {visible&&!rows.length&&<Empty description="当前日期和筛选条件下暂无面试；未安排时间的候选人请切换列表查看" />}
  </Spin>
  <Drawer title="面试日程详情" width={520} open={selectedId!==null} onClose={()=>setSelectedId(null)}>
   {detailLoading?<p role="status">正在加载面试详情…</p>:detailFailed?<Alert type="error" message="面试详情加载失败"
     action={<Button onClick={()=>void loadDetail()}>重试</Button>} />:detail&&<>
    <Typography.Title level={4}>{detail.candidate_name} · {detail.round}</Typography.Title>
    <Descriptions column={1} bordered size="small" items={[
     {key:'job',label:'职位',children:detail.job_name},
     {key:'time',label:'时间',children:detail.start_at+' 至 '+detail.end_at},
     {key:'interviewer',label:'面试官',children:detail.interviewer_name||'未指定'},
     {key:'type',label:'形式',children:INTERVIEW_TYPE_TEXT[detail.type]||detail.type},
     {key:'status',label:'状态',children:detail.application_archived?'原投递已归档':INTERVIEW_STATUS_TEXT[detail.status]||detail.status},
     {key:'location',label:'地点',children:detail.location||'未填写'},
     {key:'link',label:'会议链接',children:detail.meeting_link||'未填写'},
     {key:'summary',label:'备注',children:detail.summary||detail.remark||'无'},
    ]} />
    <Space wrap style={{marginTop:20}}>
     <Button onClick={()=>onCandidate(detail)}>查看候选人</Button>
     {!detail.application_archived&&canManage&&!['completed','cancelled'].includes(detail.status)&&<>
      <Button onClick={()=>{setSelectedId(null);onEdit(detail);}}>编辑安排</Button>
      <Button onClick={()=>{setSelectedId(null);onReschedule(detail);}}>改期</Button>
     </>}
     {!detail.application_archived&&detail.status!=='cancelled'&&(canManage||userId===detail.interviewer_id)&&
      <Button type="primary" onClick={()=>{setSelectedId(null);onFeedback(detail);}}>查看或提交评价</Button>}
    </Space>
   </>}
  </Drawer>
 </section>;
}
