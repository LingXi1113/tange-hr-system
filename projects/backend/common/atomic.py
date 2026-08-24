"""MongoDB 业务操作的一致性边界。

生产环境如果 MongoDB 使用副本集/分片集群，则使用多文档事务；
开发环境的单机 MongoDB 不支持事务时，由业务层的补偿回滚逻辑兜底。
"""
from contextlib import contextmanager
from contextvars import ContextVar

from flask import current_app

from .db import get_db


_active_session = ContextVar("hrats_active_mongo_session", default=None)


def current_session():
    return _active_session.get()


def transactions_supported() -> bool:
    """判断当前 MongoDB 是否支持多文档事务，并缓存结果。"""
    cached = current_app.extensions.get("mongo_transactions_supported")
    if cached is not None:
        return bool(cached)

    try:
        hello = get_db(current_app).client.admin.command("hello")
        # 副本集和 mongos 都支持事务；standalone 不支持。
        supported = bool(hello.get("setName") or hello.get("msg") == "isdbgrid")
    except Exception as exc:
        current_app.logger.warning(
            "无法确认 MongoDB 事务能力，将使用业务补偿回滚: %s", type(exc).__name__
        )
        supported = False
    current_app.extensions["mongo_transactions_supported"] = supported
    return supported


@contextmanager
def business_transaction():
    """创建招聘业务事务；不支持事务时返回 None 供调用方执行补偿回滚。"""
    if not transactions_supported():
        yield None
        return

    client = get_db(current_app).client
    with client.start_session() as session:
        token = _active_session.set(session)
        try:
            with session.start_transaction():
                yield session
        finally:
            _active_session.reset(token)
