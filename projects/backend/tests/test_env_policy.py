"""D7/D8 配置策略：生产环境强制校验 MongoDB/OSS，密钥不落日志。"""
import types

import pytest

from common.mongo import init_mongo, validate_production_mongo_env
from common.storage import LocalStorage, OssStorage, StorageConfigError, create_storage

PROD_URI = "mongodb://appuser:s3cretPW@10.0.0.9:27017/?authSource=admin"


def fake_app(config: dict):
    app = types.SimpleNamespace()
    app.config = config
    app.extensions = {}
    return app


def prod_config(**overrides):
    cfg = {
        "ENV_NAME": "production",
        "MONGODB_URI": PROD_URI,
        "MONGODB_DATABASE": "hr_ats",
        "OSS_ACCESSKEY_ID": "ak-demo",
        "OSS_ACCESSKEY_SECRET": "sk-demo-value",
        "OSS_BUCKET": "demo-bucket",
        "OSS_ENDPOINT": "https://oss-cn-hangzhou.aliyuncs.com",
        "OSS_PREFIX": "hr-ats/",
        "UPLOAD_DIR": "/tmp/hrats-uploads",
    }
    cfg.update(overrides)
    return cfg


# ---------------- MongoDB ----------------

def test_validate_prod_mongo_env_reports_missing_vars(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("MONGODB_DATABASE", raising=False)
    problems = validate_production_mongo_env()
    assert any("MONGODB_URI" in p for p in problems)
    assert any("MONGODB_DATABASE" in p for p in problems)


def test_prod_rejects_localhost_uri(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("MONGODB_DATABASE", "hr_ats")
    problems = validate_production_mongo_env()
    assert any("禁止指向本机" in p for p in problems)

    app = fake_app(prod_config(MONGODB_URI="mongodb://127.0.0.1:27017"))
    with pytest.raises(RuntimeError, match="禁止指向本机"):
        init_mongo(app)


def test_prod_mongo_connect_failure_blocks_startup(monkeypatch):
    uri = "mongodb://appuser:s3cretPW@10.255.255.1:27017/?serverSelectionTimeoutMS=300"
    monkeypatch.setenv("MONGODB_URI", uri)
    monkeypatch.setenv("MONGODB_DATABASE", "hr_ats")
    app = fake_app(prod_config(MONGODB_URI=uri))
    with pytest.raises(RuntimeError) as excinfo:
        init_mongo(app)
    msg = str(excinfo.value)
    assert "连接失败" in msg
    # 错误信息不得泄漏 URI/密码
    assert "s3cretPW" not in msg and "10.255.255.1" not in msg


def test_dev_mongo_failure_degrades_without_leaking_secret(caplog):
    app = fake_app(prod_config(
        ENV_NAME="development",
        MONGODB_URI="mongodb://appuser:s3cretPW@10.255.255.1:27017/?serverSelectionTimeoutMS=300"))
    with caplog.at_level("ERROR"):
        init_mongo(app)  # 开发环境不抛出
    assert app.extensions["mongo_client"] is None
    assert "s3cretPW" not in caplog.text
    assert "10.255.255.1" not in caplog.text


def test_testconfig_skips_prod_gate(app):
    """TESTING 模式不触发生产阻断（测试套件自身可用本地 Mongo）。"""
    with app.app_context():
        from common.mongo import get_db

        assert get_db(app).client is not None


# ---------------- OSS ----------------

def test_prod_storage_requires_all_oss_vars():
    app = fake_app(prod_config(OSS_ACCESSKEY_SECRET=""))
    with pytest.raises(StorageConfigError) as excinfo:
        create_storage(app)
    msg = str(excinfo.value)
    assert "OSS_ACCESSKEY_SECRET" in msg
    assert "禁止降级本地存储" in msg
    # 不得输出已配置的密钥值
    assert "ak-demo" not in msg and "sk-demo-value" not in msg


def test_prod_storage_requires_endpoint_or_region():
    app = fake_app(prod_config(OSS_ENDPOINT="", OSS_REGION=""))
    with pytest.raises(StorageConfigError) as excinfo:
        create_storage(app)
    assert "OSS_END_POINT" in str(excinfo.value)


def test_prod_storage_region_builds_endpoint():
    app = fake_app(prod_config(OSS_ENDPOINT="", OSS_REGION="cn-hangzhou"))
    storage = create_storage(app)
    assert isinstance(storage, OssStorage)


def test_prod_storage_full_config_uses_oss():
    app = fake_app(prod_config())
    storage = create_storage(app)
    assert isinstance(storage, OssStorage)


def test_dev_storage_local_fallback():
    app = fake_app(prod_config(ENV_NAME="development", OSS_ACCESSKEY_ID="",
                               OSS_ACCESSKEY_SECRET="", OSS_BUCKET=""))
    storage = create_storage(app)
    assert isinstance(storage, LocalStorage)
