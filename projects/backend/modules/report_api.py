"""招聘报表接口：需求、漏斗、渠道、招聘周期和 CSV 导出。"""
import csv
import io
from collections import defaultdict
from datetime import datetime, time

from flask import Blueprint, Response, current_app, g, request

from common.db import col, dt, next_id
from common.decorators import role_required
from common.errors import BizError
from common.response import BizCode, ok
from common.stages import DEFAULT_STAGES, INTERVIEW_ROUNDS, STAGE_NAMES
from common.roles import HR
from platform_identity import get_identity

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
    try:
        template_id = int(args["template_id"]) if args.get("template_id") else None
    except ValueError as exc:
        raise BizError(BizCode.PARAM_INVALID, "template_id 必须是整数") from exc
    try:
        requirement_id = int(args["requirement_id"]) if args.get("requirement_id") else None
    except ValueError as exc:
        raise BizError(BizCode.PARAM_INVALID, "requirement_id 必须是整数") from exc
    job_date_from = None
    job_date_to = None
    try:
        if args.get("job_date_from"):
            job_date_from = datetime.strptime(args["job_date_from"], "%Y-%m-%d")
        if args.get("job_date_to"):
            job_date_to = datetime.combine(
                datetime.strptime(args["job_date_to"], "%Y-%m-%d").date(), time(23, 59, 59)
            )
    except ValueError as exc:
        raise BizError(BizCode.PARAM_INVALID, "职位开始时间格式应为 YYYY-MM-DD") from exc
    return {
        "date_from": date_from,
        "date_to": date_to,
        "job_id": job_id,
        "dept_id": args.get("dept_id") or None,
        "source": args.get("source") or None,
        "owner_id": args.get("owner_id") or None,
        "requirement_status": args.get("requirement_status") or None,
        "job_status": args.get("job_status") or None,
        "template_id": template_id,
        "requirement_id": requirement_id,
        "job_date_from": job_date_from,
        "job_date_to": job_date_to,
        "interviewer_name": args.get("interviewer_name") or None,
        "interviewer_dept": args.get("interviewer_dept") or None,
        "resume_status": args.get("resume_status") or None,
        "headhunter_supplier": args.get("headhunter_supplier") or None,
        "portal_plan": args.get("portal_plan") or None,
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
        if filters.get("job_status") and job.get("status") != filters["job_status"]:
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


RECOMMENDED_STAGES = {
    "business_screen", "hr_screen_passed", "pending_interview", "interviewing",
    "interview_passed", "interview_1", "interview_2", "interview_3", "hr_interview",
    "re_interview", "offer_approval", "offer", "offer_pending", "pending_onboard",
    "onboarded",
}


def _job_matches_report_filters(job, filters):
    if filters["job_id"] and job.get("_id") != filters["job_id"]:
        return False
    if filters["dept_id"] and job.get("dept_id") != filters["dept_id"]:
        return False
    if filters["owner_id"] and job.get("owner_id") != filters["owner_id"]:
        return False
    if filters.get("job_status") and job.get("status") != filters["job_status"]:
        return False
    if filters.get("template_id") and job.get("template_id") != filters["template_id"]:
        return False
    if filters.get("requirement_id") and job.get("requirement_id") != filters["requirement_id"]:
        return False
    created_at = _as_datetime(job.get("created_at"))
    if filters.get("job_date_from") and (created_at is None or created_at < filters["job_date_from"]):
        return False
    if filters.get("job_date_to") and (created_at is None or created_at > filters["job_date_to"]):
        return False
    return True


def _job_progress_data(filters):
    """按职位聚合招聘进展，所有数量均以应聘记录为统计单位。"""
    # 此页面的“招聘 HR”指职位负责人；不再用应聘记录当前锁定人二次过滤。
    context_filters = dict(filters)
    context_filters["owner_id"] = None
    jobs_by_id, apps = _load_context(context_filters)
    jobs = [
        job for job in jobs_by_id.values()
        if _job_matches_report_filters(job, filters)
    ]
    visible_job_ids = {job["_id"] for job in jobs}
    apps = [app for app in apps if app.get("job_id") in visible_job_ids]
    app_ids = [app["_id"] for app in apps]

    interviews_by_app = defaultdict(list)
    offers_by_app = defaultdict(list)
    reached_stages_by_app = defaultdict(set)
    onboarded_at_by_app = {}
    if app_ids:
        for item in col("interviews").find({"application_id": {"$in": app_ids}}):
            interviews_by_app[item.get("application_id")].append(item)
        for item in col("offers").find({"application_id": {"$in": app_ids}}):
            offers_by_app[item.get("application_id")].append(item)
        for item in col("stage_transitions").find({"application_id": {"$in": app_ids}}):
            reached_stages_by_app[item.get("application_id")].add(item.get("to_stage"))
            if item.get("to_stage") == "onboarded":
                created_at = _as_datetime(item.get("created_at"))
                if created_at:
                    onboarded_at_by_app[item.get("application_id")] = created_at

    apps_by_job = defaultdict(list)
    for app in apps:
        apps_by_job[app.get("job_id")].append(app)

    def app_metrics(job_apps):
        received = len(job_apps)
        recommended = sum(
            1 for app in job_apps
            if app.get("current_stage") in RECOMMENDED_STAGES
            or reached_stages_by_app.get(app.get("_id"), set()) & RECOMMENDED_STAGES
        )
        scheduled = sum(1 for app in job_apps if interviews_by_app.get(app.get("_id")))
        interviewed = sum(
            1 for app in job_apps
            if any(item.get("status") in ("completed", "passed", "failed")
                   for item in interviews_by_app.get(app.get("_id"), []))
        )
        offered = sum(
            1 for app in job_apps
            if any(item.get("status") in ("sent", "accepted", "rejected", "expired", "withdrawn")
                   for item in offers_by_app.get(app.get("_id"), []))
        )
        pending_onboard = sum(
            1 for app in job_apps
            if app.get("current_stage") == "pending_onboard"
            or app.get("status") == "pending_onboard"
        )
        onboarded = sum(
            1 for app in job_apps
            if app.get("current_stage") == "onboarded" or app.get("status") == "onboarded"
        )
        return {
            "received": received,
            "recommended": recommended,
            "scheduled": scheduled,
            "interviewed": interviewed,
            "offered": offered,
            "pending_onboard": pending_onboard,
            "onboarded": onboarded,
            # 当前系统尚无转正业务数据，先保留报表指标位。
            "regularized": 0,
        }

    def onboarding_cycle(job_apps):
        days = []
        for app in job_apps:
            if app.get("current_stage") != "onboarded" and app.get("status") != "onboarded":
                continue
            started_at = _as_datetime(app.get("created_at"))
            ended_at = onboarded_at_by_app.get(app.get("_id")) or _as_datetime(app.get("updated_at"))
            if started_at and ended_at:
                days.append(max((ended_at - started_at).total_seconds() / 86400, 0))
        return round(sum(days) / len(days), 1) if days else 0

    rows = []
    for job in sorted(jobs, key=lambda item: item.get("_id", 0), reverse=True):
        metrics = app_metrics(apps_by_job[job["_id"]])
        headcount = max(int(job.get("headcount") or 0), 0)
        rows.append({
            "job_id": job["_id"],
            "job_name": job.get("name", ""),
            "owner_id": job.get("owner_id", ""),
            "owner_name": job.get("owner_name", "") or "未分配",
            "dept_id": job.get("dept_id", ""),
            "dept_name": job.get("dept_name", "") or "未设置部门",
            "location": job.get("location", ""),
            "job_type": job.get("job_type", ""),
            "status": job.get("status", ""),
            "headcount": headcount,
            "completion_rate": round(metrics["onboarded"] / headcount * 100, 1) if headcount else 0,
            "onboarding_cycle": onboarding_cycle(apps_by_job[job["_id"]]),
            **metrics,
        })

    summary = {
        key: sum(row[key] for row in rows)
        for key in (
            "received", "recommended", "scheduled", "interviewed", "offered",
            "pending_onboard", "onboarded", "regularized",
        )
    }
    summary["active_jobs"] = sum(1 for row in rows if row["status"] == "recruiting")
    total_headcount = sum(row["headcount"] for row in rows)
    summary["completion_rate"] = round(
        summary["onboarded"] / total_headcount * 100, 1
    ) if total_headcount else 0
    onboard_cycles = [row["onboarding_cycle"] for row in rows if row["onboarding_cycle"] > 0]
    summary["onboarding_cycle"] = round(
        sum(onboard_cycles) / len(onboard_cycles), 1
    ) if onboard_cycles else 0

    source_names = {
        "website": "官网投递", "job_site": "招聘网站", "campus": "校园招聘",
        "referral": "内部推荐", "headhunt": "猎头", "manual": "手动录入",
        "unknown": "其他",
    }
    source_counts = defaultdict(int)
    delivery_onboarded = defaultdict(int)
    active_sources = {"website", "job_site", "campus"}
    for app in apps:
        source = app.get("source") or "unknown"
        source_counts[source_names.get(source, source)] += 1
        if app.get("current_stage") == "onboarded" or app.get("status") == "onboarded":
            delivery_onboarded["主动投递" if source in active_sources else "被动寻访"] += 1

    def grouped_rows(group_key, metric_key):
        grouped = defaultdict(int)
        for row in rows:
            grouped[row[group_key]] += row[metric_key]
        return [
            {"name": name, "value": value}
            for name, value in sorted(grouped.items(), key=lambda item: (-item[1], item[0]))
        ]

    return {
        "summary": summary,
        "rankings": {
            "job_resumes": [
                {"name": row["job_name"], "value": row["received"]} for row in rows
            ],
            "department_onboarded": grouped_rows("dept_name", "onboarded"),
            "hr_recommended": grouped_rows("owner_name", "recommended"),
            "hr_offers": grouped_rows("owner_name", "offered"),
            "job_completion": [
                {"name": row["job_name"], "value": row["completion_rate"]} for row in rows
            ],
            "job_onboarded": [
                {"name": row["job_name"], "value": row["onboarded"]} for row in rows
            ],
            "job_onboarding_cycle": [
                {"name": row["job_name"], "value": row["onboarding_cycle"]} for row in rows
            ],
            "delivery_onboarded": [
                {"name": name, "value": value} for name, value in delivery_onboarded.items()
            ],
            "resume_sources": [
                {"name": name, "value": value}
                for name, value in sorted(source_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
        },
        "rows": rows,
    }


@bp.get("/job-progress")
@role_required(HR)
def job_progress_report():
    return ok(_job_progress_data(_filters()))


def _channel_effect_data(filters):
    """招聘渠道效果：按来源聚合投递、Offer、入职及转化率。"""
    jobs_by_id, apps = _load_context(filters)
    visible_job_ids = {
        job["_id"] for job in jobs_by_id.values()
        if _job_matches_report_filters(job, filters)
    }
    apps = [app for app in apps if app.get("job_id") in visible_job_ids]
    rows = _channel_rows(apps)
    app_ids = [app["_id"] for app in apps]

    onboarded_at_by_app = {}
    if app_ids:
        for item in col("stage_transitions").find({
            "application_id": {"$in": app_ids}, "to_stage": "onboarded",
        }):
            created_at = _as_datetime(item.get("created_at"))
            if created_at:
                onboarded_at_by_app[item.get("application_id")] = created_at

    cycle_days = []
    pending_onboard = 0
    for app in apps:
        if app.get("current_stage") == "pending_onboard" or app.get("status") == "pending_onboard":
            pending_onboard += 1
        if app.get("current_stage") != "onboarded" and app.get("status") != "onboarded":
            continue
        started_at = _as_datetime(app.get("created_at"))
        ended_at = onboarded_at_by_app.get(app.get("_id")) or _as_datetime(app.get("updated_at"))
        if started_at and ended_at:
            cycle_days.append(max((ended_at - started_at).total_seconds() / 86400, 0))

    return {
        "summary": {
            "active_channels": sum(1 for row in rows if row["applications"] > 0),
            "applications": len(apps),
            "offers": sum(row["offers"] for row in rows),
            "pending_onboard": pending_onboard,
            "onboarded": sum(row["onboarded"] for row in rows),
            "onboarding_cycle": round(sum(cycle_days) / len(cycle_days), 1) if cycle_days else 0,
        },
        "rows": rows,
        # 当前系统尚未建设入职后离职模块，先保留图表数据位。
        "attrition": [],
    }


@bp.get("/channel-effect")
@role_required(HR)
def channel_effect_report():
    return ok(_channel_effect_data(_filters()))


def _stage_funnel_data(filters):
    """阶段转化漏斗：累计到达、面试轮次和当前阶段三组数据。"""
    # 页面筛选项中的负责人是职位负责人，不是应聘记录当前锁定人。
    context_filters = dict(filters)
    context_filters["owner_id"] = None
    jobs_by_id, apps = _load_context(context_filters)
    visible_job_ids = {
        job["_id"] for job in jobs_by_id.values()
        if _job_matches_report_filters(job, filters)
    }
    apps = [app for app in apps if app.get("job_id") in visible_job_ids]
    app_ids = [app["_id"] for app in apps]

    stage_keys = [stage[0] for stage in DEFAULT_STAGES]
    reached_by_app = defaultdict(set)
    for app in apps:
        reached_by_app[app["_id"]].add("new_resume")
        if app.get("current_stage"):
            reached_by_app[app["_id"]].add(app["current_stage"])
    if app_ids:
        for item in col("stage_transitions").find({"application_id": {"$in": app_ids}}):
            if item.get("from_stage"):
                reached_by_app[item["application_id"]].add(item["from_stage"])
            if item.get("to_stage"):
                reached_by_app[item["application_id"]].add(item["to_stage"])

    cumulative_counts = []
    for index, stage_key in enumerate(stage_keys):
        count = 0
        for app in apps:
            reached = reached_by_app[app["_id"]]
            reached_indexes = [stage_keys.index(key) for key in reached if key in stage_keys]
            if reached_indexes and max(reached_indexes) >= index:
                count += 1
        cumulative_counts.append(count)

    stage_funnel = []
    first_count = cumulative_counts[0] if cumulative_counts else 0
    for index, stage_key in enumerate(stage_keys):
        count = cumulative_counts[index]
        previous = cumulative_counts[index - 1] if index else count
        stage_funnel.append({
            "stage_key": stage_key,
            "name": STAGE_NAMES.get(stage_key, stage_key),
            "count": count,
            "previous_rate": round(count / previous * 100, 1) if previous else 0,
            "overall_rate": round(count / first_count * 100, 1) if first_count else 0,
        })

    interview_apps = defaultdict(set)
    if app_ids:
        for interview in col("interviews").find({"application_id": {"$in": app_ids}}):
            round_name = interview.get("round") or "未设置轮次"
            interview_apps[round_name].add(interview.get("application_id"))
    interview_order = list(INTERVIEW_ROUNDS)
    interview_order += sorted(name for name in interview_apps if name not in interview_order)
    interview_funnel = []
    first_interview_count = 0
    previous_interview_count = 0
    for round_name in interview_order:
        count = len(interview_apps.get(round_name, set()))
        if not first_interview_count and count:
            first_interview_count = count
        interview_funnel.append({
            "name": round_name,
            "count": count,
            "previous_rate": round(count / previous_interview_count * 100, 1)
            if previous_interview_count else (100 if count else 0),
            "overall_rate": round(count / first_interview_count * 100, 1)
            if first_interview_count else 0,
        })
        if count:
            previous_interview_count = count

    current_counts = defaultdict(int)
    for app in apps:
        current_counts[app.get("current_stage") or "unknown"] += 1
    current_order = stage_keys + ["eliminated", "abandoned", "talent_pool"]
    current_order += sorted(key for key in current_counts if key not in current_order)
    current_stages = [{
        "stage_key": stage_key,
        "name": STAGE_NAMES.get(stage_key, stage_key),
        "count": current_counts.get(stage_key, 0),
    } for stage_key in current_order]

    return {
        "total": len(apps),
        "stage_funnel": stage_funnel,
        "interview_funnel": interview_funnel,
        "current_stages": current_stages,
    }


@bp.get("/stage-funnel")
@role_required(HR)
def stage_funnel_report():
    return ok(_stage_funnel_data(_filters()))


def _interviewer_efficiency_data(filters):
    """面试官效率：按面试官聚合推荐、反馈、通过率和反馈时效。"""
    jobs = {job["_id"]: job for job in col("jobs").find({})}
    visible_job_ids = {
        job["_id"] for job in jobs.values()
        if _job_matches_report_filters(job, filters)
    }
    department_users = None
    if filters.get("interviewer_dept"):
        department_users = {
            user.name for user in get_identity(current_app).list_users()
            if user.dept_id == filters["interviewer_dept"]
            or user.dept_name == filters["interviewer_dept"]
        }

    interviews = []
    for interview in col("interviews").find({}).sort("created_at", 1):
        if interview.get("job_id") not in visible_job_ids:
            continue
        interviewer_name = interview.get("interviewer_name") or "未指定面试官"
        if filters.get("interviewer_name") and interviewer_name != filters["interviewer_name"]:
            continue
        if department_users is not None and interviewer_name not in department_users:
            continue
        operated_at = _as_datetime(interview.get("created_at")) or _as_datetime(interview.get("start_at"))
        if filters["date_from"] and (operated_at is None or operated_at < filters["date_from"]):
            continue
        if filters["date_to"] and (operated_at is None or operated_at > filters["date_to"]):
            continue
        interviews.append(interview)

    interview_ids = [item["_id"] for item in interviews]
    feedback_by_interview = {}
    if interview_ids:
        feedback_by_interview = {
            item["interview_id"]: item
            for item in col("interview_feedback").find({"interview_id": {"$in": interview_ids}})
        }

    grouped = defaultdict(lambda: {
        "recommended": 0, "feedback": 0, "passed": 0, "failed": 0,
        "held": 0, "no_feedback": 0, "attended": 0,
        "interview_feedback": 0, "feedback_hours": [],
    })
    for interview in interviews:
        name = interview.get("interviewer_name") or "未指定面试官"
        item = grouped[name]
        item["recommended"] += 1
        feedback = feedback_by_interview.get(interview["_id"])
        valid_feedback = feedback is not None and not feedback.get("skip_eval")
        if valid_feedback:
            item["feedback"] += 1
            conclusion = feedback.get("conclusion")
            if conclusion == "pass":
                item["passed"] += 1
            elif conclusion == "fail":
                item["failed"] += 1
            else:
                item["held"] += 1
            started_at = _as_datetime(interview.get("created_at")) or _as_datetime(interview.get("end_at"))
            feedback_at = _as_datetime(feedback.get("created_at")) or _as_datetime(feedback.get("updated_at"))
            if started_at and feedback_at:
                item["feedback_hours"].append(
                    max((feedback_at - started_at).total_seconds() / 3600, 0)
                )
        else:
            item["no_feedback"] += 1
        if interview.get("status") == "completed":
            item["attended"] += 1
            if valid_feedback:
                item["interview_feedback"] += 1

    rows = []
    for name, item in grouped.items():
        feedback_hours = item.pop("feedback_hours")
        rows.append({
            "name": name,
            **item,
            "feedback_rate": round(item["feedback"] / item["recommended"] * 100, 1)
            if item["recommended"] else 0,
            "interview_feedback_rate": round(
                item["interview_feedback"] / item["attended"] * 100, 1
            ) if item["attended"] else 0,
            "pass_rate": round(item["passed"] / item["feedback"] * 100, 1)
            if item["feedback"] else 0,
            "feedback_hours": round(sum(feedback_hours) / len(feedback_hours), 1)
            if feedback_hours else 0,
        })
    rows.sort(key=lambda item: (-item["recommended"], item["name"]))

    summary = {
        "recommended": sum(item["recommended"] for item in rows),
        "feedback": sum(item["feedback"] for item in rows),
        "attended": sum(item["attended"] for item in rows),
        "interview_feedback": sum(item["interview_feedback"] for item in rows),
    }
    summary["feedback_rate"] = round(
        summary["feedback"] / summary["recommended"] * 100, 1
    ) if summary["recommended"] else 0
    summary["interview_feedback_rate"] = round(
        summary["interview_feedback"] / summary["attended"] * 100, 1
    ) if summary["attended"] else 0
    return {"summary": summary, "rows": rows}


@bp.get("/interviewer-efficiency")
@role_required(HR)
def interviewer_efficiency_report():
    return ok(_interviewer_efficiency_data(_filters()))


def _parse_profile_date(value):
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def _work_years(candidate):
    experiences = candidate.get("work_experience") or []
    if isinstance(candidate.get("work_years"), (int, float)):
        return float(candidate["work_years"])
    months = 0
    for item in experiences:
        start = _parse_profile_date(item.get("start") or item.get("start_date"))
        end = _parse_profile_date(item.get("end") or item.get("end_date")) or datetime.now()
        if start and end and end >= start:
            months += max((end.year - start.year) * 12 + end.month - start.month, 0)
    return months / 12 if months else None


def _age(candidate):
    value = candidate.get("age")
    if isinstance(value, (int, float)):
        return int(value)
    birth = _parse_profile_date(candidate.get("birth_date") or candidate.get("birthday"))
    if birth:
        today = datetime.now()
        return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    return None


_PROFILE_DEGREE_ORDER = ["初中", "高中", "中专", "大专", "本科", "硕士", "博士"]
_PROFILE_DEGREE_RANK = {name: index for index, name in enumerate(_PROFILE_DEGREE_ORDER, 1)}


def _normalized_profile_degree(value):
    value = str(value or "").strip()
    if "博士" in value:
        return "博士"
    if any(token in value.upper() for token in ("硕士", "研究生", "MBA", "EMBA")):
        return "硕士"
    if "本科" in value or "学士" in value:
        return "本科"
    if any(token in value for token in ("大专", "专科", "高职")):
        return "大专"
    if "中专" in value:
        return "中专"
    if "高中" in value:
        return "高中"
    if "初中" in value:
        return "初中"
    return ""


def _highest_degree(candidate):
    stored = _normalized_profile_degree(candidate.get("highest_education"))
    degrees = [stored] if stored else []
    degrees.extend(
        _normalized_profile_degree(item.get("degree"))
        for item in (candidate.get("education") or [])
    )
    degrees = [item for item in degrees if item]
    return max(degrees, key=lambda item: _PROFILE_DEGREE_RANK[item], default="其他")


def _profile_date_sort_value(value, current=False):
    text = str(value or "").strip()
    if text.lower() in {"至今", "现在", "目前", "present", "current"}:
        return 999912
    parsed = _parse_profile_date(text)
    if parsed:
        return parsed.year * 100 + parsed.month
    if len(text) == 4 and text.isdigit():
        return int(text) * 100
    return 999911 if current else 0


def _latest_work_record(candidate):
    """Select the latest appointment by end date, then start date."""
    experiences = [
        item for item in (candidate.get("work_experience") or [])
        if isinstance(item, dict) and str(item.get("company") or "").strip()
    ]
    if not experiences:
        return {}
    dated = [
        item for item in experiences
        if item.get("end") or item.get("end_date") or item.get("start") or item.get("start_date")
    ]
    if not dated:
        # Resumes usually list work history newest first when dates are absent.
        return experiences[0]
    return max(dated, key=lambda item: (
        _profile_date_sort_value(item.get("end") or item.get("end_date")),
        _profile_date_sort_value(item.get("start") or item.get("start_date")),
    ))


def _candidate_profession(candidate):
    stored = str(candidate.get("major") or "").strip()
    if stored:
        return stored
    education = candidate.get("education") or []
    with_major = [item for item in education if str(item.get("major") or "").strip()]
    if not with_major:
        return "未知"
    selected = max(with_major, key=lambda item: (
        _PROFILE_DEGREE_RANK.get(_normalized_profile_degree(item.get("degree")), 0),
        str(item.get("graduate_at") or ""),
    ))
    return str(selected.get("major") or "未知").strip()


def _bucket_age(value):
    if value is None:
        return "未知"
    if value <= 25:
        return "25岁以下"
    if value <= 30:
        return "25~30岁"
    if value <= 35:
        return "31~35岁"
    if value <= 40:
        return "36~40岁"
    if value <= 45:
        return "41~45岁"
    return "45岁以上"


def _bucket_work_years(value):
    if value is None:
        return "未知"
    if value <= 1:
        return "1年以下"
    if value <= 3:
        return "1~3年"
    if value <= 5:
        return "3~5年"
    if value <= 8:
        return "5~8年"
    if value <= 10:
        return "8~10年"
    return "10年以上"


def _profile_distribution(values, order=None):
    counts = defaultdict(int)
    for value in values:
        counts[value or "未知"] += 1
    keys = list(order or [])
    keys += sorted(key for key in counts if key not in keys)
    return [{"name": key, "value": counts.get(key, 0)} for key in keys]


def _talent_profile_data(filters):
    context_filters = dict(filters)
    context_filters["owner_id"] = None
    jobs_by_id, apps = _load_context(context_filters)
    visible_job_ids = {
        job["_id"] for job in jobs_by_id.values()
        if _job_matches_report_filters(job, filters)
    }
    apps = [app for app in apps if app.get("job_id") in visible_job_ids]

    candidates = {candidate["_id"]: candidate for candidate in col("candidates").find({})}
    candidate_ids_with_applications = set(col("applications").distinct("candidate_id"))
    selected = []
    seen = set()
    for app in apps:
        candidate = candidates.get(app.get("candidate_id"))
        if not candidate or candidate["_id"] in seen:
            continue
        if filters.get("resume_status") and candidate.get("resume_status") != filters["resume_status"]:
            continue
        seen.add(candidate["_id"])
        selected.append(candidate)

    # With no job-scoped condition, talent profile also represents candidates
    # still waiting for position assignment. Previously these candidates were
    # silently omitted because the report started exclusively from applications.
    job_scoped = any(filters.get(key) for key in (
        "job_id", "dept_id", "job_status", "template_id", "requirement_id",
        "job_date_from", "job_date_to",
    ))
    if not job_scoped:
        for candidate in candidates.values():
            if candidate["_id"] in seen or candidate["_id"] in candidate_ids_with_applications:
                continue
            if filters.get("resume_status") and candidate.get("resume_status") != filters["resume_status"]:
                continue
            if filters.get("source") and candidate.get("source") != filters["source"]:
                continue
            created_at = _as_datetime(candidate.get("created_at"))
            if filters.get("date_from") and (created_at is None or created_at < filters["date_from"]):
                continue
            if filters.get("date_to") and (created_at is None or created_at > filters["date_to"]):
                continue
            seen.add(candidate["_id"])
            selected.append(candidate)

    gender_order = ["男", "女", "未知"]
    age_order = ["25~30岁", "25岁以下", "31~35岁", "36~40岁", "41~45岁", "45岁以上", "未知"]
    work_order = ["1年以下", "1~3年", "3~5年", "5~8年", "8~10年", "10年以上", "未知"]
    degree_order = [*_PROFILE_DEGREE_ORDER, "其他"]
    channel_order = ["官网投递", "招聘网站", "校园招聘", "内部推荐", "猎头", "手动录入", "其他"]
    gender = _profile_distribution([candidate.get("gender") or "未知" for candidate in selected], gender_order)
    work = _profile_distribution([_bucket_work_years(_work_years(candidate)) for candidate in selected], work_order)
    age = _profile_distribution([_bucket_age(_age(candidate)) for candidate in selected], age_order)

    degrees = []
    schools = defaultdict(int)
    for candidate in selected:
        education = candidate.get("education") or []
        degrees.append(_highest_degree(candidate))
        for item in education:
            school = str(item.get("school") or "").strip()
            if school:
                schools[school] += 1
    highest_education = _profile_distribution(degrees, degree_order)

    # 候选人画像按人数统计，避免同一候选人多次投递重复计算渠道。
    source_by_candidate = {}
    for app in apps:
        source_by_candidate.setdefault(app.get("candidate_id"), app.get("source") or "unknown")
    for candidate in selected:
        source_by_candidate.setdefault(candidate["_id"], candidate.get("source") or "unknown")
    source_values = [{
        "website": "官网投递", "job_site": "招聘网站", "campus": "校园招聘",
        "referral": "内部推荐", "headhunt": "猎头", "manual": "手动录入",
    }.get(source, "其他") for source in source_by_candidate.values()]
    channel = _profile_distribution(source_values, channel_order)
    school_rows = [
        {"name": name, "value": value}
        for name, value in sorted(schools.items(), key=lambda item: (-item[1], item[0]))[:30]
    ]
    employers = defaultdict(int)
    professions = defaultdict(int)
    for candidate in selected:
        employer = str(_latest_work_record(candidate).get("company") or "未知").strip()
        employers[employer] += 1
        profession = _candidate_profession(candidate)
        professions[profession] += 1
    employer_rows = [
        {"name": name, "value": value}
        for name, value in sorted(employers.items(), key=lambda item: (-item[1], item[0]))[:30]
    ]
    profession_rows = [
        {"name": name, "value": value}
        for name, value in sorted(professions.items(), key=lambda item: (-item[1], item[0]))[:30]
    ]
    return {
        "total": len(selected),
        "gender": gender,
        "work_experience": work,
        "age": age,
        "highest_education": highest_education,
        "channel_type": channel,
        "graduation_school": school_rows,
        "latest_employer": employer_rows,
        "profession": profession_rows,
    }


@bp.get("/talent-profile")
@role_required(HR)
def talent_profile_report():
    return ok(_talent_profile_data(_filters()))


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
