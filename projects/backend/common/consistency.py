"""Recruitment workflow consistency helpers.

The application stage is the source of truth for the recruitment pipeline.
Related records (interviews, offers and onboarding) must only operate on an
application that is in a compatible state.
"""
from datetime import datetime

from pymongo import ReturnDocument

from common.db import col
from common.errors import BizError
from common.logstore import write_log
from common.response import BizCode
from common.status import (
    APP_CLOSED,
    APP_ELIMINATED,
    APP_IN_PROGRESS,
    APP_ONBOARDED,
    APP_PENDING_ONBOARD,
)


ACTIVE_APPLICATION_STATUSES = (APP_IN_PROGRESS, APP_PENDING_ONBOARD)
TERMINAL_APPLICATION_STAGES = {
    "eliminated": APP_ELIMINATED,
    "abandoned": APP_CLOSED,
    "talent_pool": APP_CLOSED,
    "onboarded": APP_ONBOARDED,
}


def expected_application_status(stage: str) -> str:
    return TERMINAL_APPLICATION_STAGES.get(stage, APP_IN_PROGRESS if stage != "pending_onboard" else APP_PENDING_ONBOARD)


def reconcile_application_status(application: dict, *, operator_id: str = "system",
                                 operator_name: str = "系统") -> dict:
    """Repair the known stage/status mismatch and return the latest document.

    Older records were allowed to enter ``pending_onboard`` while retaining
    ``in_progress``.  Repairing this at the shared boundary prevents every
    downstream module from implementing a different interpretation.
    """
    if not application:
        raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
    expected = expected_application_status(application.get("current_stage", ""))
    if application.get("status") == expected:
        return application
    current_version = int(application.get("version", 1) or 1)
    updated = col("applications").find_one_and_update(
        {"_id": application["_id"], "version": current_version},
        {"$set": {"status": expected, "updated_at": datetime.now()},
         "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        latest = col("applications").find_one({"_id": application["_id"]})
        if latest is None:
            raise BizError(BizCode.NOT_FOUND, "应聘记录不存在")
        return latest
    write_log("application", "status_reconcile", operator_id, operator_name,
              biz_id=str(updated["_id"]),
              detail=f"stage={updated.get('current_stage', '')}; status={expected}")
    return updated


def require_application_active(application: dict, *, allow_pending_onboard: bool = True) -> dict:
    application = reconcile_application_status(application)
    allowed = (APP_IN_PROGRESS, APP_PENDING_ONBOARD) if allow_pending_onboard else (APP_IN_PROGRESS,)
    if application.get("status") not in allowed:
        raise BizError(BizCode.STATE_INVALID, "应聘记录已结束，当前操作不允许执行")
    return application


def require_interview_application(application: dict) -> dict:
    application = reconcile_application_status(application)
    if application.get("status") != APP_IN_PROGRESS:
        raise BizError(BizCode.STATE_INVALID, "只有进行中的应聘记录可以安排面试")
    if application.get("current_stage") in {
        "offer_pending", "pending_onboard", "onboarded",
        "eliminated", "abandoned", "talent_pool",
    }:
        raise BizError(BizCode.STATE_INVALID, "当前招聘阶段不允许再安排面试")
    return application


def require_offer_application(application: dict, action: str = "create") -> dict:
    application = reconcile_application_status(application)
    if application.get("status") != APP_IN_PROGRESS:
        raise BizError(BizCode.STATE_INVALID, "当前应聘记录已结束，不能继续处理 Offer")
    stage = application.get("current_stage", "")
    if action == "accept" and stage != "offer_pending":
        raise BizError(BizCode.STATE_INVALID, "只有处于 Offer 阶段的应聘记录才能接受 Offer")
    if action in {"create", "submit", "send"} and stage not in {"interview_passed", "offer_pending"}:
        raise BizError(BizCode.STATE_INVALID, "当前招聘阶段不允许处理 Offer")
    return application


def require_onboarding_application(application: dict, *, completing: bool = False) -> dict:
    application = reconcile_application_status(application)
    stage = application.get("current_stage", "")
    if completing:
        if stage != "pending_onboard" or application.get("status") != APP_PENDING_ONBOARD:
            if stage == "onboarded" and application.get("status") == APP_ONBOARDED:
                return application
            raise BizError(BizCode.STATE_INVALID, "只有待入职状态的应聘记录可以完成入职")
    elif stage not in {"pending_onboard", "onboarded"}:
        raise BizError(BizCode.STATE_INVALID, "当前应聘阶段没有入职办理")
    return application
