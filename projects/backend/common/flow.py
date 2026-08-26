"""招聘流程核心服务（MongoDB 版）：阶段序列、锁定期、应聘记录创建与流转。

规则：
- 锁定计时：进入阶段开始、离开结束、到期自动释放、强制解锁记日志；
- 锁定期内限制候选人被重复分配到其他职位；
- 阶段流转必须写入 stage_transitions，并用 version 乐观锁防并发。
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from flask import current_app
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from common.status import (
    APP_CLOSED,
    APP_ELIMINATED,
    APP_IN_PROGRESS,
    APP_ONBOARDED,
    APP_PENDING_ONBOARD,
    JOB_RECRUITING,
    REQ_CLOSED,
)
from common.stages import INTERVIEW_ROUNDS, STAGE_RULE_FALLBACK

from .db import col, get_by_id, next_id
from .errors import BizError
from .logstore import write_log
from .response import BizCode
from .consistency import reconcile_application_status
from .background_failures import record_background_failure, resolve_background_failure
from .indexes import ensure_core_indexes


def _now():
    return datetime.now()


# ---------------- 模板与阶段序列 ----------------

def get_job_template(job_doc: dict):
    tpl_col = col("pipeline_templates")
    if job_doc.get("template_id"):
        tpl = tpl_col.find_one({"_id": int(job_doc["template_id"])})
        if tpl:
            return tpl
    return tpl_col.find_one({"status": "active"}, sort=[("_id", 1)])


def job_stage_sequence(job_doc: dict):
    """职位看板列：主干阶段按序 + 启用的可选环节插入 after_key 之后。"""
    tpl = get_job_template(job_doc)
    if tpl is None:
        return []
    stages = [SimpleNamespace(**s) for s in tpl.get("stages", [])]
    main = sorted([s for s in stages if not s.optional_flag], key=lambda s: s.sort_order)
    optional_map = {s.stage_key: s for s in stages if s.optional_flag}
    enabled = {c["stage_key"]: c for c in job_doc.get("stage_configs", []) if c.get("enabled")}
    sequence = []
    for s in main:
        sequence.append(s)
        for key, cfg in enabled.items():
            if cfg.get("after_key") == s.stage_key and key in optional_map:
                sequence.append(optional_map[key])
    return sequence


def stage_lock_days(job_doc: dict, stage_key: str) -> int:
    tpl = get_job_template(job_doc)
    if tpl is None:
        return 0
    for s in tpl.get("stages", []):
        if s["stage_key"] == stage_key:
            return int(s.get("lock_days") or 0)
    return 0


def stage_rule(job_doc: dict, stage_key: str) -> dict:
    """读取阶段规则，并为历史模板补齐新字段。"""
    tpl = get_job_template(job_doc) or {}
    defaults = STAGE_RULE_FALLBACK.get(stage_key, {})
    for stage in tpl.get("stages", []):
        if stage.get("stage_key") == stage_key:
            return {
                **defaults,
                "lock_days": int(stage.get("lock_days", defaults.get("lock_days", 0)) or 0),
                "unprocessed_days": int(stage.get("unprocessed_days", defaults.get("unprocessed_days", 0)) or 0),
                "expiry_action": stage.get("expiry_action", defaults.get("expiry_action", "none")),
                "deadline_basis": stage.get("deadline_basis", defaults.get("deadline_basis", "stage_entered")),
                "reminder_days_before": int(stage.get("reminder_days_before", defaults.get("reminder_days_before", 0)) or 0),
                "skippable": bool(stage.get("skippable", False)),
                "requires_interview": bool(stage.get("requires_interview", defaults.get("requires_interview", False))),
                "requires_feedback": bool(stage.get("requires_feedback", defaults.get("requires_feedback", False))),
                "auto_reminder": bool(stage.get("auto_reminder", bool(stage.get("reminder_type")))),
                "enter_talent_pool": bool(stage.get("enter_talent_pool", defaults.get("enter_talent_pool", False))),
            }
    return {**defaults, "lock_days": 0, "unprocessed_days": 0}


def stage_rules_enabled(job_doc: dict) -> bool:
    tpl = get_job_template(job_doc) or {}
    return bool(tpl.get("stage_rules_enabled", False))


def _interview_rounds_for_stage(stage_key: str):
    return {
        "interview_1": "一面", "interview_2": "二面", "interview_3": "三面",
        "hr_interview": "HR面试", "re_interview": "复试",
    }.get(stage_key)


def configured_interview_rounds(job_doc: dict) -> list[str]:
    """返回职位配置的面试轮次；未配置时返回空，保持旧职位单轮兼容。"""
    raw = job_doc.get("interview_rounds")
    if not isinstance(raw, list):
        return []
    return list(dict.fromkeys(
        str(item).strip() for item in raw
        if str(item).strip() in INTERVIEW_ROUNDS
    ))


def expected_interview_round(application_doc: dict, job_doc: dict) -> str:
    rounds = configured_interview_rounds(job_doc)
    if not rounds:
        return ""
    current = application_doc.get("interview_round", "")
    return current if current in rounds else rounds[0]


def _check_interview_requirements(app_doc: dict, stage_key: str, rule: dict):
    if not (rule.get("requires_interview") or rule.get("requires_feedback")):
        return
    query = {"application_id": app_doc["_id"], "status": "completed"}
    round_name = _interview_rounds_for_stage(stage_key)
    if round_name:
        query["round"] = round_name
    interviews = list(col("interviews").find(query))
    if not interviews:
        raise BizError(BizCode.STATE_INVALID, "该阶段必须先完成对应面试")
    if rule.get("requires_feedback"):
        ids = [item["_id"] for item in interviews]
        feedback = col("interview_feedback").find_one({
            "interview_id": {"$in": ids}, "skip_eval": {"$ne": True},
        })
        if feedback is None:
            raise BizError(BizCode.STATE_INVALID, "该阶段必须先完成面试反馈")


def _validate_stage_transition(app_doc: dict, job_doc: dict, to_stage: str):
    if to_stage in {"eliminated", "abandoned", "talent_pool"}:
        return
    sequence = job_stage_sequence(job_doc)
    index_by_key = {stage.stage_key: index for index, stage in enumerate(sequence)}
    current_stage = app_doc.get("current_stage", "")
    current_index = index_by_key.get(current_stage)
    target_index = index_by_key.get(to_stage)
    if current_index is not None and target_index is not None and target_index <= current_index:
        raise BizError(BizCode.STATE_INVALID, "招聘阶段只能向前推进，不能倒退或重复进入当前阶段")
    if not stage_rules_enabled(job_doc):
        return
    if current_index is None or target_index is None:
        return
    skipped = sequence[current_index + 1:target_index]
    if skipped and any(not stage_rule(job_doc, stage.stage_key).get("skippable", False) for stage in skipped):
        raise BizError(BizCode.STATE_INVALID, "当前招聘阶段不允许跳过中间阶段")
    current_rule = stage_rule(job_doc, current_stage)
    _check_interview_requirements(app_doc, current_stage, current_rule)


# ---------------- 锁定期 ----------------

def release_expired_locks(candidate_id: int = None, session=None):
    """惰性自动释放：到期的锁定标记为已释放。"""
    query = {"released": False, "end_at": {"$lte": _now()}}
    if candidate_id:
        query["candidate_id"] = candidate_id
    col("lock_records").update_many(
        query, {"$set": {"released": True, "auto_released": True}}, session=session,
    )


def active_lock_for_candidate(candidate_id: int, session=None):
    release_expired_locks(candidate_id, session=session)
    return col("lock_records").find_one({
        "candidate_id": candidate_id, "released": False, "end_at": {"$gt": _now()},
    }, session=session)


def start_stage_lock(application_doc: dict, session=None, lock_days_override=None):
    job_doc = get_by_id("jobs", application_doc["job_id"], session=session)
    days = stage_lock_days(job_doc or {}, application_doc["current_stage"])
    if lock_days_override is not None:
        days = int(lock_days_override)
        if days < 0:
            raise ValueError("lock_days_override must be non-negative")
    if days <= 0:
        return None
    now = _now()
    lock = {
        "_id": next_id("lock_records", session=session),
        "application_id": application_doc["_id"],
        "candidate_id": application_doc["candidate_id"],
        "stage_key": application_doc["current_stage"],
        "start_at": now,
        "end_at": now + timedelta(days=days),
        "released": False,
        "auto_released": False,
        "force_unlocked": False,
        "unlock_reason": "",
        "unlock_operator_id": "",
        "unlock_operator_name": "",
        "created_at": now,
    }
    col("lock_records").insert_one(lock, session=session)
    return lock


def release_stage_lock(application_doc: dict, session=None):
    col("lock_records").update_many(
        {"application_id": application_doc["_id"], "released": False},
        [{"$set": {"released": True, "end_at": {"$min": ["$end_at", _now()]}}}],
        session=session,
    )


def lock_info_for_candidate(candidate_id: int):
    lock = active_lock_for_candidate(candidate_id)
    if not lock:
        return None
    return {
        "stage_key": lock["stage_key"],
        "start_at": lock["start_at"].strftime("%Y-%m-%d %H:%M:%S"),
        "end_at": lock["end_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------- 应聘记录 ----------------

def check_job_accepting(job_doc: dict):
    if job_doc.get("status") != JOB_RECRUITING:
        raise BizError(BizCode.STATE_INVALID, "该职位当前不接收投递")
    if job_doc.get("requirement_id"):
        req = get_by_id("requirements", job_doc["requirement_id"])
        if req and req.get("status") == REQ_CLOSED:
            raise BizError(BizCode.STATE_INVALID, "关联招聘需求已关闭，不能新增候选人")


def check_duplicate_application(candidate_id: int, job_id: int, session=None):
    exists = col("applications").find_one({
        "candidate_id": candidate_id, "job_id": job_id, "status": APP_IN_PROGRESS,
    }, session=session)
    if exists:
        raise BizError(BizCode.DUPLICATED, "该候选人已投递此职位，请勿重复投递")


def create_application(candidate_doc: dict, job_doc: dict, source: str,
                       operator_id: str = "", operator_name: str = "",
                       extra: dict = None, session=None,
                       initial_stage: str = "new_resume",
                       initial_lock_days=None,
                       initial_reason: str = "进入流程"):
    """新建应聘记录：校验接收状态、锁定期、重复投递；写入流转记录并开始锁定。"""
    ensure_core_indexes()
    check_job_accepting(job_doc)
    check_duplicate_application(candidate_doc["_id"], job_doc["_id"], session=session)
    lock = active_lock_for_candidate(candidate_doc["_id"], session=session)
    if lock:
        raise BizError(
            BizCode.LOCKED,
            f"候选人处于锁定期（{lock['stage_key']}，至 {lock['end_at']:%Y-%m-%d %H:%M}），暂不能分配其他职位",
        )
    now = _now()
    app_doc = {
        "_id": next_id("applications", session=session),
        "candidate_id": candidate_doc["_id"],
        "job_id": job_doc["_id"],
        "source": source,
        "current_stage": initial_stage,
        "owner_id": operator_id or candidate_doc.get("owner_id", ""),
        "owner_name": operator_name or candidate_doc.get("owner_name", ""),
        "stage_entered_at": now,
        "status": APP_IN_PROGRESS,
        "eliminate_reason": "",
        "expected_salary": "",
        "onboard_time": "",
        "interview_round": configured_interview_rounds(job_doc)[0]
        if configured_interview_rounds(job_doc) else "",
        "version": 1,
        "created_at": now,
    }
    if extra:
        app_doc.update(extra)
    transition_id = next_id("stage_transitions", session=session)
    lock_doc = None
    try:
        col("applications").insert_one(app_doc, session=session)
        col("stage_transitions").insert_one({
        "_id": transition_id,
        "application_id": app_doc["_id"],
        "from_stage": "",
        "to_stage": initial_stage,
        "reason": initial_reason,
        "operator_id": operator_id,
        "operator_name": operator_name,
        "created_at": now,
        }, session=session)
        lock_doc = start_stage_lock(
            app_doc, session=session, lock_days_override=initial_lock_days,
        )
        write_log("application", "create", operator_id, operator_name,
                  biz_id=str(app_doc["_id"]),
                  detail=f"candidate={candidate_doc['_id']} job={job_doc['_id']} source={source}",
                  session=session)
    except DuplicateKeyError as exc:
        if session is None:
            col("applications").delete_one({"_id": app_doc["_id"]})
            col("stage_transitions").delete_one({"_id": transition_id})
            if lock_doc:
                col("lock_records").delete_one({"_id": lock_doc["_id"]})
        if "uq_active_application_candidate_job" in str(exc):
            raise BizError(BizCode.DUPLICATED, "该候选人已投递此职位，请勿重复投递") from exc
        if "uq_active_candidate_lock" in str(exc):
            latest_lock = active_lock_for_candidate(candidate_doc["_id"])
            if latest_lock:
                raise BizError(
                    BizCode.LOCKED,
                    f"候选人处于锁定期（{latest_lock['stage_key']}，至 {latest_lock['end_at']:%Y-%m-%d %H:%M}），暂不能分配其他职位",
                ) from exc
            raise BizError(BizCode.LOCKED, "候选人刚刚被其他职位锁定，请刷新后重试") from exc
        raise
    except Exception:
        if session is None:
            col("applications").delete_one({"_id": app_doc["_id"]})
            col("stage_transitions").delete_one({"_id": transition_id})
            if lock_doc:
                col("lock_records").delete_one({"_id": lock_doc["_id"]})
        raise
    try:
        from common.notifier import _notify_new_candidate

        _notify_new_candidate(app_doc)
    except Exception as exc:
        # 通知属于辅助动作，不能回滚已经创建成功的应聘记录；但必须留痕，后续可重试。
        current_app.logger.exception(
            "新候选人通知发送失败 application_id=%s", app_doc.get("_id"),
        )
        record_background_failure("new_candidate_notification", app_doc.get("_id"), exc)
    else:
        resolve_background_failure("new_candidate_notification", app_doc.get("_id"))
    return app_doc


def advance_interview_round(application_doc: dict, next_round: str,
                            reason: str, operator_id: str,
                            operator_name: str, version: int, session=None):
    """完成当前面试后进入下一轮，并重新计算面试阶段客保锁定期。"""
    if not (reason or "").strip():
        raise BizError(BizCode.PARAM_INVALID, "面试轮次推进必须填写原因")
    app_doc = reconcile_application_status(_refresh(application_doc) or application_doc)
    job_doc = get_by_id("jobs", app_doc["job_id"], session=session) or {}
    rounds = configured_interview_rounds(job_doc)
    if not rounds or next_round not in rounds:
        raise BizError(BizCode.PARAM_INVALID, "该职位未配置目标面试轮次")
    if app_doc.get("status") != APP_IN_PROGRESS:
        raise BizError(BizCode.STATE_INVALID, "应聘记录已结束，不能推进面试轮次")
    if app_doc.get("current_stage") not in {"pending_interview", "interviewing"}:
        raise BizError(BizCode.STATE_INVALID, "当前阶段不允许推进面试轮次")
    if version != app_doc.get("version", 1):
        raise BizError(BizCode.CONFLICT, "应聘记录已被其他人更新，请刷新后重试")
    now = _now()
    from_stage = app_doc.get("current_stage", "")
    before_locks = list(col("lock_records").find({
        "application_id": app_doc["_id"], "released": False,
    }, session=session))
    transition_id = next_id("stage_transitions", session=session)
    lock_doc = None
    updated = col("applications").find_one_and_update(
        {"_id": app_doc["_id"], "version": version, "status": APP_IN_PROGRESS},
        {"$set": {
            "current_stage": "interviewing", "interview_round": next_round,
            "stage_entered_at": now, "updated_at": now,
         }, "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if updated is None:
        raise BizError(BizCode.CONFLICT, "应聘记录已被其他人更新，请刷新后重试")
    try:
        release_stage_lock(updated, session=session)
        col("stage_transitions").insert_one({
            "_id": transition_id, "application_id": updated["_id"],
            "from_stage": from_stage, "to_stage": "interviewing",
            "reason": reason, "operator_id": operator_id,
            "operator_name": operator_name, "interview_round": next_round,
            "created_at": now,
        }, session=session)
        lock_doc = start_stage_lock(updated, session=session)
        write_log("application", "advance_interview_round", operator_id, operator_name,
              biz_id=str(updated["_id"]), detail=f"进入{next_round}；{reason}")
    except Exception:
        if session is None:
            _rollback_application_transition(app_doc, updated, before_locks, transition_id, lock_doc)
        raise
    updated["_workflow_rollback"] = {
        "before_app": app_doc,
        "updated_app": updated,
        "before_locks": before_locks,
        "transition_id": transition_id,
        "new_lock": lock_doc,
    }
    return updated


def _rollback_application_transition(before_app: dict, updated_app: dict,
                                     before_locks: list, transition_id: int,
                                     new_lock: dict = None):
    """回滚 standalone MongoDB 上已经完成的阶段主记录写入。"""
    current = get_by_id("applications", updated_app["_id"])
    if current and current.get("version") == updated_app.get("version"):
        col("applications").replace_one(
            {"_id": updated_app["_id"], "version": updated_app.get("version")},
            before_app,
        )
    col("stage_transitions").delete_one({"_id": transition_id})
    if new_lock:
        col("lock_records").delete_one({"_id": new_lock["_id"]})
    for lock in before_locks:
        col("lock_records").replace_one({"_id": lock["_id"]}, lock, upsert=True)


def rollback_application_operation(updated_app: dict) -> None:
    """回滚一个已经成功返回、但外层关联写入失败的阶段操作。"""
    token = (updated_app or {}).pop("_workflow_rollback", None)
    if token:
        _rollback_application_transition(**token)


def _refresh(app_doc: dict):
    return get_by_id("applications", app_doc["_id"])


def _legacy_move_application(application_doc: dict, to_stage: str, reason: str,
                     operator_id: str, operator_name: str, version: int,
                     bypass_rules: bool = False):
    """阶段流转：乐观锁 + 必填原因 + 流转记录 + 锁定重计。"""
    if not (reason or "").strip():
        raise BizError(BizCode.PARAM_INVALID, "移动阶段必须填写原因")
    app_doc = _refresh(application_doc) or application_doc
    if app_doc.get("status") != APP_IN_PROGRESS:
        raise BizError(BizCode.STATE_INVALID, "该应聘记录已结束，不能流转阶段")
    if to_stage == "pending_onboard" and not col("offers").find_one({
        "application_id": app_doc["_id"], "status": "accepted",
    }):
        raise BizError(BizCode.STATE_INVALID, "只有已接受的 Offer 才能进入待入职")
    if version != app_doc.get("version", 1):
        raise BizError(BizCode.CONFLICT, "应聘记录已被其他人更新，请刷新后重试")
    job_doc = get_by_id("jobs", app_doc["job_id"]) or {}
    valid_keys = {s.stage_key for s in job_stage_sequence(job_doc)}
    valid_keys |= {"eliminated", "abandoned", "talent_pool"}
    if to_stage not in valid_keys:
        raise BizError(BizCode.PARAM_INVALID, f"目标阶段不在该职位流程中: {to_stage}")
    if not bypass_rules:
        _validate_stage_transition(app_doc, job_doc, to_stage)
    terminal_status = {
        "eliminated": APP_ELIMINATED,
        "abandoned": APP_CLOSED,
        "talent_pool": APP_CLOSED,
        "onboarded": APP_ONBOARDED,
    }.get(to_stage, APP_IN_PROGRESS)
    # 乐观锁：仅当 version 一致时更新
    updated = col("applications").find_one_and_update(
        {"_id": app_doc["_id"], "version": version, "status": APP_IN_PROGRESS},
        {"$set": {"current_stage": to_stage, "status": terminal_status,
                   "stage_entered_at": _now(),
                  "version": version + 1, "updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        current = get_by_id("applications", app_doc["_id"])
        if current and current["version"] != version:
            raise BizError(BizCode.CONFLICT, "数据已被其他人更新，请刷新后重试")
        raise BizError(BizCode.CONFLICT, "数据已被其他人更新，请刷新后重试")
    from_stage = app_doc["current_stage"]
    release_stage_lock(updated)
    col("stage_transitions").insert_one({
        "_id": next_id("stage_transitions"),
        "application_id": updated["_id"],
        "from_stage": from_stage,
        "to_stage": to_stage,
        "reason": reason,
        "operator_id": operator_id,
        "operator_name": operator_name,
        "created_at": _now(),
    })
    start_stage_lock(updated)
    write_log("application", f"move_{from_stage}_to_{to_stage}", operator_id, operator_name,
              biz_id=str(updated["_id"]), detail=reason)
    return updated


def _legacy_eliminate_application(application_doc: dict, reason: str,
                          operator_id: str, operator_name: str):
    if not (reason or "").strip():
        raise BizError(BizCode.PARAM_INVALID, "淘汰必须填写原因")
    app_doc = _refresh(application_doc) or application_doc
    if app_doc.get("status") != APP_IN_PROGRESS:
        raise BizError(BizCode.STATE_INVALID, "该应聘记录已结束")
    release_stage_lock(app_doc)
    from_stage = app_doc["current_stage"]
    updated = col("applications").find_one_and_update(
        {"_id": app_doc["_id"]},
        {"$set": {"status": APP_ELIMINATED, "current_stage": "eliminated",
                  "eliminate_reason": reason, "version": app_doc["version"] + 1,
                  "updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    col("stage_transitions").insert_one({
        "_id": next_id("stage_transitions"),
        "application_id": app_doc["_id"],
        "from_stage": from_stage,
        "to_stage": "eliminated",
        "reason": reason,
        "operator_id": operator_id,
        "operator_name": operator_name,
        "created_at": _now(),
    })
    write_log("application", "eliminate", operator_id, operator_name,
              biz_id=str(app_doc["_id"]), detail=reason)
    return updated


def application_to_dict(app_doc: dict) -> dict:
    candidate = get_by_id("candidates", app_doc["candidate_id"]) or {}
    job = get_by_id("jobs", app_doc["job_id"]) or {}
    from common.db import dt

    return {
        "id": app_doc["_id"],
        "candidate_id": app_doc["candidate_id"],
        "candidate_name": candidate.get("name", ""),
        "job_id": app_doc["job_id"],
        "job_name": job.get("name", ""),
        "source": app_doc.get("source", ""),
        "current_stage": app_doc.get("current_stage", ""),
        "interview_round": app_doc.get("interview_round", ""),
        "owner_id": app_doc.get("owner_id", ""),
        "owner_name": app_doc.get("owner_name", ""),
        "stage_entered_at": dt(app_doc.get("stage_entered_at")),
        "status": app_doc.get("status", ""),
        "eliminate_reason": app_doc.get("eliminate_reason", ""),
        "expected_salary": app_doc.get("expected_salary", ""),
        "onboard_time": app_doc.get("onboard_time", ""),
        "version": app_doc.get("version", 1),
        "created_at": dt(app_doc.get("created_at")),
    }


# Consistency-safe implementations.  Kept at the end so older callers keep
# the same public function names while all modules use the stricter behavior.
def move_application(application_doc: dict, to_stage: str, reason: str,
                     operator_id: str, operator_name: str, version: int,
                     bypass_rules: bool = False, session=None):
    if not (reason or "").strip():
        raise BizError(BizCode.PARAM_INVALID, "阶段流转必须填写原因")
    app_doc = _refresh(application_doc) or application_doc
    app_doc = reconcile_application_status(app_doc)
    if app_doc.get("status") not in (APP_IN_PROGRESS, APP_PENDING_ONBOARD):
        raise BizError(BizCode.STATE_INVALID, "应聘记录已结束，不能流转阶段")
    if app_doc.get("status") == APP_PENDING_ONBOARD and to_stage not in {
        "onboarded", "abandoned", "eliminated", "talent_pool",
    }:
        raise BizError(BizCode.STATE_INVALID, "待入职记录只能完成入职或结束流程")
    if to_stage == "onboarded" and app_doc.get("current_stage") != "pending_onboard":
        raise BizError(BizCode.STATE_INVALID, "只有待入职阶段可以进入已入职")

    if version != app_doc.get("version", 1):
        raise BizError(BizCode.CONFLICT, "应聘记录已被其他人更新，请刷新后重试")
    if to_stage == "pending_onboard" and not col("offers").find_one({
        "application_id": app_doc["_id"], "status": "accepted",
    }):
        raise BizError(BizCode.STATE_INVALID, "只有已接受的 Offer 才能进入待入职")
    job_doc = get_by_id("jobs", app_doc["job_id"]) or {}
    valid_keys = {s.stage_key for s in job_stage_sequence(job_doc)}
    valid_keys |= {"eliminated", "abandoned", "talent_pool"}
    if to_stage not in valid_keys:
        raise BizError(BizCode.PARAM_INVALID, f"目标阶段不在该职位流程中: {to_stage}")
    if not bypass_rules:
        _validate_stage_transition(app_doc, job_doc, to_stage)

    terminal_status = {
        "eliminated": APP_ELIMINATED,
        "abandoned": APP_CLOSED,
        "talent_pool": APP_CLOSED,
        "onboarded": APP_ONBOARDED,
        "pending_onboard": APP_PENDING_ONBOARD,
    }.get(to_stage, APP_IN_PROGRESS)
    from_stage = app_doc.get("current_stage", "")
    now = _now()
    before_locks = list(col("lock_records").find({
        "application_id": app_doc["_id"], "released": False,
    }, session=session))
    transition_id = next_id("stage_transitions", session=session)
    lock_doc = None
    updated = col("applications").find_one_and_update(
        {"_id": app_doc["_id"], "version": version, "status": app_doc["status"]},
        {"$set": {"current_stage": to_stage, "status": terminal_status,
                   "stage_entered_at": now, "updated_at": now},
         "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if updated is None:
        raise BizError(BizCode.CONFLICT, "应聘记录已被其他人更新，请刷新后重试")
    try:
        release_stage_lock(updated, session=session)
        col("stage_transitions").insert_one({
            "_id": transition_id,
            "application_id": updated["_id"],
            "from_stage": from_stage,
            "to_stage": to_stage,
            "reason": reason,
            "operator_id": operator_id,
            "operator_name": operator_name,
            "created_at": now,
        }, session=session)
        lock_doc = start_stage_lock(updated, session=session)
        write_log("application", f"move_{from_stage}_to_{to_stage}", operator_id,
                  operator_name, biz_id=str(updated["_id"]), detail=reason,
                  session=session)
    except Exception:
        if session is None:
            _rollback_application_transition(app_doc, updated, before_locks, transition_id, lock_doc)
        raise
    updated["_workflow_rollback"] = {
        "before_app": app_doc,
        "updated_app": updated,
        "before_locks": before_locks,
        "transition_id": transition_id,
        "new_lock": lock_doc,
    }
    return updated


def eliminate_application(application_doc: dict, reason: str,
                          operator_id: str, operator_name: str,
                          version: int = None, session=None):
    if not (reason or "").strip():
        raise BizError(BizCode.PARAM_INVALID, "淘汰必须填写原因")
    app_doc = _refresh(application_doc) or application_doc
    app_doc = reconcile_application_status(app_doc)
    if app_doc.get("status") != APP_IN_PROGRESS:
        raise BizError(BizCode.STATE_INVALID, "当前应聘记录不能淘汰")
    expected_version = app_doc.get("version", 1) if version is None else version
    from_stage = app_doc.get("current_stage", "")
    now = _now()
    before_locks = list(col("lock_records").find({
        "application_id": app_doc["_id"], "released": False,
    }, session=session))
    transition_id = next_id("stage_transitions", session=session)
    updated = col("applications").find_one_and_update(
        {"_id": app_doc["_id"], "version": expected_version,
         "status": APP_IN_PROGRESS},
        {"$set": {"status": APP_ELIMINATED, "current_stage": "eliminated",
                   "eliminate_reason": reason, "updated_at": now},
         "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if updated is None:
        raise BizError(BizCode.CONFLICT, "应聘记录已被其他人更新，请刷新后重试")
    try:
        release_stage_lock(updated, session=session)
        col("stage_transitions").insert_one({
            "_id": transition_id,
            "application_id": updated["_id"],
            "from_stage": from_stage,
            "to_stage": "eliminated",
            "reason": reason,
            "operator_id": operator_id,
            "operator_name": operator_name,
            "created_at": now,
        }, session=session)
        write_log("application", "eliminate", operator_id, operator_name,
                  biz_id=str(updated["_id"]), detail=reason, session=session)
    except Exception:
        if session is None:
            _rollback_application_transition(app_doc, updated, before_locks, transition_id)
        raise
    updated["_workflow_rollback"] = {
        "before_app": app_doc,
        "updated_app": updated,
        "before_locks": before_locks,
        "transition_id": transition_id,
        "new_lock": None,
    }
    return updated
