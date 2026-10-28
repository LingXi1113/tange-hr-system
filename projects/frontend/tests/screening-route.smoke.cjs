/* Run against a local dev server with Playwright available on NODE_PATH.
 * All API requests are intercepted; this test never changes real HR data.
 */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    for (const scenario of ['cancel', 'business', 'interview', 'retry', 'review-failure', 'pending', 'reject']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      const page = await context.newPage();
      page.setDefaultTimeout(15000);
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const application = { id: 101, candidate_id: 1, candidate_name: '流程测试', job_id: 1,
        job_name: '测试职位', current_stage: 'pending_screen', status: 'in_progress', version: 7 };
      const result = { id: 1, application_id: 101, candidate_id: 1, job_id: 1, job_name: '测试职位',
        match_mode: 'application', profile_name: '技术', score: 85, decision: 'pass', decision_label: '符合',
        summary: '测试结果', review_status: 'pending', review_decision: '', dimensions: [], matched_items: ['Java'],
        missing_items: [], risk_items: [], rules: { required_skills: [], hard_skills: [], min_work_years: 0 } };
      const candidate = { id: 1, name: '流程测试', phone: '', email: '', source: 'manual', version: 1,
        current_stage: 'pending_screen', education: [], work_experience: [], attachments: [],
        applications: [application], screening_records: [], lock: null, tags: '' };
      const mutations = [];
      const unexpected = [];
      await page.route('**/env', route => route.fulfill({ json: {} }));
      await page.route('**/api/**', async route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        let data = [];
        let code = 0;
        if (request.method() === 'POST') {
          const payload = request.postDataJSON();
          if (path.startsWith('/api/applications/')) mutations.push({ path, payload });
          if (path.endsWith('/screening-review')) {
            if (scenario === 'review-failure') code = 409;
            else {
              result.review_status = 'reviewed';
              result.review_decision = payload.decision;
              application.version++;
            }
            data = result;
          } else if (path.endsWith('/direct-interview') || path.endsWith('/assign-business')) {
            assert.equal(payload.version, application.version, 'Must route with the post-review version');
            const attempts = mutations.filter(item => item.path.endsWith('/direct-interview')).length;
            if (scenario === 'retry' && attempts === 1) code = 409;
            else {
              application.current_stage = path.endsWith('/assign-business') ? 'business_screen' : 'interview_1';
              if (payload.business_screener_id) application.business_screener_id = payload.business_screener_id;
              application.version++;
              candidate.current_stage = application.current_stage;
            }
            data = application;
          } else if (path.startsWith('/api/applications/')) unexpected.push(path);
        } else if (path === '/api/auth/me') {
          data = { user_id: 'hr-001', name: '测试HR', role: 'hr', roles: ['hr'], switchable_users: [] };
        } else if (path === '/api/candidates/1') data = candidate;
        else if (path.endsWith('/screening-result')) data = result;
        else if (path === '/api/platform/users') data = [{ user_id: 'biz-001', name: '测试复筛人员', role: 'business_screener', dept_name: '业务部' }];
        else if (path === '/api/jobs' || path === '/api/interviews' || path === '/api/offers') data = { list: [], total: 0 };
        else if (path.includes('notification')) data = { list: [], total: 0, unread_count: 0 };
        await route.fulfill({ json: { code, msg: code ? '模拟提交失败，请重试' : 'ok', data } });
      });
      await page.goto(`${process.env.TEST_BASE_URL || 'http://127.0.0.1:5173'}/#/candidates/1`);
      const decision = ['pending', 'reject'].includes(scenario) ? scenario : 'pass';
      const buttonName = { pass: 'HR确认通过', pending: '设为待定', reject: '不通过' }[decision];
      await page.getByRole('button', { name: buttonName, exact: true }).click();
      const choice = page.getByRole('dialog', { name: 'HR已确认通过，请选择下一步' });
      if (['pending', 'reject', 'review-failure'].includes(scenario)) {
        await page.waitForTimeout(500);
        assert.equal(await choice.count(), 0);
        assert.equal(application.current_stage, 'pending_screen');
      } else {
        await choice.waitFor();
        assert.equal(application.current_stage, 'pending_screen', 'Approval alone must not move stages');
        await choice.getByRole('button', { name: '推给业务复筛', exact: true }).waitFor();
        if (scenario === 'cancel') {
          await choice.locator('.ant-modal-close').click();
          await choice.waitFor({ state: 'hidden' });
          assert.equal(result.review_decision, 'pass');
          assert.equal(application.current_stage, 'pending_screen');
        } else if (scenario === 'business') {
          await choice.getByRole('button', { name: '推给业务复筛', exact: true }).click();
          const assign = page.getByRole('dialog', { name: '选择业务复筛人员' });
          await assign.waitFor();
          assert.equal(await assign.getByRole('button', { name: '确认推送' }).isDisabled(), true);
          assert.equal(mutations.length, 1, 'Choosing business must not route before a screener is selected');
          await assign.locator('.ant-select-selector').click();
          await page.getByText('测试复筛人员（业务部）', { exact: true }).click();
          await assign.getByRole('button', { name: '确认推送' }).click();
          await assign.waitFor({ state: 'hidden' });
          assert.equal(application.current_stage, 'business_screen');
          assert.equal(application.business_screener_id, 'biz-001');
        } else {
          await choice.getByRole('button', { name: '直接进入面试', exact: true }).click();
          if (scenario === 'retry') {
            await page.getByText('模拟提交失败，请重试', { exact: true }).waitFor();
            assert.equal(await choice.isVisible(), true);
            await choice.getByRole('button', { name: '直接进入面试', exact: true }).click();
          }
          await choice.waitFor({ state: 'hidden' });
          assert.equal(application.current_stage, 'interview_1');
        }
      }
      assert.equal(mutations[0].payload.decision, decision);
      assert.deepEqual(unexpected, []);
      assert.deepEqual(errors, []);
      console.log(`PASS ${scenario}`);
      await context.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
