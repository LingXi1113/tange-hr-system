const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');
(async () => {
 const browser = await chromium.launch({...(process.env.TEST_BROWSER_PATH ? {executablePath:process.env.TEST_BROWSER_PATH} : {channel:'chrome'}),headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  const rows=[1,2].map(id=>({id,name:'Review Candidate '+id,gender:'',phone:'',email:'',city:'',tags:'',source:'manual',owner_name:'HR',current_stage:'pending_screen',created_at:'2026-10-29',version:1,lock:null,latest_application:null,education_summary:{},work_summary:{}}));
  let failSecond=true;
  await page.route('**/env',r=>r.fulfill({json:{}}));
  await page.route('**/api/**',async r=>{
   const p=new URL(r.request().url()).pathname; let data=[];
   if(p==='/api/auth/me')data={user_id:'hr-001',name:'HR',role:'hr',roles:['hr'],switchable_users:[]};
   else if(p==='/api/candidates')data={list:rows,total:2};
   else if(/^\/api\/candidates\/[12]$/.test(p)){
    const id=Number(p.split('/').pop());
    if(id===2&&failSecond){failSecond=false;await r.fulfill({status:500,json:{code:500,msg:'Simulated failure'}});return;}
    data={...rows[id-1],education:[],work_experience:[],attachments:[],applications:[],screening_records:[],talent_pool_entry:null,remark:''};
   } else if(['/api/jobs','/api/interviews','/api/offers'].includes(p)||p.includes('notification'))data={list:[],total:0,unread_count:0};
   await r.fulfill({json:{code:0,msg:'ok',data}});
  });
  const url='http://127.0.0.1:5183/#/candidates?keyword=review&source=manual';
  await page.goto(url);
  await page.getByRole('button',{name:'查看候选人 Review Candidate 1',exact:true}).click();
  const drawer=page.locator('.candidate-review-drawer');
  await drawer.getByRole('heading',{name:'Review Candidate 1',exact:true,level:2}).waitFor();
  assert.equal(await drawer.getByRole('button',{name:'上一位'}).isDisabled(),true);
  assert.equal(page.url(),url);
  await drawer.getByRole('button',{name:'下一位'}).click();
  await drawer.getByText('候选人资料加载失败，请重试或切换下一位').waitFor();
  await drawer.getByRole('button',{name:/重\s*试/}).click();
  await drawer.getByRole('heading',{name:'Review Candidate 2',exact:true,level:2}).waitFor();
  assert.equal(await drawer.getByRole('button',{name:'下一位'}).isDisabled(),true);
  await drawer.getByRole('button',{name:'上一位'}).click();
  await drawer.getByRole('heading',{name:'Review Candidate 1',exact:true,level:2}).waitFor();
  await drawer.getByRole('button',{name:'关闭详情',exact:true}).click();
  await drawer.waitFor({state:'hidden'});
  assert.equal(page.url(),url);
  const row=page.getByRole('button',{name:'查看候选人 Review Candidate 2',exact:true});
  await row.focus();await page.keyboard.press('Enter');
  await page.locator('.candidate-review-drawer').getByRole('heading',{name:'Review Candidate 2',exact:true,level:2}).waitFor();
  assert.deepEqual(errors,[]);
  await page.goto('http://127.0.0.1:5183/#/candidates/1');
  await page.getByRole('heading',{name:'Review Candidate 1',exact:true,level:2}).waitFor();
  await page.getByRole('button',{name:'返回列表',exact:true}).waitFor();
  console.log('PASS: drawer, boundaries, retry, switching, URL preservation, keyboard, standalone route');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
