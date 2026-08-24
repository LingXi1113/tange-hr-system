"""站内通知服务：幂等生成 + 业务规则扫描（无 Redis/消息队列，惰性触发）。

幂等保证：notifications.dedupe_key 唯一索引，重复插入直接跳过。
触发时机：通知列表/未读数接口被访问时执行规则扫描（generate_due_notifications），
以及关键业务动作后即时生成（新应聘、面试安排、反馈待填写等）。
"""
from datetime import datetime, timedelta

from flask import current_app
from pymongo.errors import DuplicateKeyError

from common.background_failures import record_background_failure, resolve_background_failure
from common.db import col, next_id
from platform_identity import get_identity

# 收件人：全部 HR（第一版业务主角色）
SCENES = (
    "new_candidate",        # 新候选人进入流程
    "interview_remind",     # 面试提醒
    "feedback_pending",     # 反馈待填写
    "offer_expiring",       # Offer 即将过期
    "approval_due",         # Offer 审批即将/已经超期
    "stale_candidate",      # 候选人 7 天未处理
    "requirement_overdue",  # 需求逾期
)

OFFER_EXPIRE_SOON_DAYS = 3
STALE_CANDIDATE_DAYS = 7


def ensure_indexes():
    try:
        col("notifications").create_index("dedupe_key", unique=True)
        col("notifications").create_index([("receiver_id", 1), ("created_at", -1)])
        return True
    except Exception as exc:
        current_app.logger.exception("通知索引初始化失败")
        record_background_failure("notification_index", "notifications", exc)
        if current_app.config.get("ENV_NAME") == "production" and not current_app.config.get("TESTING"):
            raise
        return False


def hr_receivers():
    identity = get_identity(current_app)
    return [u for u in identity.list_users() if u.role == "hr"]


def notify(receiver_id: str, scene: str, title: str, content: str,
           biz_type: str, biz_id, route: str, dedupe_key: str) -> bool:
    """幂等写入一条通知；重复 dedupe_key 返回 False。"""
    ensure_indexes()
    doc = {
        "_id": next_id("notifications"),
        "receiver_id": receiver_id,
        "scene": scene,
        "title": title,
        "content": content,
        "biz_type": biz_type,
        "biz_id": str(biz_id),
        "route": route,
        "dedupe_key": dedupe_key,
        "read_at": None,
        "created_at": datetime.now(),
    }
    try:
        col("notifications").insert_one(doc)
        return True
    except DuplicateKeyError:
        return False


def notify_hr(scene: str, title: str, content: str,
              biz_type: str, biz_id, route: str, dedupe_key: str) -> int:
    """向全部 HR 发送（逐一幂等）。返回新增条数。"""
    count = 0
    for user in hr_receivers():
        if notify(user.user_id, scene, title, content, biz_type, biz_id,
                  route, f"{dedupe_key}::{user.user_id}"):
            count += 1
    return count


def _notify_new_candidate(application_doc: dict):
    candidate = col("candidates").find_one({"_id": application_doc["candidate_id"]}) or {}
    job = col("jobs").find_one({"_id": application_doc["job_id"]}) or {}
    notify_hr(
        "new_candidate", "新候选人进入流程",
        f"候选人「{candidate.get('name', '')}」投递了「{job.get('name', '')}」，请安排筛选",
        "candidate", application_doc["candidate_id"],
        f"/candidates/{application_doc['candidate_id']}",
        f"new_candidate:application:{application_doc['_id']}",
    )


# ---------------- 规则扫描（惰性触发，全部幂等） ----------------

def generate_due_notifications() -> None:
    now = datetime.now()

    # 面试提醒：未来 24 小时内的已确认/待安排面试
    window = col("interviews").find({
        "status": {"$in": ["pending", "invited", "confirmed", "rescheduled"]},
        "start_at": {"$gte": now, "$lte": now + timedelta(days=1)},
    })
    for iv in window:
        candidate = col("candidates").find_one({"_id": iv["candidate_id"]}) or {}
        notify_hr(
            "interview_remind", "面试即将开始",
            f"「{candidate.get('name', '')}」的{iv.get('round', '')}面试将于 "
            f"{iv['start_at']:%Y-%m-%d %H:%M} 开始",
            "interview", iv["_id"], "/interviews",
            f"interview_remind:{iv['_id']}:{iv['start_at']:%Y%m%d%H%M}",
        )

    # 反馈待填写：面试时间已过但仍处于已确认/已改期（未完成、未取消）
    past = col("interviews").find({
        "status": {"$in": ["confirmed", "rescheduled"]},
        "start_at": {"$lt": now},
    })
    for iv in past:
        candidate = col("candidates").find_one({"_id": iv["candidate_id"]}) or {}
        notify_hr(
            "feedback_pending", "面试反馈待填写",
            f"「{candidate.get('name', '')}」的{iv.get('round', '')}面试已结束，请填写面试反馈",
            "interview", iv["_id"], "/interviews",
            f"feedback_pending:{iv['_id']}",
        )

    # Offer 即将过期：已发送且有效期在 3 天内
    soon = col("offers").find({
        "status": "sent",
        "valid_until": {"$gte": now, "$lte": now + timedelta(days=OFFER_EXPIRE_SOON_DAYS)},
    })
    for of in soon:
        candidate = col("candidates").find_one({"_id": of["candidate_id"]}) or {}
        notify_hr(
            "offer_expiring", "Offer 即将过期",
            f"「{candidate.get('name', '')}」的 Offer 将于 {of['valid_until']:%Y-%m-%d} 过期，请跟进响应",
            "offer", of["_id"], "/offers",
            f"offer_expiring:{of['_id']}",
        )

    # Offer 审批期限：提交后 30 天内完成，提前 3 天开始提醒。
    approval_before = now + timedelta(days=3)
    for approval in col("offer_approvals").find({"status": "pending"}):
        deadline = approval.get("deadline_at")
        if not deadline and approval.get("created_at"):
            deadline = approval["created_at"] + timedelta(days=30)
        if not deadline or deadline > approval_before:
            continue
        offer = col("offers").find_one({"_id": approval.get("offer_id")}) or {}
        candidate = col("candidates").find_one({"_id": offer.get("candidate_id")}) or {}
        overdue = deadline < now
        title = "Offer审批已超期" if overdue else "Offer审批即将超期"
        content = (f"候选人「{candidate.get('name', '')}」的 Offer 审批已超过 30 天，请尽快处理"
                   if overdue else
                   f"候选人「{candidate.get('name', '')}」的 Offer 审批将在 {deadline:%Y-%m-%d} 到期，请及时处理")
        notify_hr(
            "approval_due", title, content, "offer_approval", approval["_id"], "/approvals",
            f"approval_due:{approval['_id']}:{deadline:%Y%m%d}",
        )

    # 候选人 7 天未处理：进行中应聘记录阶段停留超过 7 天
    stale_before = now - timedelta(days=STALE_CANDIDATE_DAYS)
    stale = col("applications").find({
        "status": "in_progress",
        "stage_entered_at": {"$lt": stale_before},
    })
    for app in stale:
        candidate = col("candidates").find_one({"_id": app["candidate_id"]}) or {}
        job = col("jobs").find_one({"_id": app["job_id"]}) or {}
        notify_hr(
            "stale_candidate", "候选人长期未跟进",
            f"「{candidate.get('name', '')}」在「{job.get('name', '')}」的阶段已停留超过 "
            f"{STALE_CANDIDATE_DAYS} 天，请跟进处理",
            "candidate", app["candidate_id"], f"/candidates/{app['candidate_id']}",
            f"stale_candidate:application:{app['_id']}:{app.get('current_stage', '')}",
        )

    # 需求逾期：招聘中且期望到岗日期已过
    overdue = col("requirements").find({
        "status": "recruiting",
        "due_date": {"$lt": now},
    })
    for req in overdue:
        notify_hr(
            "requirement_overdue", "招聘需求已逾期",
            f"需求「{req.get('name', '')}」期望到岗日期 {req['due_date']:%Y-%m-%d} 已过，请跟进",
            "requirement", req["_id"], f"/requirements/{req['_id']}",
            f"requirement_overdue:{req['_id']}",
        )
