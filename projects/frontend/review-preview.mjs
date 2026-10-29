import { createServer } from 'vite';
const names = ['演示候选人·张晨', '演示候选人·李悦', '演示候选人·王宁'];
const roles = ['后端开发工程师', '产品经理', '数据分析师'];
const rows = names.map((name, i) => ({
  id: i + 1, application_id: 101 + i, name, gender: '', phone: '138****000' + i,
  email: 'demo' + i + '@example.com', city: '广州', age: 25 + i, highest_education: '本科',
  major: ['计算机科学与技术', '信息管理', '统计学'][i],
  tags: ['Java,Spring Boot,项目经验', '需求分析,产品设计', 'Python,SQL,数据分析'][i],
  source: 'manual', owner_id: 'hr-demo', owner_name: '演示HR',
  current_stage: i ? 'interview_1' : 'pending_screen', created_at: '2026-10-29 10:00:00', version: 1,
  lock: null, latest_application: null,
  education_summary: { school: '演示大学', degree: '本科', major: ['计算机科学与技术', '信息管理', '统计学'][i] },
  work_summary: { company: '示例科技有限公司（虚构）', position: roles[i], start: '2023-07', end: '至今',
    desc: ['负责接口开发、服务性能优化及系统维护。', '负责用户需求分析、原型设计与项目协作。', '负责指标体系建设、SQL 分析与报表开发。'][i] },
}));
const apps = rows.map((r,i)=>({id:101+i,candidate_id:r.id,candidate_name:r.name,job_id:i+1,
 job_name:roles[i],source:'manual',owner_name:'演示HR',current_stage:i ? 'interview_1' : 'pending_screen',
 status:'in_progress',stage_entered_at:'2026-10-29 10:00:00',created_at:'2026-10-29 10:00:00',
 eliminate_reason:'',expected_salary:'',onboard_time:'',version:1}));
const jobs = roles.map((name,i)=>({id:i+1,name,code:'DEMO-'+(i+1),dept_name:'示例部门',
 status:'open',headcount:2,location:'广州',description:'仅用于查看交互效果的虚构职位。',
 qualification:'',skill_tags:'',interview_rounds:['一面'],screening_rules:{
 profile:'tech',profile_name:'技术',required_skills:[],preferred_skills:[],hard_skills:[],
 industry_tags:[],min_education:'本科',min_work_years:0,pass_score:75,pending_score:55,weights:{} }}));
const generated = () => new Date().toLocaleString('sv-SE');
const day = new Date().toLocaleDateString('sv-SE');
const notices = [
 {id:1,scene:'offer_expiring',title:'演示：Offer 即将到期',content:'虚构候选人的 Offer 将在 3 天内到期，请跟进意向。',route:'/offers?status=sent',created_at:generated(),unread:true},
 {id:2,scene:'approval_due',title:'演示：审批即将到期',content:'请联系当前审批节点负责人，确认处理进度。',route:'/approvals?status=pending',created_at:generated(),unread:true},
];
const interviewRows = [{id:201,candidate_id:3,candidate_name:rows[2].name,job_id:3,job_name:roles[2],application_id:103,
 round:'一面',type:'video',start_at:day+' 14:00',end_at:day+' 15:00',status:'confirmed',
 interviewer_id:'demo-interviewer',interviewer_name:'演示面试官',created_by:'hr-demo',version:1}];
interviewRows[0] = {...interviewRows[0],location:'线上面试',meeting_link:'https://example.com/demo-meeting',
 interviewer_contact:'演示联系方式',summary:'虚构日程，用于查看日历交互。',reschedule_history:[],feedback:null,template_id:null};
const nextDay = new Date(Date.now()+86400000).toLocaleDateString('sv-SE');
interviewRows.push(
 {...interviewRows[0],id:202,candidate_id:2,candidate_name:rows[1].name,job_id:2,application_id:102,job_name:roles[1],
 start_at:day+' 14:30',end_at:day+' 15:30',summary:'演示历史排期重叠，请在真实环境核查。'},
 {...interviewRows[0],id:203,candidate_id:1,candidate_name:rows[0].name,job_id:1,application_id:101,job_name:roles[0],
 interviewer_id:'demo-interviewer-2',interviewer_name:'演示面试官乙',start_at:nextDay+' 10:00',end_at:nextDay+' 11:00'},
 {...interviewRows[0],id:204,candidate_id:2,candidate_name:rows[1].name,
 interviewer_id:'demo-interviewer-3',interviewer_name:'演示面试官丙',start_at:day+' 23:30',end_at:nextDay+' 00:30'}
);
const workbenchSummary = () => ({
 todos:{},todo_items:[],overview:{},funnel:[],notification_unread:2,recent_activities:[],generated_at:generated(),
 workbench_metrics:[
  {key:'screening',title:'简历初筛',items:[{key:'unprocessed',label:'未处理',count:1,route:'/candidates?unprocessed=1'},
   {key:'referral',label:'内推简历',count:0,route:'/candidates?source=referral'},
   {key:'recommended',label:'人才推荐',count:0,route:'/candidates?source_group=talent_recommendation'},
   {key:'unassigned',label:'待分配',count:0,route:'/candidates?unassigned=1'}]},
  {key:'recommendation',title:'简历推荐',items:[{key:'pending_feedback',label:'推荐待反馈',count:0,route:'/candidates?recommendation_status=pending'}]},
  {key:'interview',title:'面试',items:[{key:'waiting_schedule',label:'待约面',count:1,route:'/candidates?action_state=awaiting_interview_schedule'},
   {key:'feedback',label:'面试待反馈',count:0,route:'/interviews?action_state=awaiting_interviewer_feedback'}]},
  {key:'hiring',title:'录用',items:[{key:'pending_approval',label:'待审批 Offer',count:0,route:'/approvals?status=pending'},
   {key:'pending_send',label:'待发 Offer',count:0,route:'/offers?status=pending_send&ready_to_send=1'},
   {key:'pending_onboard',label:'待入职',count:0,route:'/onboarding?application_stage=pending_onboard'}]},
 ]});
const banner = '<div style="position:fixed;bottom:12px;left:50%;transform:translateX(-50%);z-index:9999;background:#fffbe6;border:1px solid #ffe58f;border-radius:8px;padding:9px 20px;box-shadow:0 3px 14px #0002;font:14px sans-serif;pointer-events:none">交互演示 · 全部为虚构数据 · 修改不会保存</div>';
const server = await createServer({
 server:{host:'127.0.0.1',port:5183,strictPort:true},
 plugins:[{name:'candidate-review-demo',transformIndexHtml(html){return html.replace('</body>',banner+'</body>');},
 configureServer(server){server.middlewares.use((req,res,next)=>{
  const url=new URL(req.url,'http://127.0.0.1');
  if(url.pathname==='/env'){res.setHeader('Content-Type','application/json');res.end('{}');return;}
  if(!url.pathname.startsWith('/api/'))return next();
  res.setHeader('Content-Type','application/json; charset=utf-8');
  if(req.method!=='GET'){res.end(JSON.stringify({code:1006,msg:'当前为只读交互演示，操作不会保存',data:null}));return;}
  const p=url.pathname;let data=[];
  if(p==='/api/auth/me')data={user_id:'hr-demo',name:'演示HR',role:'hr',role_name:'HR',roles:['hr'],
    dept_name:'演示环境',switchable_users:[],mock_mode:true};
  else if(p==='/api/candidates'){
   let list=rows;
   if(url.searchParams.get('unprocessed')==='1')list=list.filter(r=>r.current_stage==='pending_screen');
   if(url.searchParams.get('action_state')==='awaiting_interview_schedule')list=list.filter(r=>r.id===2);
   const keyword=url.searchParams.get('keyword');
   if(keyword)list=list.filter(r=>(r.name+r.tags+r.major).includes(keyword));
   data={list,total:list.length};
  } else if(/^\/api\/candidates\/[123]$/.test(p)){
   const i=Number(p.split('/').pop())-1;const row=rows[i];
   data={...row,education:[{...row.education_summary,graduate_at:'2023-06'}],
    work_experience:[row.work_summary],remark:'用于展示候选人连续审阅，不代表真实求职者。',
    applications:[apps[i]],attachments:[],screening_records:[],talent_pool_entry:null};
  } else if(p.endsWith('/delivery-analysis')){
   const i=Number(p.split('/')[3])-1;data={candidate_id:rows[i]?.id,applications:[],activities:[],summary:{total_deliveries:1,highest_stage:'简历初筛',recommendations:0,passed_recommendations:0,recommendation_pass_rate:0,interviews:0,passed_interviews:0,interview_pass_rate:0}};
  } else if(p.endsWith('/screening-result'))data=null;
  else if(p==='/api/jobs')data={list:jobs,total:jobs.length};
  else if(p==='/api/screening/profiles')data=[];
  else if(p==='/api/dashboard/summary')data=workbenchSummary();
  else if(p==='/api/notifications/unread-count')data={count:notices.length};
  else if(p==='/api/notifications')data={list:notices.slice(0,Number(url.searchParams.get('page_size'))||10),total:notices.length};
  else if(p==='/api/interviews'){
   const from=url.searchParams.get('date_from'),to=url.searchParams.get('date_to');
   const items=url.searchParams.get('action_state')==='awaiting_interviewer_feedback'?[]:interviewRows.filter(r=>{
    const overlap=url.searchParams.get('date_range_mode')==='overlap';
    const range=overlap?(!from||r.end_at>from+' 00:00')&&(!to||r.start_at.slice(0,10)<=to):
      (!from||r.start_at.slice(0,10)>=from)&&(!to||r.start_at.slice(0,10)<=to);
    return range&&(!url.searchParams.get('status')||r.status===url.searchParams.get('status'))
     &&(!url.searchParams.get('round')||r.round===url.searchParams.get('round'))
     &&(!url.searchParams.get('job_id')||r.job_id===Number(url.searchParams.get('job_id')))
     &&(!url.searchParams.get('interviewer')||r.interviewer_name.includes(url.searchParams.get('interviewer')));
   });
   const page=Number(url.searchParams.get('page'))||1,size=Number(url.searchParams.get('page_size'))||10;
   data={list:items.slice((page-1)*size,page*size),total:items.length};
  }
  else if(/^\/api\/interviews\/\d+$/.test(p))data=interviewRows.find(r=>r.id===Number(p.split('/').pop()));
  else if(p==='/api/interviews/pending-applications')data={list:[],total:0};
  else if(p==='/api/platform/users')data=[
    {user_id:'demo-interviewer',name:'演示面试官',role:'interviewer',role_name:'面试官'},
    {user_id:'demo-interviewer-2',name:'演示面试官乙',role:'interviewer',role_name:'面试官'}];
  else if(p.includes('eval-template'))data={list:[],total:0};
  else if(/^\/api\/candidates\/[123]\/applications$/.test(p))data=apps.filter(r=>r.candidate_id===Number(p.split('/')[3]));
  else if(p==='/api/approvals')data={list:[],total:0};
  else if(p==='/api/interviews'||p==='/api/offers')data={list:[],total:0};
  res.end(JSON.stringify({code:0,msg:'ok',data}));
 });}}]
});
await server.listen();console.log('Review preview: http://127.0.0.1:5183/#/candidates');
