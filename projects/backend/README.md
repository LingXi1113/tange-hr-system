# HR招聘管理系统 — 后端

Flask + MongoDB（pymongo）后端，端口固定 **8100**，所有业务接口位于 `/api/` 前缀下。
**项目完全使用 MongoDB**：用户/候选人/职位/需求/应聘记录/模板/日志等全部业务数据与
文件元数据统一存 MongoDB；不使用 SQLite/MySQL/PostgreSQL 等任何 SQL 数据库。
文档、简历、图片等文件统一存阿里云 OSS，MongoDB 只存文件元数据。

## 技术栈

- Python 3.12、Flask 3、Flask-Cors、pymongo（MongoDB）、oss2（阿里云 OSS）
- 测试：pytest

## 目录结构

```
backend/
├── run.py                  # 服务入口（supervisor 约定启动方式）
├── app.py                  # Flask 应用工厂（MongoDB 初始化 + 演示数据）
├── config.py               # 配置（全部来自环境变量）
├── seed.py                 # 演示数据初始化（幂等）
├── env.example/.env.example # 环境变量示例（仅占位符）
├── common/
│   ├── db.py               # MongoDB 数据访问层（整数id发号/分页/增删改查）
│   ├── mongo.py            # MongoDB 连接/断开/异常处理
│   ├── storage.py          # 阿里云 OSS / 本地兜底存储层
│   ├── file_service.py     # 文件上传与元数据服务
│   ├── flow.py             # 招聘流程核心（阶段流转/锁定期/乐观锁）
│   ├── logstore.py         # 操作日志（operation_logs）
│   ├── response.py         # 统一响应 {code,msg,data} 与业务错误码
│   ├── errors.py           # BizError 与全局错误处理
│   ├── decorators.py       # login_required / role_required
│   └── roles.py            # 8 类流程参与角色常量
├── platform_identity/      # 平台身份抽象层（接口 + Mock 实现）
├── modules/                # 各业务 API（requirements/jobs/candidates/pipeline/files/…）
└── tests/                  # pytest 测试
```

## 启动方式

生产/容器内由 supervisor 托管（`supervisorctl restart backend`），等价命令：

```bash
cd backend
.venv/bin/python run.py     # 监听 0.0.0.0:8100
```

本地重建虚拟环境：

```bash
cd backend
uv venv .venv
uv pip install -r requirements.txt --python .venv/bin/python
```

## 环境变量

见 `env.example`。关键项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `HRATS_ENV` | development | 运行环境；`production` 时 Mock 登录与演示数据默认关闭 |
| `HRATS_PORT` | 8100 | 服务端口（固定） |
| `HRATS_SECRET_KEY` | dev 默认值 | 会话密钥，生产必须修改 |
| `HRATS_PLATFORM_PROVIDER` | mock | 平台身份提供方；`open_platform` 为即先平台预留切换点 |
| `HRATS_ENABLE_MOCK_AUTH` | dev=1 / prod=0 | Mock 登录/角色切换开关，生产必须为 0 |
| `HRATS_SEED_DEMO_DATA` | dev=1 / prod=0 | 启动时写入演示数据 |

## MongoDB 与阿里云 OSS

- **MongoDB**：全部业务数据（需求/职位/候选人/应聘记录/流转/锁定/模板/字典/参数/日志）
  与文件元数据；连接启动时 ping 校验，异常统一转 JSON 错误（`MongoUnavailable` → code 5001）。
- **阿里云 OSS**：文件（文档/附件/图片/简历）对象存储；凭据全部来自环境变量，禁止写死。

### 环境变量（见 `env.example` / `.env.example`，仅占位符，禁止提交真实密钥）

| 变量 | 说明 |
|---|---|
| `MONGODB_URI` | MongoDB 连接串，默认 `mongodb://127.0.0.1:27017` |
| `MONGODB_DATABASE` | MongoDB 库名，默认 `hr_ats`（测试 `hr_ats_test`） |
| `OSS_ACCESSKEY_ID` / `OSS_ACCESSKEY_SECRET` | OSS 凭据（缺失时自动降级本地存储，仅限开发环境） |
| `OSS_BUCKET` | OSS Bucket 名称 |
| `OSS_PREFIX` | 对象 Key 前缀，如 `hr-ats/` |
| `OSS_ENDPOINT` 或 `OSS_REGION` | 二选一；region 自动拼为 `https://oss-<region>.aliyuncs.com` |

### 生产环境强制校验（PRD v1.1 D7/D8）

当 `HRATS_ENV=production` 时（测试模式除外）：

- 必须显式设置 `MONGODB_URI` 与 `MONGODB_DATABASE`，禁止使用默认值、禁止指向
  `127.0.0.1/localhost`；启动时 ping 校验，连接失败**直接阻止服务启动**；
- 必须完整配置 `OSS_ACCESSKEY_ID`、`OSS_ACCESSKEY_SECRET`、`OSS_BUCKET` 与
  `OSS_END_POINT`/`OSS_ENDPOINT`/`OSS_REGION` 之一，缺失**直接阻止服务启动**，
  禁止静默降级本地存储；
- 所有校验错误与日志只输出变量名与异常类型，不输出连接串、密码或密钥；
- 开发/测试环境保留本地兜底：MongoDB 不可用时业务接口返回 code 5001，
  OSS 凭据缺失时文件存储降级本地模式（启动日志告警）。

部署提示：supervisor 的 backend 启动命令通过 `with-env` 加载 `/etc/environment`，
生产变量由部署平台注入即可，无需修改 supervisor 配置。

### 行为约定

- 对象 Key：`{OSS_PREFIX}{yyyyMMdd}/{uuid}{ext}`，日期+UUID 防冲突；
- 上传校验类型（文档/附件/图片白名单）与大小（≤20MB）；失败自动清理临时文件/已产生的 OSS 对象；
- MongoDB 元数据字段：`originalName`、`objectKey`、`url`、`mimeType`、`size`、`uploadedBy`、`createdAt`；
- 下载/预览不暴露密钥：OSS 返回短时效签名 URL 跳转；本地模式走后端代理；
- 删除文件同时删除 OSS 对象与 MongoDB 元数据；
- MongoDB 启动时连接并 ping 校验；连接失败时业务接口统一返回 code 5001 清晰报错。

### 主要集合

`requirements`、`jobs`、`candidates`、`applications`、`stage_transitions`、`lock_records`、
`attachments`、`pipeline_templates`、`eval_templates`、`sys_params`、`dict_items`、
`offer_approver_config`、`operation_logs`、`export_logs`、`files`、`counters`（整数 id 发号）。
集合 `_id` 为自增整数，保持既有 API 与前端调用完全兼容。

### 文件接口（登录态，统一 `{code,msg,data}` 风格）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/files/upload` | multipart `file` + 可选 `biz_type`；返回元数据 |
| GET | `/api/files?biz_type=&page=&page_size=` | 元数据列表 |
| GET | `/api/files/<id>` | 单条元数据 |
| GET | `/api/files/<id>/download` | 下载/预览（签名 URL 或代理） |
| DELETE | `/api/files/<id>` | 删除对象与元数据（上传者或 HR） |

既有简历上传接口（`/api/resume/upload`、公开页投递附件）已切换到同一存储层，
接口出入参保持兼容（响应新增 `file_id` 字段）。

## 埋点兼容端点

前端内置埋点 SDK 未配置 `TRACKING_ENDPOINT` 时请求同源 `/env`、`/api/v1/events/*` 与 tracking-schema。后端 `modules/tracking_stub.py` 提供静默兼容端点（返回成功、事件丢弃），避免控制台 404 噪音；如后续接入真实埋点服务，为前端注入 `TRACKING_ENDPOINT` 即可绕过。

## 平台身份与角色

当前环境使用 Mock 平台（即先平台 SDK 安装包与凭据缺失），内置 9 个演示用户覆盖 8 类角色。

**登录态机制**：内嵌应用运行在第三方 iframe 中，浏览器会拦截第三方 Cookie，session 不可靠；因此 `mock-login` / `switch-user` 会签发 HMAC 签名 Token（`common/auth_token.py`，SECRET_KEY 签名、7 天有效），前端存入 localStorage 并通过 `X-Auth-Token` 请求头携带；`login_required` 优先校验 Token，兼容 Cookie session。

| user_id | 姓名 | 角色 |
|---|---|---|
| hr-001 / hr-002 | 张薇 / 李娜 | HR（hr-002 另含解锁权限） |
| screen-001 | 王强 | 业务复筛人员 |
| interviewer-001 | 刘洋 | 面试人员 |
| org-001 | 陈静 | 组织统筹审批人 |
| gm-001 | 赵敏 | 总经理 |
| chairman-001 | 孙浩 | 董事长 |
| offer-001 | 周婷 | Offer 发送专人 |
| ssc-001 | 吴迪 | SSC 入职处理人员 |

生产切换：实现 `platform_identity` 包中的 `OpenPlatformIdentityProvider`（基于 jahead-open-platform SDK），在 `get_identity()` 中按 `HRATS_PLATFORM_PROVIDER=open_platform` 返回，业务代码无需改动。

## 测试

```bash
cd backend && .venv/bin/python -m pytest tests -q
```

覆盖：健康检查、登录态校验、Mock 登录/切换/登出、8 类角色齐全、部门树与成员搜索、DB 初始化与模型基类。
