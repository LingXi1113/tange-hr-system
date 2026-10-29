const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:5183';
(async () => {
 const browser = await chromium.launch({ ...(process.env.TEST_BROWSER_PATH ? {executablePath:process.env.TEST_BROWSER_PATH} : {channel:'chrome'}),headless:true });
 try {
  for(const scenario of ['normal','empty','failure','interviewer']){
   const page=await browser.newPage({viewport:{width:1440,height:1000}});
   page.setDefaultTimeout(10000);
   const errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));
   let fail=scenario==='failure';
   const zero=scenario==='empty';
   const group=(key,items)=>({key,title:key,items});
   const item=(key,count,route)=>({key,label:key,count:zero?0:count,route});
   const summary={generated_at:'2026-10-29 18:00:00',todos:{},todo_items:[],overview:{},funnel:[],recent_activities:[],notification_unread:0,
    workbench_metrics:[
     group('screening',[item('unprocessed',7,'/candidates?unprocessed=1')]),
     group('interview',[item('waiting_schedule',3,'/candidates?action_state=awaiting_interview_schedule'),item('feedback',2,'/interviews?action_state=awaiting_interviewer_feedback')]),
     group('hiring',[item('pending_approval',4,'/approvals?status=pending')])]};
   const reminders=zero?[]:[{id:1,title:'测试到期提醒',content:'请跟进审批',scene:'approval_due',route:'/approvals?status=pending',unread:true,created_at:'2026-10-29 12:00'}];
   await page.route('**/env',r=>r.fulfill({json:{}}));
   await page.route('**/api/**',async r=>{
    const url=new URL(r.request().url()),p=url.pathname;requests.push(url);
    if(fail&&['/api/dashboard/summary','/api/notifications','/api/interviews'].includes(p)){
     await r.fulfill({status:500,json:{code:500,msg:'模拟加载失败'}});return;
    }
    let data=[];
    if(p==='/api/auth/me')data={user_id:'hr-001',name:'Test HR',role:scenario==='interviewer'?'interviewer':'hr',roles:[scenario==='interviewer'?'interviewer':'hr'],switchable_users:[]};
    else if(p==='/api/dashboard/summary')data=summary;
    else if(p==='/api/notifications')data={list:reminders,total:zero?0:5};
    else if(p==='/api/notifications/unread-count')data={count:0};
    else if(['/api/candidates','/api/interviews','/api/interviews/pending-applications','/api/jobs','/api/offers','/api/approvals'].includes(p))data={list:[],total:0};
    await r.fulfill({json:{code:0,msg:'ok',data}});
   });
   await page.goto(base+'/#/workbench');
   await page.getByRole('heading',{name:'招聘工作台',exact:true}).waitFor();
   if(scenario==='interviewer'){
    assert.equal(await page.getByTestId('priority-screen').count(),0);
    await page.getByRole('button',{name:'查看我的任务',exact:true}).waitFor();
   }else if(scenario==='failure'){
    await page.getByText('工作台统计加载失败，请重试',{exact:true}).waitFor();
    assert.equal(await page.getByTestId('priority-screen').isDisabled(),true);
    await page.getByText('到期提醒暂时无法加载',{exact:true}).waitFor();
    fail=false;
    await page.getByRole('button',{name:'刷新工作台',exact:true}).click();
    await page.getByTestId('priority-screen').locator('strong').filter({hasText:'7'}).waitFor();
   }else if(scenario==='empty'){
    assert.equal(await page.getByTestId('priority-screen').locator('strong').innerText(),'0');
    await page.getByText('暂无未读到期提醒',{exact:false}).waitFor();
   }else{
    for(const [key,count] of [['screen','7'],['schedule','3'],['feedback','2'],['approval','4'],['deadline','5']]){
     assert.equal(await page.getByTestId('priority-'+key).locator('strong').innerText(),count);
    }
    assert.equal(await page.locator('details.workbench-overview').getAttribute('open'),null);
    await page.locator('details.workbench-overview > summary').click();
    assert.notEqual(await page.locator('details.workbench-overview').getAttribute('open'),null);
    const routes={screen:'/candidates?unprocessed=1',schedule:'/candidates?action_state=awaiting_interview_schedule',feedback:'/interviews?action_state=awaiting_interviewer_feedback',approval:'/approvals?status=pending',deadline:'/notifications?status=unread&scene_group=deadline'};
    for(const [key,route] of Object.entries(routes)){
     await page.goto(base+'/#/workbench');
     await page.getByTestId('priority-'+key).click();
     await page.waitForURL('**/#'+route);
     assert.equal(page.url().split('#')[1],route);
    }
    assert(requests.some(u=>u.pathname==='/api/notifications'&&u.searchParams.get('scene_group')==='deadline'&&u.searchParams.get('status')==='unread'));
    assert.equal(await page.getByRole('button',{name:'全部已读',exact:true}).isDisabled(),true);
    await page.goto(base+'/#/workbench');
    await page.setViewportSize({width:390,height:844});
    await page.getByTestId('priority-screen').waitFor();
    const columns=await page.locator('.workbench-priority-grid').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length);
    assert(columns<=2);
   }
   assert.deepEqual(errors,[],scenario+' browser errors');
   await page.close();
   console.log('PASS '+scenario);
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
