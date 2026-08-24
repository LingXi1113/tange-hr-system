"""招聘阶段规则执行器。

规则配置保存在流程模板中；本模块负责计算未处理期限、执行到期动作，
并提供一个轻量级后台扫描器。所有动作都使用现有的阶段流转和操作日志。
"""
import threading
from datetime import datetime, timedelta

from flask import current_app

from common.background_failures import record_background_failure, resolve_background_failure
from common.db import col, get_by_id, insert_doc
from common.flow import get_job_template, move_application, stage_rule, stage_rules_enabled
from common.logstore import write_log
from common.status import APP_IN_PROGRESS, APP_PENDING_ONBOARD
from common.worker_lease import acquire_lease, new_worker_id, release_lease


def _planned_onboard_date(application_doc: dict):
    offer = col("offers").find_one(
        {"application_id": application_doc["_id"], "status": "accepted"},
        sort=[("_id", -1)],
    )
    return offer.get("onboard_date") if offer else None


def deadline_for_application(application_doc: dict, now=None):
    """返回当前阶段的到期时间；期限为 0 表示没有未处理期限。"""
    job = get_by_id("jobs", application_doc.get("job_id")) or {}
    if not stage_rules_enabled(job):
        return None
    rule = stage_rule(job, application_doc.get("current_stage", ""))
    days = int(rule.get("unprocessed_days") or 0)
    if days <= 0:
        return None
    start = application_doc.get("stage_entered_at")
    if rule.get("deadline_basis") == "planned_onboard_date":
        start = _planned_onboard_date(application_doc) or start
    if not start:
        return None
    return start + timedelta(days=days)


def _add_to_talent_pool(application_doc: dict, reason: str):
    candidate_id = application_doc["candidate_id"]
    try:
        col("talent_pool").create_index("candidate_id", unique=True)
    except Exception as exc:
        current_app.logger.exception(
            "人才库唯一索引创建失败 candidate_id=%s", candidate_id,
        )
        record_background_failure(
            "talent_pool_index", candidate_id, exc,
            {"source": "stage_rule_expire"},
        )
        raise
    if col("talent_pool").find_one({"candidate_id": candidate_id}):
        return
    insert_doc("talent_pool", {
        "candidate_id": candidate_id,
        "category": "",
        "tags": [],
        "source": "elimination_added",
        "reason": reason,
        "recommended_job_id": application_doc.get("job_id"),
        "last_contact_at": None,
        "status": "active",
        "added_by": "system",
    })
    write_log("talent_pool", "add_auto", "system", "系统",
              biz_id=str(candidate_id), detail=reason)


def process_expired_stage_rules(now=None, limit=500):
    """扫描并执行到期规则，返回本次执行数量。"""
    now = now or datetime.now()
    processed = 0
    apps = col("applications").find(
        {"status": {"$in": [APP_IN_PROGRESS, APP_PENDING_ONBOARD]}}
    ).limit(limit)
    for app in apps:
        job = get_by_id("jobs", app.get("job_id")) or {}
        deadline = deadline_for_application(app, now)
        if deadline is None:
            continue
        rule = stage_rule(job, app.get("current_stage", ""))
        reminder_days_before = int(rule.get("reminder_days_before") or 0)
        if deadline and reminder_days_before > 0 and rule.get("auto_reminder") \
                and now <= deadline <= now + timedelta(days=reminder_days_before):
            try:
                from common.notifier import notify_hr

                candidate = get_by_id("candidates", app.get("candidate_id")) or {}
                notify_hr(
                    "stage_rule_remind", "招聘阶段即将到期",
                    f"候选人「{candidate.get('name', '')}」的阶段「{app.get('current_stage', '')}」"
                    f"将在 {deadline:%Y-%m-%d} 到期，请及时处理",
                    "application", app["_id"], "/pipeline",
                    f"stage_rule_remind:{app['_id']}:{app.get('current_stage', '')}:{deadline:%Y%m%d}",
                )
            except Exception as exc:
                current_app.logger.exception(
                    "客保阶段提醒失败 application_id=%s stage=%s",
                    app.get("_id"), app.get("current_stage"),
                )
                record_background_failure(
                    "stage_rule_remind",
                    f"{app.get('_id')}:{app.get('current_stage')}:{deadline:%Y%m%d}",
                    exc,
                    {"application_id": app.get("_id"), "stage": app.get("current_stage")},
                )
            else:
                resolve_background_failure(
                    "stage_rule_remind",
                    f"{app.get('_id')}:{app.get('current_stage')}:{deadline:%Y%m%d}",
                )
        if deadline > now:
            continue
        action = rule.get("expiry_action", "none")
        reason = f"阶段规则到期：{app.get('current_stage', '')} 未处理超过 {rule.get('unprocessed_days', 0)} 天"
        if rule.get("auto_reminder"):
            try:
                from common.notifier import notify_hr

                candidate = get_by_id("candidates", app.get("candidate_id")) or {}
                notify_hr(
                    "stage_rule_due", "招聘阶段规则已到期",
                    f"候选人「{candidate.get('name', '')}」的招聘阶段需要处理：{reason}",
                    "application", app["_id"], "/pipeline",
                    f"stage_rule_due:{app['_id']}:{app.get('current_stage', '')}",
                )
            except Exception as exc:
                current_app.logger.exception(
                    "客保到期提醒失败 application_id=%s stage=%s",
                    app.get("_id"), app.get("current_stage"),
                )
                record_background_failure(
                    "stage_rule_due",
                    f"{app.get('_id')}:{app.get('current_stage')}",
                    exc,
                    {"application_id": app.get("_id"), "stage": app.get("current_stage")},
                )
            else:
                resolve_background_failure(
                    "stage_rule_due",
                    f"{app.get('_id')}:{app.get('current_stage')}",
                )
        if action == "none":
            continue
        try:
            move_application(
                app, action, reason, "system", "系统", app.get("version", 1),
                bypass_rules=True,
            )
            if rule.get("enter_talent_pool") or action == "talent_pool":
                _add_to_talent_pool(app, reason)
            write_log("application", "stage_rule_expire", "system", "系统",
                      biz_id=str(app["_id"]), detail=reason)
            processed += 1
        except Exception as exc:
            # 单个候选人的异常不应阻塞其他到期规则，但必须留痕并在下一轮重试。
            current_app.logger.exception(
                "客保到期自动动作失败 application_id=%s stage=%s action=%s",
                app.get("_id"), app.get("current_stage"), action,
            )
            record_background_failure(
                "stage_rule_expire", app.get("_id"), exc,
                {"stage": app.get("current_stage"), "action": action},
            )
            continue
        else:
            resolve_background_failure("stage_rule_expire", app.get("_id"))
    return processed


def start_stage_rule_worker(app, interval_seconds=60):
    """启动进程内扫描器；生产多进程部署时由部署层保证单实例或加租约。"""
    if app.extensions.get("stage_rule_worker"):
        return
    stop_event = threading.Event()
    owner = new_worker_id("stage-rule-worker")
    lease_name = "stage-rule-worker"

    def worker():
        while not stop_event.wait(interval_seconds):
            lease_acquired = False
            try:
                with app.app_context():
                    lease_acquired = acquire_lease(
                        lease_name, owner, ttl_seconds=max(interval_seconds * 3, 60),
                    )
                    if not lease_acquired:
                        continue
                    process_expired_stage_rules()
                    from common.notifier import generate_due_notifications

                    generate_due_notifications()
            except Exception:
                app.logger.exception("招聘阶段规则扫描失败")
            finally:
                if lease_acquired:
                    with app.app_context():
                        release_lease(lease_name, owner)

    thread = threading.Thread(target=worker, name="stage-rule-worker", daemon=True)
    thread.start()
    app.extensions["stage_rule_worker"] = {"thread": thread, "stop": stop_event}
