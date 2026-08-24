# jahead-track-frontend-sdk

`jahead-track-frontend-sdk` 是给前端应用接入 Jahead AI Coding 埋点系统的轻量级 TypeScript SDK。SDK 不依赖 React、Vue、axios、Vite 或 Ant Design，接入方只需要在应用入口初始化一次，然后调用 `tracking.track()`、`tracking.pageView()` 或 `tracking.pageLeave()` 上报事件。

## 能力范围

- 建议初始化时传入 `tenantId` 和 `projectId`，后端会按 `tenant_id + project_id` 查找 Schema 和事件目录；即使暂时拿不到这些值，SDK 也不会阻断事件上报。
- SDK 不再从构建环境变量读取埋点环境；未传 `environment` 时会先读 localStorage 缓存，缓存没有再请求同源 `GET /env`。
- `GET /env` 返回 `{ "env_name": "dev" }` 后，SDK 会缓存到 localStorage，并重置当前 init 配置里的 `environment`。
- `GET /env` 不可用、返回非 2xx 或返回值异常时，SDK 会兜底使用 `dev`，并继续执行后续事件上报。
- `endpoint` 表示埋点服务基址，和 `environment` 无关；不传时默认使用 `https://aicoding-event-tracking.tangees.com`。
- 每条事件的 `properties.environment` 和批量请求顶层 `environment` 都会写入当前环境。
- 每条事件都会写入 `tracking_project_id_missing`、`tracking_company_id_missing`、`tracking_user_id_missing` 和 `tracking_missing_fields`，用于排查项目 ID、公司 ID 或用户 ID 缺失导致的归因问题；内嵌应用未传入 `userId` 时会生成本地兜底 `user_id`，避免 UV 等指标因空用户丢失。
- 事件先进入 localStorage 队列，默认累计 100 条再批量上报。
- 队列未达到 100 条时，默认每 2 分钟自动 flush 一次。
- 成功上报后会删除 localStorage 中已发送的队列数据，避免长期增长。
- 浏览器关闭或页面隐藏时会尽量使用 `keepalive` flush 剩余队列。
- 网络失败或服务端返回非 2xx 时，会把本次批次重新写回 localStorage，避免事件直接丢失。
- 支持队列式 `track`，单条即时 `trackImmediately`，以及可选的 `page_view`、`page_leave` 上报。
- 支持通过 `tracking.syncSchema()` 把前端本地维护的埋点 Schema 同步到后端 `tracking-schema` 接口。

## 目录结构

```text
frontend-sdk/
  src/
    environment.ts          环境校验与 endpoint 解析
    index.ts                SDK 统一导出与 tracking 单例
    storage.ts              localStorage 队列封装
    trackingClient.ts       埋点客户端、批量上报与定时 flush
    trackingClient.test.ts  SDK 行为测试
    types.ts                类型声明
    utils.ts                页面与设备信息采集工具
  README.md                 使用说明
  SKILL.md                  AI 使用规范
```

## 推荐接入

在应用入口初始化 SDK。SDK 不直接读取工程环境变量里的埋点环境，接入项目只需要把租户、项目 ID 和项目类型注入成运行时代码可访问的常量，再把最终值传给 `tracking.init()`。

常用环境变量约定：

| 环境变量       | 注入常量           | SDK 参数      | 说明                              |
| -------------- | ------------------ | ------------- | --------------------------------- |
| `PROJECT_ID`   | `__PROJECT_ID__`   | `projectId`   | 租户内项目 ID                     |
| `COMPANY_ID`   | `__COMPANY_ID__`   | `tenantId`    | 租户 ID，对应后端 `tenant_id`     |
| `PROJECT_TYPE` | `__PROJECT_TYPE__` | `projectType` | 项目类型，`embedded` 表示内嵌应用 |

### Vite 配置示例

在 `vite.config.ts` 中从系统环境变量、CI/CD 变量或前端项目启动脚本读取变量，并通过 `define` 注入全局常量；不要依赖本地 `.env*` 文件判断这些配置：

```ts
import { defineConfig } from 'vite';

export default defineConfig(() => {
  const env = process.env;
  const projectId = env.PROJECT_ID || '';
  const companyId = env.COMPANY_ID || '';
  const project_type = env.PROJECT_TYPE || '';

  return {
    envDir: false,
    define: {
      __PROJECT_ID__: JSON.stringify(projectId),
      __COMPANY_ID__: JSON.stringify(companyId),
      __PROJECT_TYPE__: JSON.stringify(project_type),
    },
  };
});
```

如果项目启用了 TypeScript，可以在 `src/env.d.ts` 或同类全局声明文件中声明这些常量：

```ts
declare const __PROJECT_ID__: string;
declare const __COMPANY_ID__: string;
declare const __PROJECT_TYPE__: string;
```

### 初始化示例

```ts
import { tracking } from 'jahead-track-frontend-sdk';

tracking.init({
  projectId: __PROJECT_ID__,
  tenantId: __COMPANY_ID__,
  projectType: __PROJECT_TYPE__,
  // 内嵌应用必须在业务 SSO 登录完成后传入 data.company_user_id，见下方示例。
  autoPageView: true,
});
```

示例中的导入包名请按实际发布包名或项目内接入路径调整。

如果项目需要显式区分用户，也可以在登录后把业务用户 ID 一并传入：

```ts
tracking.init({
  projectId: __PROJECT_ID__,
  tenantId: __COMPANY_ID__,
  projectType: __PROJECT_TYPE__,
  userId: currentUser.id,
});
```

## 用户 ID 解析策略

SDK 会把解析到的用户 ID 写入事件请求顶层 `user_id`。接入时按项目类型处理：

### 内嵌应用

当 `projectType === "embedded"` 时，埋点 `user_id` **必须优先使用业务项目调用 `POST /api/auth/sso/login` 成功后返回的 `data.company_user_id`**。它是公司租户内的用户标识；不要使用 `individual_user_id` 替代它。

SDK **绝不会**调用 `/api/auth/sso/login` 或任何业务认证接口，也不提供认证接口地址配置。接入时必须查找项目已有的 SSO 登录成功、失败处理，在那里把 `data.company_user_id` 传入 `tracking.init({ userId })`；不得为了埋点再新增一次登录请求。

`existingSsoLogin` 代表项目已有的登录调用，SDK 不实现也不调用它。接入项目应按以下方式改造原有登录处理：

```ts
type SsoLoginResult = {
  data?: { company_user_id?: string };
};

const embeddedFallbackUserStorageKey =
  'jahead_tracking_embedded_fallback_user_id';

function getOrCreateEmbeddedFallbackUserId() {
  const cachedUserId = localStorage.getItem(embeddedFallbackUserStorageKey);

  if (cachedUserId) {
    return cachedUserId;
  }

  const userId = crypto.randomUUID();
  localStorage.setItem(embeddedFallbackUserStorageKey, userId);
  return userId;
}

function initEmbeddedTracking(userId: string) {
  tracking.init({
    projectId: __PROJECT_ID__,
    tenantId: __COMPANY_ID__,
    projectType: __PROJECT_TYPE__,
    userId,
  });
}

async function completeExistingSsoLogin() {
  try {
    const result: SsoLoginResult = await existingSsoLogin();
    const companyUserId = result.data?.company_user_id;

    if (!companyUserId) {
      throw new Error('SSO response does not contain company_user_id.');
    }

    initEmbeddedTracking(companyUserId);
  } catch {
    // SSO 失败时仍初始化埋点，使用稳定的本地兜底 ID。
    initEmbeddedTracking(getOrCreateEmbeddedFallbackUserId());
  }
}
```

`POST /api/auth/sso/login` 的成功响应取值路径为 `data.company_user_id`。当 SSO 登录异常、响应缺少该字段或登录态未建立时，业务项目必须使用 `crypto.randomUUID()` 生成并缓存兜底 `user_id` 后传入 SDK。若业务项目意外漏传 `userId`，SDK 也只会本地生成并缓存同类兜底 ID，绝不会补发认证请求。

### 普通匿名应用

当 `projectType !== "embedded"` 且当前用户是匿名用户时，初始化时传入 `anonymousUser: true`。SDK 会优先读取 localStorage 的 `jahead_tracking_anonymous_user_id`；没有缓存时使用 `crypto.randomUUID()` 生成匿名 ID 并写入 localStorage，后续继续复用。

```ts
tracking.init({
  projectId: __PROJECT_ID__,
  tenantId: __COMPANY_ID__,
  projectType: __PROJECT_TYPE__,
  anonymousUser: true,
});
```

### 普通登录应用

当 `projectType !== "embedded"` 且用户已经登录时，用户 ID 由业务系统自己获取，然后传入 SDK。大模型接入时应先查看业务项目已有的登录态、用户 store、全局状态或 `/me` 类接口，不要让 SDK 再生成匿名 ID。

```ts
tracking.init({
  projectId: __PROJECT_ID__,
  tenantId: __COMPANY_ID__,
  projectType: __PROJECT_TYPE__,
  userId: currentUser.id,
});
```

手动上报点击事件：

```ts
await tracking.track('click', {
  target_id: 'btn_create_order',
  target_type: 'button',
  target_name: '创建订单',
});
```

手动上报自定义事件：

```ts
await tracking.track('custom', {
  action_name: 'search_order',
  keyword: 'A001',
});
```

页面离开时可手动上报停留时长：

```ts
await tracking.pageLeave();
```

## 本地埋点 Schema 维护

前端项目第一次新增埋点时，必须同时在项目本地新增一份埋点 Schema，例如 `src/tracking.schema.ts`。之后每次新增、修改、删除埋点，都要同步修改这份 Schema，并更新 `schema_version`。

这份 Schema 是埋点数据的查询契约：后端会用它生成事件目录、识别某个 `tenant_id + project_id` 下有哪些事件、有哪些自定义属性、哪些字段是敏感字段，以及查询和统计时应该如何解释这些数据。如果只写 `tracking.track()`，但没有维护并同步 Schema，后端就无法可靠地知道这个项目有哪些埋点，查询埋点数据时会缺少事件定义。

推荐在业务项目里维护一个独立文件：

```ts
import type { TrackingProjectSchemaInput } from 'jahead-track-frontend-sdk';

export const trackingSchema = {
  project_name: '订单系统',
  schema_version: '1.0.0',
  timezone: 'Asia/Shanghai',
  events: [
    {
      event_key: 'click',
      event_type: 'click',
      event_name: '点击创建订单',
      description: '用户点击创建订单按钮',
      source: 'frontend',
      properties_schema: {
        target_id: {
          type: 'string',
          name: '目标 ID',
          required: true,
          sensitive: false,
        },
        target_name: {
          type: 'string',
          name: '目标名称',
        },
      },
    },
    {
      event_key: 'search_order',
      event_type: 'custom',
      event_name: '搜索订单',
      description: '用户在订单列表执行搜索',
      source: 'frontend',
      properties_schema: {
        keyword: {
          type: 'string',
          name: '搜索关键词',
          sensitive: true,
        },
      },
    },
  ],
} satisfies TrackingProjectSchemaInput;
```

在初始化 SDK 后调用 `tracking.syncSchema()` 同步到后端。业务代码可以在每次应用启动时都调用它；SDK 会先比较本地 Schema 和 localStorage 缓存里的 `schema_version`，只有版本不一致时才请求后端。

```ts
import { tracking } from 'jahead-track-frontend-sdk';
import { trackingSchema } from './tracking.schema';

tracking.init({
  projectId: __PROJECT_ID__,
  tenantId: __COMPANY_ID__,
  schemaVersion: trackingSchema.schema_version,
});

await tracking.syncSchema(trackingSchema);
```

当 `schema_version` 变化时，`tracking.syncSchema()` 会调用：

```http
POST /api/v1/tenants/{tenant_id}/projects/{project_id}/tracking-schema
Content-Type: application/json
```

SDK 会根据 `tracking.init()` 中的 `tenantId` 和 `projectId` 自动拼接 path 参数，并自动补充请求体里的 `tenant_id`、`project_id`，业务代码只需要维护不含租户和项目 ID 的本地 Schema。

同步成功后，SDK 会把本地 Schema 写入 localStorage。默认缓存 key 为：

```text
jahead_tracking_schema:{encodeURIComponent(tenantId)}:{encodeURIComponent(projectId)}
```

下次进入页面再次调用 `tracking.syncSchema(trackingSchema)` 时，如果缓存中的 `schema_version` 和本地 `trackingSchema.schema_version` 一致，SDK 会直接跳过 schemaEndpoint 请求。因此，每次新增、修改、删除埋点时都必须更新本地 Schema，并递增 `schema_version`，否则后端不会收到新的 Schema。

同步请求体示例：

```json
{
  "tenant_id": "tenant_001",
  "project_id": "project_order",
  "project_name": "订单系统",
  "schema_version": "1.0.0",
  "timezone": "Asia/Shanghai",
  "events": [
    {
      "event_key": "click",
      "event_type": "click",
      "event_name": "点击创建订单",
      "description": "用户点击创建订单按钮",
      "source": "frontend",
      "properties_schema": {
        "target_id": {
          "type": "string",
          "name": "目标 ID",
          "required": true,
          "sensitive": false
        }
      }
    }
  ]
}
```

Schema 字段约束：

- `schema_version` 必填；修改埋点定义时建议递增版本。
- `events` 必须非空。
- 每个事件的 `event_key`、`event_type`、`event_name` 必填。
- `event_key` 在同一个项目 Schema 内不能重复。
- `properties_schema.*.type` 只支持 `string`、`number`、`boolean`、`datetime`。
- `schemaVersion` 初始化参数应和本地 `trackingSchema.schema_version` 保持一致。
- `tracking.syncSchema()` 只按 `schema_version` 判断是否需要同步；修改事件定义后没有更新版本号，会被视为无需同步。

## 环境与 endpoint

`environment` 表示埋点数据所属环境，只用于上报字段，不决定请求域名。SDK 初始化后会按下面顺序获取环境：

1. 先读取 localStorage 的 `jahead_tracking_environment`。
2. 如果没有缓存，请求同源 `GET /env`。这个地址默认不跟 `endpoint` 拼接。
3. 接口返回 `{ "env_name": "dev" }`、`{ "env_name": "gray" }` 或 `{ "env_name": "prod" }` 后，SDK 会写入缓存，并重置当前客户端配置里的 `environment`。
4. 如果 `/env` 不可用、返回非 2xx、缺少 `env_name` 或返回了不支持的环境值，SDK 会兜底使用 `dev`，不会阻断 `page_view`、`track` 或批量上报。

当前可选值如下：

| environment | 含义         |
| ----------- | ------------ |
| `dev`       | 开发环境埋点 |
| `gray`      | 灰度环境埋点 |
| `prod`      | 生产环境埋点 |

`endpoint` 表示埋点服务基址。不传时默认使用：

```text
https://aicoding-event-tracking.tangees.com
```

如果 `/env` 不是当前站点同源接口，可以用 `envEndpoint` 覆盖：

```ts
tracking.init({
  projectId: 'project_order',
  tenantId: 'tenant_001',
  envEndpoint: 'https://app.example.com/env',
});
```

如果未来服务域名变化，在初始化时传入新的 `endpoint`：

```ts
tracking.init({
  projectId: 'project_order',
  tenantId: 'tenant_001',
  endpoint: 'https://tracking.example.com',
});
```

SDK 会自动拼接：

- 环境发现：`/env`
- 批量上报：`/api/v1/events/batch`
- 单条即时上报：`/api/v1/events/track`
- Schema 同步：`/api/v1/tenants/{tenant_id}/projects/{project_id}/tracking-schema`

## 批量上报策略

默认配置：

- `batchSize: 100`
- `flushInterval: 120000`
- `storageKey: "jahead_tracking_queue"`
- `envStorageKey: "jahead_tracking_environment"`
- `schemaStorageKey: "jahead_tracking_schema:{tenantId}:{projectId}"`
- `anonymousUserStorageKey: "jahead_tracking_anonymous_user_id"`

事件会先写入 localStorage。达到 `batchSize` 时立即批量上报；未达到阈值时由定时器每 2 分钟上报一次。`batchSize` 最大会被限制为 100，保持和后端 `POST /api/v1/events/batch` 的单次最大数量一致。

批量上报成功后，SDK 会从 localStorage 删除已发送事件。浏览器关闭或页面隐藏时，SDK 会监听 `pagehide` 和 `beforeunload`，尽量用 `keepalive` 发送剩余队列并清理成功发送的数据。

调试时可以降低阈值：

```ts
tracking.init({
  projectId: 'project_order',
  tenantId: 'tenant_001',
  batchSize: 10,
  flushInterval: 30000,
});
```

## 上报协议

SDK 使用批量接口：

```http
POST /api/v1/events/batch
Content-Type: application/json
```

如果需要不经过 localStorage 的单条即时上报，使用：

```http
POST /api/v1/events/track
Content-Type: application/json
```

请求体示例：

```json
{
  "project_id": "project_order",
  "schema_version": "1.0.0",
  "tenant_id": "tenant_001",
  "user_id": "user_001",
  "environment": "dev",
  "events": [
    {
      "event_key": "click",
      "event_time": "2026-06-26T03:00:00.000Z",
      "page_url": "https://example.com/orders",
      "page_path": "/orders",
      "page_title": "订单列表",
      "referrer": "https://example.com/home",
      "device_type": "desktop",
      "os": "Windows",
      "browser": "Chrome",
      "user_agent": "Mozilla/5.0 ...",
      "language": "zh-CN",
      "screen_width": 1440,
      "screen_height": 900,
      "properties": {
        "environment": "dev",
        "target_id": "btn_create_order"
      }
    }
  ]
}
```

## API

### `tracking.init(options)`

初始化全局单例，并启动定时 flush。

常用参数：

| 参数                      | 必填 | 默认值                                        | 说明                                                                           |
| ------------------------- | ---- | --------------------------------------------- | ------------------------------------------------------------------------------ |
| `tenantId`                | 否   | `''`                                          | 租户 ID；缺失时仍会上报事件，并标记 `tracking_company_id_missing`              |
| `projectId`               | 否   | `''`                                          | 租户内项目 ID；缺失时仍会上报事件，并标记 `tracking_project_id_missing`        |
| `projectType`             | 否   | 无                                            | 项目类型，`embedded` 表示内嵌应用                                              |
| `environment`             | 否   | `dev`                                         | 兼容旧接入的初始值；新接入不要从 `ENV_NAME` 注入，SDK 会通过 `/env` 获取并缓存 |
| `schemaVersion`           | 否   | 无                                            | 当前埋点 Schema 版本                                                           |
| `userId`                  | 否   | 无                                            | 用户 ID；内嵌应用必须传业务 SSO 成功返回的 `data.company_user_id`             |
| `anonymousUser`           | 否   | `false`                                       | 普通应用匿名用户开关；为 `true` 时自动生成并缓存匿名 ID                        |
| `endpoint`                | 否   | `https://aicoding-event-tracking.tangees.com` | 埋点服务基址                                                                   |
| `envEndpoint`             | 否   | `/env`                                        | 环境发现接口；默认同源请求，不跟 `endpoint` 拼接                               |
| `autoPageView`            | 否   | `false`                                       | 初始化后自动上报 `page_view`                                                   |
| `autoPageLeave`           | 否   | `false`                                       | 监听页面离开并上报 `page_leave`                                                |
| `batchSize`               | 否   | `100`                                         | 批量阈值，最大 100                                                             |
| `flushInterval`           | 否   | `120000`                                      | 定时 flush 间隔，单位毫秒                                                      |
| `envStorageKey`           | 否   | `jahead_tracking_environment`                 | 环境缓存 localStorage key                                                      |
| `schemaStorageKey`        | 否   | 按 `tenantId + projectId` 生成                | Schema 缓存 localStorage key                                                   |
| `anonymousUserStorageKey` | 否   | `jahead_tracking_anonymous_user_id`           | SDK 自动生成匿名或内嵌缺失 `userId` 兜底 ID 时使用的 localStorage key          |

### `tracking.track(eventKey, properties?, options?)`

写入一条事件。SDK 会自动补充 `event_time`、页面信息、设备信息和 `properties.environment`。

### `tracking.trackImmediately(eventKey, properties?, options?)`

立即通过 `POST /api/v1/events/track` 上报单条事件。该方法不会写入 localStorage，也不会等待批量阈值或定时器。

### `tracking.syncSchema(schema)`

通过 `POST /api/v1/tenants/{tenant_id}/projects/{project_id}/tracking-schema` 同步本地埋点 Schema。SDK 会使用初始化时的 `tenantId`、`projectId` 生成 path，并补充请求体里的 `tenant_id`、`project_id`。同步成功后会缓存本地 Schema；缓存版本和本地版本一致时不会再次请求后端。

### `tracking.pageView(properties?)`

上报 `page_view`。

### `tracking.pageLeave(properties?)`

上报 `page_leave`，并自动附加 `duration_ms`。

### `tracking.flush()`

立即发送 localStorage 中的队列。适合在应用切换路由、用户退出登录或页面关键动作后主动调用。

### `tracking.destroy()`

清理定时器和自动监听页面离开事件。

## 开发与验证

当前 SDK 没有绑定 package.json。可以直接用 TypeScript 做类型检查：

```bash
tsc --target ES2022 --module ESNext --moduleResolution Bundler --lib ES2022,DOM --strict --skipLibCheck --noEmit frontend-sdk/src/index.ts
```

行为测试可编译到临时目录后用 Node 执行：

```bash
tsc --target ES2022 --module CommonJS --moduleResolution Node10 --ignoreDeprecations 6.0 --lib ES2022,DOM --strict --skipLibCheck --outDir frontend-sdk/.tmp-test frontend-sdk/src/trackingClient.test.ts
node frontend-sdk/.tmp-test/trackingClient.test.js
```
