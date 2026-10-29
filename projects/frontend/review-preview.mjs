import { createServer } from 'vite';
const names = ['演示候选人·张晨', '演示候选人·李悦', '演示候选人·王宁'];
const roles = ['后端开发工程师', '产品经理', '数据分析师'];
const rows = names.map((name, i) => ({
  id: i + 1, application_id: 101 + i, name, gender: '', phone: '138****000' + i,
  email: 'demo' + i + '@example.com', city: '广州', age: 25 + i, highest_education: '本科',
  major: ['计算机科学与技术', '信息管理', '统计学'][i],
  tags: ['Java,Spring Boot,项目经验', '需求分析,产品设计', 'Python,SQL,数据分析'][i],
  source: 'manual', owner_id: 'hr-demo', owner_name: '演示HR',
  current_stage: 'pending_screen', created_at: '2026-10-29 10:00:00', version: 1,
  lock: null, latest_application: null,
  education_summary: { school: '演示大学', degree: '本科', major: ['计算机科学与技术', '信息管理', '统计学'][i] },
  work_summary: { company: '示例科技有限公司（虚构）', position: roles[i], start: '2023-07', end: '至今',
    desc: ['负责接口开发、服务性能优化及系统维护。', '负责用户需求分析、原型设计与项目协作。', '负责指标体系建设、SQL 分析与报表开发。'][i] },
}));
const apps = rows.map((r,i)=>({id:101+i,candidate_id:r.id,candidate_name:r.name,job_id:i+1,
 job_name:roles[i],source:'manual',owner_name:'演示HR',current_stage:'pending_screen',
 status:'in_progress',stage_entered_at:'2026-10-29 10:00:00',created_at:'2026-10-29 10:00:00',
 eliminate_reason:'',expected_salary:'',onboard_time:'',version:1}));
const jobs = roles.map((name,i)=>({id:i+1,name,code:'DEMO-'+(i+1),dept_name:'示例部门',
 status:'open',headcount:2,location:'广州',description:'仅用于查看交互效果的虚构职位。',
 qualification:'',skill_tags:'',interview_rounds:['一面'],screening_rules:{
 profile:'tech',profile_name:'技术',required_skills:[],preferred_skills:[],hard_skills:[],
 industry_tags:[],min_education:'本科',min_work_years:0,pass_score:75,pending_score:55,weights:{} }}));
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
   let list=rows;const keyword=url.searchParams.get('keyword');
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
  else if(p.includes('notification'))data={list:[],total:0,unread_count:0};
  else if(p==='/api/interviews'||p==='/api/offers')data={list:[],total:0};
  res.end(JSON.stringify({code:0,msg:'ok',data}));
 });}}]
});
await server.listen();console.log('Review preview: http://127.0.0.1:5183/#/candidates');
