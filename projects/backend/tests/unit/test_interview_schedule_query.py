from datetime import datetime, timedelta

from common.interview_schedule_query import conflict_query, calendar_range_query


def matches(row, query):
    for key, value in query.items():
        if key == "$or":
            if not any(matches(row, item) for item in value):
                return False
        elif isinstance(value, dict):
            for op, expected in value.items():
                actual = row.get(key)
                if op == "$lt" and not actual < expected:
                    return False
                if op == "$gt" and not actual > expected:
                    return False
                if op == "$ne" and actual == expected:
                    return False
                if op == "$in" and actual not in expected:
                    return False
        elif row.get(key) != value:
            return False
    return True


START = datetime(2026, 10, 29, 10)
END = START + timedelta(hours=1)


def row(**changes):
    return {"_id": 1, "candidate_id": 10, "interviewer_id": "examiner",
            "status": "confirmed", "start_at": START, "end_at": END, **changes}


def test_different_candidates_cannot_share_interviewer_time():
    query = conflict_query(99, START, END, interviewer_id="examiner")
    assert matches(row(), query)
    assert not matches(row(interviewer_id="other"), query)
    assert matches(row(candidate_id=99, interviewer_id="other"), query)


def test_adjacent_cancelled_completed_and_self_do_not_conflict():
    query = conflict_query(10, START, END, exclude_id=1, interviewer_id="examiner")
    assert not matches(row(), query)
    assert not matches(row(_id=2, start_at=END, end_at=END+timedelta(hours=1)), query)
    assert not matches(row(_id=2, start_at=START-timedelta(hours=1), end_at=START), query)
    assert not matches(row(_id=2, status="cancelled"), query)
    assert not matches(row(_id=2, status="completed"), query)
    assert matches(row(_id=2, status="rescheduled"), query)


def test_calendar_includes_cross_midnight_but_excludes_midnight_boundary():
    day = START.replace(hour=0)
    query = calendar_range_query(day, day+timedelta(days=1))
    assert matches(row(start_at=day-timedelta(hours=1), end_at=day+timedelta(hours=1)), query)
    assert not matches(row(start_at=day-timedelta(hours=1), end_at=day), query)
    assert not matches(row(start_at=day+timedelta(days=1), end_at=day+timedelta(days=1,hours=1)), query)


def test_no_interviewer_keeps_candidate_conflict_protection():
    query = conflict_query(10, START, END)
    assert matches(row(), query)
    assert not matches(row(candidate_id=11), query)
