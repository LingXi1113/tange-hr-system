from datetime import datetime

from flask import Blueprint, current_app

from common.response import ok

bp = Blueprint("health", __name__)


@bp.get("/api/health")
def health():
    return ok({
        "status": "ok",
        "service": "hr-ats-backend",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "platform_provider": current_app.config.get("PLATFORM_PROVIDER", "mock"),
    })
