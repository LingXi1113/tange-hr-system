# 前端脚手架

这是一个工程化的前端项目模板，技术栈为 Vite 7、TypeScript、React 18.3.1、React Router Hash 路由、Axios、Ant Design 5、@ant-design/icons 5.x 和 Less。

本 README 是初始化项目后的开发手册。后续由 AI 或开发者继续开发时，应优先阅读本文件，再修改代码。

## 技术栈

- Vite 7
- TypeScript
- React 18.3.1
- react-router-dom（HashRouter）
- axios
- Ant Design 5
- @ant-design/icons 5.x
- Less

## AI 后续开发必读

接手本项目后，先按下面顺序理解项目，不要直接重写工程配置：

1. 阅读本 README，确认应用类型、环境变量、免登、埋点和自检规则。
2. 阅读 `src/routes/`、`src/pages/`、`src/layouts/`，确认真实路由和页面入口。
3. 如果涉及埋点开发或 SDK 调整，必须阅读 `src/lib/jahead-track-frontend-sdk/README.md`。
4. 如果发现 `/workspace/projects/.prd_details/preview` 目录存在内容，需要把它作为 UI 稿参考来源，阅读其中的 HTML、JS、CSS、资源和交互代码，尽量还原布局、样式、组件状态、动效和响应式细节。
5. `preview` 目录通常只用于用户预览 UI，不做登录拦截，并且使用 mock 数据；正式项目只能参考它的 UI 呈现和交互表达，登录、权限、接口、数据来源和异常处理必须按真实需求实现。
6. 除非需求明确要求免登录访问，否则受保护页面必须接入真实登录态和路由/接口权限约束，不能因为 UI 预览稿能直接进入系统，就在正式项目里绕过登录或权限。
7. 完成开发后必须执行“开发后自检与 Playwright 页面检查”章节，只用 Playwright 检查真实页面运行情况。

## 常用命令

安装依赖：

```bash
npm i --registry=https://registry.npmmirror.com
```

本地开发启动。服务器或工作区如果提供了自己的前端项目启动脚本，优先使用该脚本；本地兜底可以使用下面的命令：

```bash
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort --clearScreen false --cors
```

开发后自检不需要执行 `npm run typecheck`、`npm run lint` 或 `npm run build`。这些命令不能替代真实浏览器预览，后续功能开发完成后只使用 Playwright 检查页面运行情况。

## 外部环境变量

本模板不提供也不依赖 `.env`、`.env.local`、`.env.example` 或其他本地 `.env*` 文件。项目需要的外部变量统一从系统环境变量、CI/CD 变量或前端项目启动脚本注入。

Vite 配置已通过 `envDir: false` 禁用本地 `.env*` 文件加载，并只读取启动进程的 `process.env`。不要根据本地 `.env*` 文件里的空值判断用户没有配置。

| 变量                   | 用途            | 说明                                                                 |
| ---------------------- | --------------- | -------------------------------------------------------------------- |
| `PROJECT_TYPE`         | 应用类型        | `normal` 外部应用，`embedded` 内嵌应用；未设置或空值按 `normal` 处理 |
| `OPEN_PLATFORM_APP_ID` | 开放平台应用 ID | 内嵌应用必填，用于 Jahead JSSDK 免登                                 |
| `APP_ID`               | 应用 ID         | 可选；内嵌应用未设置时使用 `OPEN_PLATFORM_APP_ID`                    |
| `PROJECT_ID`           | 埋点项目 ID     | 注入为 `__PROJECT_ID__`，对应埋点后端 `project_id`                   |
| `COMPANY_ID`           | 埋点租户 ID     | 注入为 `__COMPANY_ID__`，对应埋点后端 `tenant_id`                    |
| `TRACKING_ENDPOINT`    | 埋点服务基址    | 可选；不要写成 `VITE_TRACKING_ENDPOINT`，未设置时使用 SDK 默认地址   |
| `VITE_API_BASE_URL`    | Axios 基址      | 必须为 `/`，不要配置成完整后端地址                                   |

只有以 `VITE_` 开头的变量才能直接暴露给浏览器端代码。`PROJECT_TYPE`、`OPEN_PLATFORM_APP_ID`、`APP_ID`、`PROJECT_ID`、`COMPANY_ID` 和 `TRACKING_ENDPOINT` 只允许通过 Vite `define` 注入为编译期常量。

Linux/macOS 临时启动示例：

```bash
PROJECT_TYPE=embedded \
OPEN_PLATFORM_APP_ID=your_open_platform_app_id \
PROJECT_ID=your_project_id \
COMPANY_ID=your_company_id \
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort --clearScreen false --cors
```

Windows PowerShell 临时启动示例：

```powershell
$env:PROJECT_TYPE = 'embedded'
$env:OPEN_PLATFORM_APP_ID = 'your_open_platform_app_id'
$env:PROJECT_ID = 'your_project_id'
$env:COMPANY_ID = 'your_company_id'
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort --clearScreen false --cors
```

## 应用启动链路

浏览器入口在 `src/main.tsx`，启动顺序固定为：

```text
prepareApplication() -> initializeTracking(embeddedUserId) -> ReactDOM.createRoot(...).render(...)
```

- `prepareApplication()` 位于 `src/bootstrap/appBootstrap.ts`，负责根据应用类型做启动前置逻辑，并为内嵌应用返回用于埋点的用户 ID。
- `initializeTracking(embeddedUserId)` 位于 `src/tracking/index.ts`，负责初始化埋点 SDK、同步 Schema。
- React 渲染使用 `HashRouter`，项目不使用 `StrictMode`；没有明确需求不要加回 `StrictMode`。

## 应用类型与免登

项目通过 `PROJECT_TYPE` 判断应用类型：

- `normal`：外部应用，默认类型，不注入 Jahead JSSDK，不加载免登分包，不执行 `window.Jahead.requestAuthCode()`。
- `embedded`：内嵌应用，会在入口阶段加载免登预备逻辑。

内嵌应用必须提供 `OPEN_PLATFORM_APP_ID`。`APP_ID` 可选；未设置时模板会使用 `OPEN_PLATFORM_APP_ID` 作为 `APP_ID`。

当 `PROJECT_TYPE=embedded` 时，Vite 的 `transformIndexHtml` 会向 `index.html` 注入：

```html
<script src="https://cdn.jahead.com/jahead-jssdk/v0.1.0/jahead-jssdk.js"></script>
```

随后入口会动态加载 `src/bootstrap/embeddedSso.ts`，调用：

```ts
window.Jahead.requestAuthCode({ appId });
```

获取一次性授权码后，会请求：

```text
POST /api/auth/sso/login
```

用授权码换取应用后端登录态。接口返回的 `token` 会保存到本地，后续 Axios 请求和埋点请求都会通过请求头携带：

```text
X-Auth-Token: <token>
```

`/api/auth/sso/login` 成功响应中的 `data.company_user_id` 是公司租户内的用户 ID。埋点上报的 `user_id` 必须使用该字段，不能使用 `individual_user_id` 替代。

免登开发注意事项：

- `PROJECT_TYPE=normal` 或空值时，不允许引入或执行 Jahead 免登流程。
- 只有 `PROJECT_TYPE=embedded` 时，才允许加载 Jahead JSSDK 和 `embeddedSso` 分包。
- 免登成功时，`src/bootstrap/embeddedSso.ts` 直接提取 `data.company_user_id`，由 `src/main.tsx` 传入 `initializeTracking(embeddedUserId)`，最终写入埋点请求顶层 `user_id`。
- 免登失败、响应缺少 `company_user_id` 或登录态未建立时，`src/bootstrap/embeddedSso.ts` 使用 `crypto.randomUUID()` 生成并缓存 `jahead_tracking_embedded_fallback_user_id`，仍将该值传入埋点初始化。
- `src/lib/jahead-track-frontend-sdk/` 不会调用任何业务认证接口。修改项目时必须在已有 SSO 调用的成功、失败分支传值，不得为了埋点新增第二次登录请求。
- 新增登录拦截、权限判断或路由守卫时，必须按真实业务需求开发，不要照搬 `preview` 目录里的 mock 和无登录逻辑。

## 接口请求与 nginx 转发

- `VITE_API_BASE_URL` 必须保持为 `/`。不要配置成 `http://127.0.0.1:8100` 这类完整后端地址，否则浏览器会直接请求后端并产生跨域问题。
- 生产环境接口转发由 nginx 统一处理，前端不依赖 Vite proxy。
- 开发联调：Vite dev server 已配置代理，将同源 `/api` 与 `/env` 转发到 `http://127.0.0.1:8100`（可用 `HRATS_DEV_PROXY_TARGET` 覆盖目标），因此 `npm run dev` 下可直接联调后端，无需 Playwright 拦截等旁路手段。
- 业务接口路径使用同源路径，例如 `http.get('/api/users')`。
- Axios 实例位于 `src/services/http.ts`，会自动设置 `X-Request-Id`；统一错误处理：`code != 0` 抛出 `BizError` 并经统一消息封装提示，HTTP 401 自动跳转登录页（公开接口除外）。
- 如果本地存在应用后端 token，Axios 会自动设置 `X-Auth-Token: <token>`。
- 业务接口按模块放在 `src/services/` 下，并保持请求和响应类型清晰。
- 全局提示一律使用 `src/utils/message.ts` 的 `msg` 封装（由 `App.tsx` 中 `MessageBinder` 注入 AntD App 上下文实例），不要直接调用 antd 静态 `message`。

## 埋点接入

项目已经集成 Jahead AI Coding 前端埋点 SDK，源码位于：

```text
src/lib/jahead-track-frontend-sdk/
```

不要再次安装 `jahead-track-frontend-sdk`，也不要把它加入 `package.json` 依赖。SDK 文档位于 `src/lib/jahead-track-frontend-sdk/README.md`；有埋点开发或 SDK 调整需求时，必须先读该文档。

### 默认埋点流程

- `src/tracking/index.ts` 在免登预备完成后、React 渲染前初始化埋点。
- `src/tracking.schema.ts` 维护本地埋点 Schema。
- `src/components/TrackingPageViewReporter.tsx` 在应用页面加载完成后只上报一次 `page_view`。
- 页面加载完成后的 `page_view` 上报后会主动 `tracking.flush()`，触发 `/api/v1/events/batch`。
- Hash 路由变化不重复计算 PV；同一次浏览器页面加载只算一次 PV。
- 页面离开时会尝试上报 `page_leave` 并 flush 队列。
- UV 由后端基于 `page_view` 自动去重统计，前端不要新增独立 UV 事件。

### 环境和接口

- SDK 会先读取 localStorage 中的 `jahead_tracking_environment`。
- 没有缓存时请求同源 `GET /env`。
- `/env` 不可用、404、非 2xx、缺少 `env_name` 或返回不支持的环境值时，SDK 会兜底使用 `dev`，并继续执行 `page_view` 和 `/api/v1/events/batch` 上报。
- `TRACKING_ENDPOINT` 是埋点服务基址，未设置时使用 SDK 默认地址 `https://aicoding-event-tracking.tangees.com`。
- `TRACKING_ENDPOINT` 不等于 `/env`，也不要写成 `VITE_TRACKING_ENDPOINT`。

### 缺失字段也必须上报

未配置 `PROJECT_ID`、`COMPANY_ID` 或暂时拿不到 `user_id` 时，也不能跳过埋点初始化和事件上报。SDK 会继续请求 `/api/v1/events/batch`，并在每条事件 `properties` 中写入：

```text
tracking_project_id_missing
tracking_company_id_missing
tracking_user_id_missing
tracking_missing_fields
```

这些字段用于定位是项目 ID 缺失、公司 ID 缺失、免登用户缺失，还是页面代码根本没有触发上报。

### 新增业务埋点

新增、修改或删除埋点事件时，必须同时维护代码和 Schema：

1. 在业务代码中调用 `tracking.track('event_key', properties)`。
2. 在 `src/tracking.schema.ts` 中维护事件定义和属性定义。
3. 修改后递增 `trackingSchema.schema_version`。
4. 应用启动后会调用 `tracking.syncSchema(trackingSchema)`，当 `schema_version` 变化时请求：

```text
POST /api/v1/tenants/{tenant_id}/projects/{project_id}/tracking-schema
```

如果只写 `tracking.track()`，但没有维护并同步 Schema，后端就无法可靠知道该项目有哪些事件和属性。

### 埋点排查

进入页面后如果没有看到 `/api/v1/events/batch`：

1. 确认 `TrackingPageViewReporter` 仍挂载在应用根组件中。
2. 确认当前访问的是 Hash 路由页面，例如 `http://127.0.0.1:5173/#/dashboard`。
3. 确认控制台没有 React runtime error 或入口渲染中断。
4. `/env` 404 不应阻断上报，SDK 会使用 `dev` 兜底。
5. `PROJECT_ID`、`COMPANY_ID` 或 `user_id` 缺失也不应阻断页面加载完成后的 `page_view` 上报，应通过诊断字段体现。
6. 如果是内嵌应用，确认免登失败不会导致 React 根节点白屏。

## 开发后自检与 Playwright 页面检查

完成任何前端代码、路由、样式、依赖、Vite 配置、环境变量或构建脚本修改后，都必须自检。开发后自检不再执行 `npm run typecheck`、`npm run lint` 或 `npm run build`，只使用 Playwright 检查真实页面运行情况。

使用当前前端项目已有的启动脚本启动预览服务。服务器或工作区通常会提供自己的前端项目启动脚本，优先使用该脚本，不要擅自替换成固定命令。不要把启动输出重定向写入项目目录中的日志文件。

Playwright 检查必须使用本次开发或修改出来的真实路由页面，不要固定检查模板默认页面。业务开发后模板默认页面很可能已经被删除。

检查 URL 应从实际项目中获取，例如路由配置、菜单配置、页面入口、用户指定页面或本次新增/修改的页面。使用 HashRouter 时，访问地址应包含对应 hash 路由，例如：

```text
http://127.0.0.1:5173/#/actual-route
```

检查 Playwright 是否可用：

```bash
playwright --version
```

服务器环境里 Playwright 依赖通常已经放在：

```text
/root/.volta/tools/image/packages/playwright/lib/node_modules
```

不要安装 Playwright，不要执行 `npm install playwright`、`npm install -g playwright`、`npx playwright install`、`playwright install chromium`、`playwright install` 或任何下载浏览器/安装依赖的命令。

如果需要单独诊断 Playwright 和 Chromium 是否真的可启动，可以只对单条命令临时设置 `NODE_PATH`，不要 `export NODE_PATH` 到整个 shell：

```bash
NODE_PATH=/root/.volta/tools/image/packages/playwright/lib/node_modules \
node -e "const { chromium } = require('playwright'); chromium.launch({ headless: true, args: ['--no-sandbox'] }).then(async b => { console.log('chromium ok'); await b.close(); })"
```

推荐把要检查的 URL 放到环境变量中，再用 Node 调用环境里已有的 Playwright：

```powershell
$env:FRONTEND_CHECK_URLS = 'http://127.0.0.1:5173/#/dashboard,http://127.0.0.1:5173/#/settings'
node .\scripts\playwright-smoke-check.mjs
```

如果项目没有现成脚本，可以临时创建 `scripts/playwright-smoke-check.mjs` 进行检查；除非团队明确要求保留，否则不要把临时脚本当作业务代码提交：

```js
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

function loadPlaywright() {
  try {
    return require('playwright');
  } catch (_) {
    const voltaRequire = createRequire(
      '/root/.volta/tools/image/packages/playwright/lib/node_modules/playwright/package.json',
    );
    return voltaRequire('playwright');
  }
}

const urls = (process.env.FRONTEND_CHECK_URLS || '')
  .split(',')
  .map((item) => item.trim())
  .filter(Boolean);

if (urls.length === 0) {
  throw new Error('FRONTEND_CHECK_URLS 不能为空，请填写实际路由页面 URL');
}

const { chromium } = loadPlaywright();
const browser = await chromium.launch({
  headless: true,
  args: ['--no-sandbox'],
});
const failures = [];

try {
  for (const url of urls) {
    const page = await browser.newPage();
    const pageErrors = [];

    page.on('pageerror', (error) => pageErrors.push(`pageerror: ${error.message}`));
    page.on('console', (message) => {
      if (message.type() === 'error') {
        pageErrors.push(`console.error: ${message.text()}`);
      }
    });
    page.on('requestfailed', (request) => {
      const failure = request.failure();
      pageErrors.push(`requestfailed: ${request.url()} ${failure?.errorText || ''}`.trim());
    });
    page.on('response', (response) => {
      if (response.status() >= 400) {
        pageErrors.push(`response ${response.status()}: ${response.url()}`);
      }
    });

    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 10000 });
    await page.waitForTimeout(500);

    const rootText = await page
      .locator('#root')
      .innerText({ timeout: 3000 })
      .catch(() => '');
    if (!rootText.trim()) {
      pageErrors.push('#root 为空或没有可见文本');
    }

    if (pageErrors.length > 0) {
      failures.push({ url, errors: pageErrors });
    }

    await page.close();
  }
} finally {
  await browser.close();
}

if (failures.length > 0) {
  console.error(JSON.stringify(failures, null, 2));
  process.exit(1);
}

console.log(`Playwright 页面检查通过，共检查 ${urls.length} 个 URL`);
```

每个页面至少确认：

- 页面不是白屏，`#root` 内有可见内容。
- 关键布局、标题、导航或主要操作按钮可见。
- 浏览器控制台没有 `error`、React runtime error、未处理的 Promise rejection。
- 页面加载期间没有因为接口失败、环境变量缺失或内嵌免登分支导致入口渲染中断。
- `PROJECT_TYPE=normal` 时不执行 `window.Jahead.requestAuthCode()`。
- `PROJECT_TYPE=embedded` 时才允许加载 Jahead JSSDK 和免登分包。
- 如果页面按真实需求需要登录，优先使用真实登录流程或项目认可的测试登录态进入后检查。

如果当前环境无法启动 dev server、无法访问本地端口，或 Playwright/Chromium 不可用，最终交付说明必须明确写出未完成的自检项和原因，不能把未完成的页面预览说成“验证通过”。

## 目录结构

```text
src/
  assets/       应用静态资源
  bootstrap/    应用启动前置逻辑，内嵌应用免登预备逻辑在此按需加载
  config/       项目类型、APP_ID 等编译期配置
  components/   跨页面或跨业务复用的公共组件
  layouts/      应用布局组件
  lib/          项目内置 SDK 源码
  pages/        路由级页面组件
  routes/       路由配置与路由视图组合
  services/     Axios 实例与类型化接口模块
  styles/       全局 Less 样式与 Ant Design 主题配置
  tracking/     埋点初始化与路由上报封装
  types/        全局 TypeScript 类型声明
  App.tsx       应用根组件与 Provider 组合
  main.tsx      浏览器入口文件
  tracking.schema.ts 本地埋点 Schema
```

## 业务路由（与 UI 预览 hash 一致）

| 路由 | 页面 | P0 状态 |
| --- | --- | --- |
| `#/login` | 登录页（Mock 用户选择，免登录） | 已实现 |
| `#/public/job/:token` | 职位公开页（免登录，含简易投递表单） | 已实现（阶段A） |
| `#/workbench` | 工作台（P0：系统状态卡 + 空状态） | 壳已实现，P11 接数据 |
| `#/requirements` `#/requirements/:id` | 招聘需求列表/详情 | 已实现（阶段A） |
| `#/jobs` `#/jobs/:id` | 职位列表/详情 | 已实现（阶段A） |
| `#/candidates` `#/candidates/:id` | 候选人列表/详情 | 已实现（阶段A） |
| `#/pipeline` | 招聘流程看板 | 已实现（阶段A） |
| `#/interviews` | 面试管理 | 占位，P6 |
| `#/approvals` `#/offers` | 录用审批 / Offer 管理 | 占位，P7 |
| `#/onboarding` | 入职资料 | 占位，P8 |
| `#/talent-pool` | 人才库 | 占位，P9 |
| `#/reports` | 招聘报表 | 占位，P10 |
| `#/pipeline-template` `#/eval-template` `#/settings` | 系统设置组 | 已实现（P1） |
| `#/notifications` `#/tasks` | 站内通知 / 我的任务 | 占位，P11 |

路由守卫：除 `#/login` 与 `#/public/*` 外，全部路由由 `RequireAuth` 校验登录态，未登录重定向到 `#/login`。登录后默认首页：HR → `#/workbench`，其他角色 → `#/tasks`。

## 登录态与角色切换器

- 登录态由 `src/services/user.ts` 维护（`useCurrentUser` Hook），入口 `main.tsx` 渲染前先请求 `/api/auth/me`。
- **Token 鉴权**：内嵌 iframe 场景第三方 Cookie 会被浏览器拦截，登录/切换用户返回的 `token` 存入 localStorage（`authToken.ts`），由 `http.ts` 自动附加 `X-Auth-Token` 请求头；退出时清除。
- 当前环境为 Mock 平台登录：登录页调用 `/api/auth/mock-users` 列出演示用户，`POST /api/auth/mock-login` 建立会话。生产接入即先平台免登后由 embedded SSO 链路替代。
- 统一错误处理在 `src/services/http.ts`：`code != 0` 抛 `BizError` 并提示；HTTP 401 自动跳登录页（公开接口除外）。
- 角色切换器（`src/components/RoleSwitcher.tsx`）：仅开发环境渲染（`import.meta.env.DEV` 为编译期常量，生产构建自动移除）；可用 `VITE_ENABLE_ROLE_SWITCHER=false` 在开发环境强制关闭。切换调用 `POST /api/auth/switch-user`，后端以 `HRATS_ENABLE_MOCK_AUTH=0` 可整体禁用。
- 视觉 token 对齐 `.prd_details/preview/assets/styles.css`：深色顶栏 `#17191B`（52px）、白色侧边栏、页面底 `#F7F8FC`、金橙强调色 `#CD9324`。

## 开发规范

- Vite 保持 7.x，并使用兼容 Vite 7 的 React 插件。
- Vite 配置需要保留 `envDir: false`、`server.allowedHosts: true` 和 `server.hmr.path: '/vite-hmr'`，不要在业务开发中误删。
- React 和 React DOM 固定为 `18.3.1`，除非需求明确要求变更。
- Ant Design 和 `@ant-design/icons` 保持 5.x。
- 项目使用 Hash 路由，入口文件中使用 `HashRouter`，页面访问路径形如 `http://127.0.0.1:5173/#/workbench`。
- 公共组件统一放在 `src/components/`。
- 仅当前页面使用的组件先保留在页面相关目录中，出现复用需求后再提升为公共组件。
- React 组件使用 PascalCase 命名，组件 props 与公共 API 必须提供 TypeScript 类型。
- 默认使用 Less 编写样式。全局样式放在 `src/styles/`，组件私有样式可与组件文件就近存放。
- 路由级页面放在 `src/pages/`，路由组合与跳转配置放在 `src/routes/`。
- HTTP 基础能力放在 `src/services/http.ts`，业务接口按模块放在 `src/services/`。
- 埋点初始化放在 `src/tracking/`，本地埋点 Schema 放在 `src/tracking.schema.ts`。
- 项目内部导入优先使用 `@/` 别名，避免过长的相对路径。
- 外部变量统一来自系统环境变量、CI/CD 变量或前端项目启动脚本，不维护 `.env` / `.env.example`。
- 不要新增 Vite proxy 配置，API 转发由 nginx 负责。
- 不要把开发服务器输出写入项目目录中的 `*.log` 文件。
- 修改目录结构、新增 `src/` 一级公共目录、调整免登、埋点或环境变量规则时，必须同步更新本 README。

## 交付说明要求

AI 完成开发后，最终回复需要简要列出：

- 使用的前端项目启动脚本或启动方式。
- Playwright 已检查的真实路由 URL。
- 是否发现控制台错误、接口错误或白屏。
- 如果有跳过项，说明跳过原因和剩余风险。
