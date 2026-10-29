const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_PATH||'playwright');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5183';
(async()=>{
 const browser=await chromium.launch({...(process.env.TEST_BROWSER_PATH?{executablePath:process.env.TEST_BROWSER_PATH}:{channel:'chrome'}),headless:true});
 try{for(const scenario of ['normal','empty','failure','interviewer']){
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(12000);
 const errors=[],queries=[],writes=[];page.on('pageerror',e=>errors.push(e.message));let fail=scenario==='failure';
 const date=new Date().toLocaleDateString('sv-SE');const tomorrow=new Date(Date.now()+86400000).toLocaleDateString('sv-SE');
 const row={candidate_id:1,candidate_name:'日历测试甲',job_id:1,job_name:'测试职位',application_id:101,round:'一面',type:'video',
  start_at:date+' 10:00',end_at:date+' 11:00',status:'confirmed',interviewer_id:'examiner',interviewer_name:'张面试官',version:1,
  location:'线上',summary:'测试备注',meeting_link:'https://example.com',reschedule_history:[],feedback:null,created_at:date,template_id:null};
 const rows=[{...row,id:201},{...row,id:202,candidate_id:2,candidate_name:'日历测试乙',start_at:date+' 10:30',end_at:date+' 11:30'},
 {...row,id:203,candidate_id:3,candidate_name:'跨天面试',interviewer_id:'other',start_at:date+' 23:30',end_at:tomorrow+' 00:30'}];
 let failDetail=true;
 await page.route('**/env',r=>r.fulfill({json:{}}));
 await page.route('**/api/**',async r=>{
  const url=new URL(r.request().url()),p=url.pathname;queries.push(url);
  if(r.request().method()!=='GET'&&!p.startsWith('/api/v1/'))writes.push(p);
  let data=[];
  if(p==='/api/auth/me')data={user_id:scenario==='interviewer'?'examiner':'hr-001',name:'测试用户',role:scenario==='interviewer'?'interviewer':'hr',roles:[scenario==='interviewer'?'interviewer':'hr'],switchable_users:[]};
  else if(p==='/api/interviews'){
   if(fail){await r.fulfill({status:500,json:{code:500,msg:'模拟失败'}});return;}
   data=scenario==='empty'?{list:[],total:0}:{list:url.searchParams.get('page')==='2'?rows.slice(2):rows.slice(0,2),total:3};
  }else if(p==='/api/interviews/201'){
   if(scenario==='normal'&&failDetail){failDetail=false;await r.fulfill({status:500,json:{code:500,msg:'模拟详情失败'}});return;}
   data=rows[0];
  }else if(p==='/api/jobs'||p==='/api/interviews/pending-applications'||p.includes('notification'))data={list:[],total:0};
  await r.fulfill({json:{code:0,msg:'ok',data}});
 });
 await page.goto(base+'/#/interviews?view=calendar');
 await page.getByRole('heading',{name:'面试管理',exact:true}).waitFor();
 if(scenario==='empty'){
  await page.getByText('当前日期和筛选条件下暂无面试；未安排时间的候选人请切换列表查看',{exact:true}).waitFor();
 }else if(scenario==='failure'){
  await page.getByText('日历加载失败或范围过大，请重试或缩小日期及筛选范围',{exact:true}).waitFor();
  fail=false;await page.getByRole('button',{name:/重\s*试/}).click();
  await page.getByTestId('calendar-event-201').waitFor();
 }else{
  await page.getByTestId('calendar-event-201').waitFor();
  assert(queries.some(u=>u.pathname==='/api/interviews'&&u.searchParams.get('page')==='2'));
  await page.getByText('当前结果中有 2 场面试存在时间重叠，请核对候选人及面试官安排',{exact:true}).waitFor();
  const weekday=new Date().getDay();
  assert.equal(await page.getByTestId('calendar-event-203').count(),weekday===0?1:2);
  await page.getByTestId('calendar-event-201').click();
  if(scenario==='normal'){
   await page.getByText('面试详情加载失败',{exact:true}).waitFor();
   await page.getByRole('button',{name:/重\s*试/}).click();
  }
  const drawer=page.getByRole('dialog',{name:'面试日程详情'});
  await drawer.getByRole('heading',{name:'日历测试甲 · 一面'}).waitFor();
  if(scenario==='interviewer'){
   assert.equal(await drawer.getByRole('button',{name:'编辑安排',exact:true}).count(),0);
   await drawer.getByRole('button',{name:'查看或提交评价',exact:true}).waitFor();
  }else{
   await drawer.getByRole('button',{name:/改\s*期/}).click();
   const modal=page.getByRole('dialog',{name:/改期/});await modal.waitFor();
   await modal.getByRole('button',{name:/取\s*消/}).click();
   await modal.waitFor({state:'hidden'});
   await page.getByPlaceholder('面试官',{exact:true}).fill('张');
   await page.getByPlaceholder('面试官',{exact:true}).press('Enter');
   await page.getByText('列表',{exact:true}).click();
   await page.getByRole('heading',{name:'面试记录',exact:true}).waitFor();
   assert(queries.some(u=>u.pathname==='/api/interviews'&&u.searchParams.get('page_size')==='10'&&u.searchParams.get('interviewer')==='张'));
   await page.getByText('日历',{exact:true}).click();
   await page.getByText('日视图',{exact:true}).click();
   await page.getByTestId('calendar-event-201').waitFor();
   assert(queries.some(u=>u.searchParams.get('date_range_mode')==='overlap'&&u.searchParams.get('date_from')===u.searchParams.get('date_to')));
   await page.setViewportSize({width:390,height:844});
   assert.equal(await page.locator('.interview-calendar-grid.is-day').count(),1);
  }
 }
 assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
 await page.close();console.log('PASS '+scenario);
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
