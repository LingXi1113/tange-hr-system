"""招聘报表接口：需求、漏斗、渠道、招聘周期和 CSV 导出。"""
import csv
import io
from collections import defaultdict
from datetime import datetime, time

from flask import Blueprint, Response, g, request

from common.db import col, dt, next_id
from common.decorators import role_required
from common.errors import BizError
from common.response import BizCode, ok
from common.stages import DEFAULT_STAGES, STAGE_NAMES
from common.roles import HR

bp = Blueprint("report_api", __name__, url_prefix="/api/reports")


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _filters():
    args = request.args
    date_from = None
    date_to = None
    try:
        if args.get("date_from"):
            date_from = datetime.strptime(args["date_from"], "%Y-%m-%d")
        if args.get("date_to"):
            date_to = datetime.combine(
                datetime.strptime(args["date_to"], "%Y-%m-%d").date(), time(23, 59, 59)
            )
    except ValueError as exc:
        raise BizError(BizCode.PARAM_INVALID, "日期格式应为 YYYY-MM-DD") from exc
    try:
        job_id = int(args["job_id"]) if args.get("job_id") else None
    except ValueError as exc:
        raise BizError(BizCode.PARAM_INVALID, "job_id 必须是整数") from exc
    return {
        "date_from": date_from,
        "date_to": date_to,
        "job_id": job_id,
        "dept_id": args.get("dept_id") or None,
        "source": args.get("source") or None,
        "owner_id": args.get("owner_id") or None,
        "requirement_status": args.get("requirement_status") or None,
    }


def _load_context(filters):
    jobs = {job["_id"]: job for job in col("jobs").find({})}
    candidates = {candidate["_id"]: candidate for candidate in col("candidates").find({})}
    apps = []
    for app in col("applications").find({}).sort("created_at", 1):
        job = jobs.get(app.get("job_id"), {})
        if filters["job_id"] and app.get("job_id") != filters["job_id"]:
            continue
        if filters["dept_id"] and job.get("dept_id") != filters["dept_id"]:
            continue
        if filters["source"] and app.get("source") != filters["source"]:
            continue
        if filters["owner_id"] and app.get("owner_id") != filters["owner_id"]:
            continue
        created_at = _as_datetime(app.get("created_at"))
        if filters["date_from"] and (created_at is None or created_at < filters["date_from"]):
            continue
        if filters["date_to"] and (created_at is None or created_at > filters["date_to"]):
            continue
        app["_job"] = job
        app["_candidate"] = candidates.get(app.get("candidate_id"), {})
        apps.append(app)
    return jobs, apps


def _funnel_rows(apps):
    counts = defaultdict(int)
    for app in apps:
        counts[app.get("current_stage", "unknown")] += 1
    known = [stage_key for stage_key, *_ in DEFAULT_STAGES] + ["eliminated", "talent_pool"]
    known += [stage for stage in counts if stage not in known]
    return [{
        "stage_key": stage_key,
        "name": STAGE_NAMES.get(stage_key, stage_key),
        "count": counts.get(stage_key, 0),
    } for stage_key in known]


def _channel_rows(apps):
    app_ids = [app["_id"] for app in apps]
    interviews = defaultdict(set)
    offers = defaultdict(set)
    if app_ids:
        for item in col("interviews").find({"application_id": {"$in": app_ids}}):
            interviews[item.get("application_id")].add(item.get("_id"))
        for item in col("offers").find({"application_id": {"$in": app_ids}}):
            offers[item.get("application_id")].add(item.get("_id"))
    grouped = defaultdict(list)
    for app in apps:
        grouped[app.get("source") or "unknown"].append(app)
    rows = []
    for source, source_apps in sorted(grouped.items()):
        source_ids = {app["_id"] for app in source_apps}
        interview_count = sum(len(interviews[app_id]) for app_id in source_ids)
        offer_count = sum(len(offers[app_id]) for app_id in source_ids)
        onboarded = sum(1 for app in source_apps if app.get("status") == "onboarded")
        total = len(source_apps)
        rows.append({
            "source": source,
            "applications": total,
            "candidates": len({app.get("candidate_id") for app in source_apps}),
            "interviews": interview_count,
            "offers": offer_count,
            "onboarded": onboarded,
            "interview_rate": round(interview_count / total * 100, 1) if total else 0,
            "offer_rate": round(offer_count / total * 100, 1) if total else 0,
            "onboard_rate": round(onboarded / total * 100, 1) if total else 0,
        })
    return rows


def _average(values):
    return round(sum(values) / len(values), 1) if values else 0


def _cycle_data(apps):
    app_ids = [app["_id"] for app in apps]
    transitions = defaultdict(list)
    if app_ids:
        for item in col("stage_transitions").find({"application_id": {"$in": app_ids}}).sort("created_at", 1):
            created_at = _as_datetime(item.get("created_at"))
            if created_at:
                transitions[item["application_id"]].append((created_at, item.get("from_stage", ""), item.get("to_stage", "")))
    recruitment, screening, interview, offer_onboard = [], [], [], []
    for app in apps:
        events = transitions.get(app["_id"], [])
        start = _as_datetime(app.get("created_at")) or (events[0][0] if events else None)
        if not start:
            continue
        first_screen = next((event[0] for event in events if event[2] == "pending_screen"), None)
        screen_passed = next((event[0] for event in events if event[2] == "hr_screen_passed"), None)
        interview_start = next((event[0] for event in events if event[2] == "pending_interview"), None)
        interview_end = next((event[0] for event in events if event[2] == "interview_passed"), None)
        offer_start = next((event[0] for event in events if event[2] == "offer_pending"), None)
        onboarded = next((event[0] for event in events if event[2] in ("pending_onboard", "onboarded")), None)
        final_event = next((event[0] for event in reversed(events) if event[2] in ("onboarded", "eliminated", "abandoned")), None)
        if final_event:
            recruitment.append(max((final_event - start).total_seconds() / 86400, 0))
        if first_screen and screen_passed:
            screening.append(max((screen_passed - first_screen).total_seconds() / 86400, 0))
        if interview_start and interview_end:
            interview.append(max((interview_end - interview_start).total_seconds() / 86400, 0))
        if offer_start and onboarded:
            offer_onboard.append(max((onboarded - offer_start).total_seconds() / 86400, 0))
    return {
        "metrics": {
            "avg_recruitment_days": _average(recruitment),
            "avg_screening_days": _average(screening),
            "avg_interview_days": _average(interview),
            "avg_offer_to_onboard_days": _average(offer_onboard),
        },
        "sample_count": len(apps),
    }


def _requirements_data(filters=None):
    now = datetime.now()
    requirements = list(col("requirements").find({}).sort("_id", -1))
    jobs = list(col("jobs").find({}))
    apps = list(col("applications").find({}))
    rows = []
    status_counts = defaultdict(int)
    for req in requirements:
        status = req.get("status", "draft")
        created_at = _as_datetime(req.get("created_at"))
        if filters:
            if filters["date_from"] and (created_at is None or created_at < filters["date_from"]):
                continue
            if filters["date_to"] and (created_at is None or created_at > filters["date_to"]):
                continue
        job_ids = [job["_id"] for job in jobs if job.get("requirement_id") == req["_id"]]
        if filters and filters["job_id"] and filters["job_id"] not in job_ids:
            continue
        if filters and filters["dept_id"] and req.get("dept_id") != filters["dept_id"]:
            continue
        if filters and filters["owner_id"] and req.get("owner_id") != filters["owner_id"]:
            continue
        if filters and filters["requirement_status"] and status != filters["requirement_status"]:
            continue
        status_counts[status] += 1
        candidate_count = sum(1 for app in apps if app.get("job_id") in job_ids)
        due_date = _as_datetime(req.get("due_date"))
        rows.append({
            "id": req["_id"],
            "code": req.get("code", f"REQ-{req['_id']:04d}"),
            "name": req.get("name", ""),
            "dept_name": req.get("dept_name", ""),
            "status": status,
            "headcount": req.get("headcount", 0),
            "due_date": dt(due_date),
            "job_count": len(job_ids),
            "candidate_count": candidate_count,
            "overdue": bool(due_date and due_date < now and status in ("recruiting", "paused")),
        })
    summary = {
        "total": len(requirements),
        "draft": status_counts["draft"],
        "pending_confirm": status_counts["pending_confirm"],
        "recruiting": status_counts["recruiting"],
        "paused": status_counts["paused"],
        "completed": status_counts["completed"],
        "closed": status_counts["closed"],
        "overdue": sum(1 for row in rows if row["overdue"]),
    }
    return {"summary": summary, "rows": rows}


@bp.get("/requirements")
@role_required(HR)
def requirements_report():
    return ok(_requirements_data(_filters()))


@bp.get("/funnel")
@role_required(HR)
def funnel_report():
    _, apps = _load_context(_filters())
    rows = _funnel_rows(apps)
    return ok({"total": len(apps), "stage_counts": rows, "rows": rows})


@bp.get("/channels")
@role_required(HR)
def channels_report():
    _, apps = _load_context(_filters())
    rows = _channel_rows(apps)
    return ok({"total": len(apps), "rows": rows})


@bp.get("/cycle")
@role_required(HR)
def cycle_report():
    _, apps = _load_context(_filters())
    return ok(_cycle_data(apps))


def _export_rows(report_type, filters):
    if report_type == "requirements":
        return _requirements_data(filters)["rows"]
    _, apps = _load_context(filters)
    if report_type == "funnel":
        return _funnel_rows(apps)
    if report_type == "channels":
        return _channel_rows(apps)
    if report_type == "cycle":
        return [{"metric": key, "days": value} for key, value in _cycle_data(apps)["metrics"].items()]
    raise BizError(BizCode.PARAM_INVALID, "不支持的报表类型")


@bp.get("/export")
@role_required(HR)
def export_report():
    report_type = request.args.get("type", "funnel")
    rows = _export_rows(report_type, _filters())
    output = io.StringIO()
    fieldnames = list(rows[0].keys()) if rows else ["message"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    if rows:
        writer.writerows(rows)
    else:
        writer.writerow({"message": "暂无数据"})
    col("export_logs").insert_one({
        "_id": next_id("export_logs"),
        "scene": "report",
        "report_type": report_type,
        "exporter_id": g.current_user.user_id,
        "exporter_name": g.current_user.name,
        "conditions": {key: value for key, value in request.args.items()},
        "row_count": len(rows),
        "created_at": datetime.now(),
    })
    from common.logstore import write_log

    write_log("export", "report", g.current_user.user_id, g.current_user.name,
              detail=f"type={report_type}; rows={len(rows)}")
    response = Response("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="hr-report-{report_type}.csv"'
    return response
