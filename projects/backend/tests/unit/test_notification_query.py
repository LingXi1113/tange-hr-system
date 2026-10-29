from common.notification_query import DEADLINE_SCENES, notification_query


def test_deadline_filter_keeps_authenticated_receiver_and_unread_scope():
    query = notification_query("hr-current", "unread", "deadline")
    assert query["receiver_id"] == "hr-current"
    assert query["read_at"] is None
    assert set(query["scene"]["$in"]) == set(DEADLINE_SCENES)
    assert set(query["scene"]["$in"]) == {
        "offer_expiring", "approval_due", "requirement_overdue",
        "stage_rule_remind", "stage_rule_due",
    }
    assert "new_candidate" not in query["scene"]["$in"]
    assert "feedback_pending" not in query["scene"]["$in"]


def test_normal_and_unknown_groups_do_not_hide_notifications():
    assert notification_query("hr-current") == {"receiver_id": "hr-current"}
    assert notification_query("hr-current", "all", "unknown") == {"receiver_id": "hr-current"}
    assert notification_query("other-user", "unread") == {
        "receiver_id": "other-user", "read_at": None,
    }


def test_filter_lists_are_independent_between_requests():
    query = notification_query("one", "unread", "deadline")
    query["scene"]["$in"].clear()
    assert notification_query("two", "unread", "deadline")["scene"]["$in"]
