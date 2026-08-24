# HR ATS 沙箱部署说明

## 项目组成

- 前端：React 18 + TypeScript + Vite 7，开发访问端口 `5173`
- 后端：Flask 3 + PyMongo，API 访问端口 `8100`
- 数据库：MongoDB，默认连接 `mongodb://127.0.0.1:27017`
- 文件：开发环境未配置 OSS 时自动使用后端本地目录

项目不占用 `80`、`8090` 或 `38000` 端口。

## 沙箱启动前提

沙箱需要提供：

1. Python 3.12；
2. Node.js 22 和 npm；
3. MongoDB 7 或可访问的 MongoDB 服务。

如果沙箱已有 MongoDB，直接设置 `MONGODB_URI` 即可；不需要 MySQL、Redis 或其他数据库。

## 推荐启动方式

在项目根目录执行：

```bash
cp .env.sandbox.example .env.sandbox
# 按沙箱实际 MongoDB 地址修改 .env.sandbox

bash scripts/start-backend.sh
bash scripts/start-frontend.sh
```

前端访问：`http://127.0.0.1:5173`

后端健康检查：`http://127.0.0.1:8100/health`

也可以使用一键启动：

```bash
bash scripts/start-all.sh
bash scripts/check-sandbox.sh
bash scripts/stop-all.sh
```

启动脚本会自动创建 Python 虚拟环境并安装后端依赖；前端第一次启动时会根据 `package-lock.json` 执行 `npm ci`。

## 测试登录

沙箱默认开启 Mock 登录，登录页可以使用以下账号：

```text
hr-001
hr-002
screen-001
interviewer-001
org-001
gm-001
chairman-001
offer-001
ssc-001
```

开发环境默认写入演示数据。如果需要空库测试，将 `.env.sandbox` 中的 `HRATS_SEED_DEMO_DATA` 改为 `0`。

## 生产/真实环境注意事项

- 不要把真实 MongoDB 密码、平台凭据或 OSS 密钥写入项目文件；通过环境变量注入。
- `HRATS_ENV=production` 时必须配置真实 MongoDB 和 OSS，Mock 登录会关闭。
- 沙箱展示建议保持 `HRATS_ENV=development`，这样可以使用 Mock 登录和本地文件存储。
