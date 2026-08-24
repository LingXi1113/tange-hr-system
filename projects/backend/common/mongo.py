"""MongoDB 连接管理。

- 连接串与库名全部来自环境变量 MONGODB_URI / MONGODB_DATABASE；
- 应用启动时建连并 ping 校验；
- **生产环境（HRATS_ENV=production）**：必须显式配置 MONGODB_URI / MONGODB_DATABASE，
  禁止默认连接 127.0.0.1；连接失败直接阻止服务启动（不输出 URI/密码）；
- 开发/测试环境：连接失败仅降级（业务接口返回 5001）；
- 通过 get_collection() 统一获取集合，连接异常包装为 MongoUnavailable。
"""
import logging
import os
from urllib.parse import urlparse

from pymongo import MongoClient
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_MS = 5000
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


class MongoUnavailable(Exception):
    """MongoDB 不可用（未连接或连接中断）。"""


def is_production(app) -> bool:
    return app.config.get("ENV_NAME") == "production"


def validate_production_mongo_env():
    """生产环境 MongoDB 配置校验：返回问题列表（不含任何敏感信息）。"""
    problems = []
    uri = os.environ.get("MONGODB_URI", "").strip()
    database = os.environ.get("MONGODB_DATABASE", "").strip()
    if not uri:
        problems.append("缺少环境变量 MONGODB_URI（生产环境禁止使用默认值）")
    else:
        try:
            host = (urlparse(uri).hostname or "").lower()
        except ValueError:
            host = ""
        if host in _LOCAL_HOSTS:
            problems.append("生产环境 MONGODB_URI 禁止指向本机地址（127.0.0.1/localhost）")
    if not database:
        problems.append("缺少环境变量 MONGODB_DATABASE")
    return problems


def init_mongo(app):
    """应用启动时初始化 MongoDB 连接（幂等）。"""
    uri = app.config["MONGODB_URI"]
    database = app.config["MONGODB_DATABASE"]
    production = is_production(app) and not app.config.get("TESTING")
    if production:
        problems = validate_production_mongo_env()
        if problems:
            # 只报变量名，不输出连接串/密码
            raise RuntimeError("生产环境 MongoDB 配置校验失败：" + "；".join(problems))
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=CONNECT_TIMEOUT_MS)
        client.admin.command("ping")
        app.extensions["mongo_client"] = client
        app.extensions["mongo_db_name"] = database
        logger.info("MongoDB 已连接: db=%s", database)
    except PyMongoError as e:
        app.extensions["mongo_client"] = None
        app.extensions["mongo_db_name"] = database
        if production:
            # 生产环境连接失败：阻止服务启动（错误信息不含 URI/密码）
            raise RuntimeError(
                f"生产环境 MongoDB 连接失败（{type(e).__name__}），阻止服务启动；"
                "请检查 MONGODB_URI 配置") from None
        logger.error("MongoDB 连接失败（业务接口将返回 5001）: %s", type(e).__name__)


def close_mongo(app):
    """关闭连接（进程退出/测试清理时调用）。"""
    client = app.extensions.get("mongo_client")
    if client is not None:
        client.close()
        app.extensions["mongo_client"] = None
        logger.info("MongoDB 连接已关闭")


def get_db(app):
    client = app.extensions.get("mongo_client")
    if client is None:
        raise MongoUnavailable("MongoDB 未连接，文件服务不可用")
    try:
        return client[app.extensions["mongo_db_name"]]
    except PyMongoError as e:
        raise MongoUnavailable(f"MongoDB 访问失败: {e}") from e


def get_collection(app, name: str):
    return get_db(app)[name]


FILES_COLLECTION = "files"
