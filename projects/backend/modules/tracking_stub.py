"""埋点 SDK 兼容端点。

前端内置埋点 SDK 在未配置 TRACKING_ENDPOINT 时请求同源 /env、
/api/v1/events/*、tracking-schema。本系统不自建埋点服务，这里提供
静默兼容端点，避免控制台 404 噪音；事件直接丢弃，不落库。
"""
from flask import Blueprint, jsonify

bp = Blueprint("tracking_stub", __name__)


@bp.get("/env")
def env():
    # SDK 约定：env_name ∈ dev/gray/prod
    return jsonify({"env_name": "dev"})


@bp.post("/api/v1/events/batch")
@bp.post("/api/v1/events/track")
def events():
    return jsonify({"code": 0, "msg": "ok", "data": None})


@bp.post("/api/v1/tenants/<tenant_id>/projects/<project_id>/tracking-schema")
def tracking_schema(tenant_id: str, project_id: str):
    return jsonify({"code": 0, "msg": "ok", "data": None})
