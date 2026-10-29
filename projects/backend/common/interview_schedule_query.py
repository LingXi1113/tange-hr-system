"""Half-open intervals: adjacent interviews do not overlap."""
ACTIVE_STATUSES = ("pending", "invited", "confirmed", "rescheduled")


def conflict_query(candidate_id, start_at, end_at, exclude_id=None, interviewer_id=None):
    query = {
        "status": {"$in": list(ACTIVE_STATUSES)},
        "start_at": {"$lt": end_at},
        "end_at": {"$gt": start_at},
    }
    participants = [{"candidate_id": candidate_id}]
    if interviewer_id:
        participants.append({"interviewer_id": interviewer_id})
    query["$or"] = participants
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    return query


def calendar_range_query(start_at, end_exclusive):
    return {"start_at": {"$lt": end_exclusive}, "end_at": {"$gt": start_at}}
