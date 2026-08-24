"""应用配置。所有外部变量从环境变量读取，不依赖 .env 文件。"""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # 运行环境：development / production。影响 Mock 登录与演示数据的默认开关。
    ENV_NAME = os.environ.get("HRATS_ENV", "development")
    _is_dev = ENV_NAME != "production"

    # 服务端口固定 8100（系统约定，不可更改）
    PORT = int(os.environ.get("HRATS_PORT", "8100"))
    SECRET_KEY = os.environ.get("HRATS_SECRET_KEY", "hrats-dev-secret-key-change-in-prod")

    UPLOAD_DIR = os.environ.get("HRATS_UPLOAD_DIR", os.path.join(BASE_DIR, "data", "uploads"))

    # MongoDB（文件元数据存储）
    MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017")
    MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "hr_ats")

    # 阿里云 OSS（文件对象存储）：凭据一律来自环境变量，禁止写死
    OSS_ACCESSKEY_ID = os.environ.get("OSS_ACCESSKEY_ID", "")
    OSS_ACCESSKEY_SECRET = os.environ.get("OSS_ACCESSKEY_SECRET", "")
    OSS_BUCKET = os.environ.get("OSS_BUCKET", "")
    OSS_PREFIX = os.environ.get("OSS_PREFIX", "hr-ats/")
    # 兼容 OSS_ENDPOINT / OSS_END_POINT 两种命名
    OSS_ENDPOINT = os.environ.get("OSS_ENDPOINT") or os.environ.get("OSS_END_POINT") or ""
    OSS_REGION = os.environ.get("OSS_REGION", "")
    JSON_AS_ASCII = False

    # 平台身份提供方：mock（当前环境）；open_platform 为生产切换点（预留，未实现）
    PLATFORM_PROVIDER = os.environ.get("HRATS_PLATFORM_PROVIDER", "mock")
    # 是否允许 Mock 登录/角色切换接口：开发环境默认开，生产默认关（可显式覆盖）
    ENABLE_MOCK_AUTH = os.environ.get("HRATS_ENABLE_MOCK_AUTH", "1" if _is_dev else "0") == "1"
    # 启动时是否写入演示数据：开发环境默认开，生产默认关
    SEED_DEMO_DATA = os.environ.get("HRATS_SEED_DEMO_DATA", "1" if _is_dev else "0") == "1"
    STAGE_RULE_WORKER_ENABLED = os.environ.get("HRATS_STAGE_RULE_WORKER", "1") == "1"
    STAGE_RULE_WORKER_INTERVAL = max(int(os.environ.get("HRATS_STAGE_RULE_INTERVAL", "60")), 10)


class TestConfig(Config):
    TESTING = True
    SEED_DEMO_DATA = False
    MONGODB_DATABASE = "hr_ats_test"
