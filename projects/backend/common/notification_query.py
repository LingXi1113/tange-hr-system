"""Shared notification filters. The receiver always comes from authenticated context."""

DEADLINE_SCENES = (
    "offer_expiring", "approval_due", "requirement_overdue",
    "stage_rule_remind", "stage_rule_due",
)


def notification_query(receiver_id, status="", scene_group=""):
    query = {"receiver_id": receiver_id}
    if status == "unread":
        query["read_at"] = None
    if scene_group == "deadline":
        query["scene"] = {"$in": list(DEADLINE_SCENES)}
    return query
