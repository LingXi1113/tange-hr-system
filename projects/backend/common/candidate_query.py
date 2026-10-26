"""One request-scoped candidate snapshot for list filters, stage facets and dashboard counts."""
from collections import defaultdict

from common.db import col
from common.flow import active_lock_for_candidate, application_process_state
from common.stages import STAGE_NAMES

TALENT_RECOMMENDATION_SOURCES = {"referral", "headhunt", "talent_pool", "business_recommendation"}
SUBCATEGORY_FILTERS = {
    "category", "unprocessed", "unassigned", "assigned", "source_group",
    "recommendation_status", "action_state", "page", "page_size", "include_summary", "mask",
}


def stage_bucket(application):
    if not application:
        return "pending_screen"
    stage = application.get("current_stage", "pending_screen")
    round_name = application.get("interview_round", "")
    if stage in {"new_resume", "pending_screen", "hr_screen_passed"}:
        return "pending_screen"
    if stage in {"pending_interview", "interviewing", "interview_passed"}:
        if round_name == "二面":
            return "interview_2"
        if round_name in {"三面", "终面", "HR面试", "终面（HR）"}:
            return "interview_3"
        return "interview_1"
    return {"hr_interview": "interview_3", "offer": "offer_pending"}.get(stage, stage)


class CandidateQuery:
    def __init__(self):
        self.candidates = list(col("candidates").find({}).sort("_id", -1))
        self.jobs = {job["_id"]: job for job in col("jobs").find({}, {"name": 1, "dept_id": 1, "dept_name": 1})}
        self.apps = defaultdict(list)
        for application in col("applications").find({}).sort("_id", -1):
            self.apps[application["candidate_id"]].append(application)
        self._locks = {}
        self._states = {}
        self._recommendations = None

    def _recommendation_ids(self, status):
        if self._recommendations is None:
            self._recommendations = {"passed": set(), "failed": set()}
            for transition in col("stage_transitions").find({"from_stage": "business_screen"}):
                target = transition.get("to_stage")
                if target in {"pending_interview", "interviewing", "interview_1", "interview_2", "interview_3",
                              "hr_interview", "re_interview", "interview_passed", "hrbp_interview"}:
                    self._recommendations["passed"].add(transition.get("application_id"))
                elif target in {"eliminated", "abandoned", "talent_pool"}:
                    self._recommendations["failed"].add(transition.get("application_id"))
        return self._recommendations[status]

    def matching_applications(self, candidate, args):
        """None means no match; [] means a matching, genuinely unassigned person."""
        all_apps = self.apps[candidate["_id"]]
        apps = all_apps
        if args.get("job_id"):
            apps = [app for app in apps if str(app.get("job_id")) == str(args["job_id"])]
        if args.get("job_dept_id"):
            apps = [app for app in apps if self.jobs.get(app.get("job_id"), {}).get("dept_id") == args["job_dept_id"]]
        if (args.get("job_id") or args.get("job_dept_id") or args.get("assigned") == "1") and not apps:
            return None
        if args.get("unassigned") == "1" and all_apps:
            return None
        if args.get("highest_education") and candidate.get("highest_education") != args["highest_education"]:
            return None
        if args.get("tag") and str(args["tag"]).lower() not in str(candidate.get("tags") or "").lower():
            return None
        keyword = str(args.get("keyword") or "").strip().casefold()
        if keyword:
            text = [candidate.get(key, "") for key in ("name", "phone", "email", "major")]
            text += [record.get(key, "") for record in candidate.get("education") or [] for key in ("school", "major")]
            text += [record.get(key, "") for record in candidate.get("work_experience") or [] for key in ("company", "position")]
            matching_jobs = [app for app in apps if any(keyword in str(self.jobs.get(app.get("job_id"), {}).get(key) or "").casefold()
                                                       for key in ("name", "dept_name"))]
            if not any(keyword in str(value or "").casefold() for value in text):
                if not matching_jobs:
                    return None
                apps = matching_jobs
        if args.get("stage"):
            apps = [app for app in apps if stage_bucket(app) == args["stage"]]
            if not apps and (all_apps or args["stage"] != "pending_screen"):
                return None
        if args.get("unprocessed") == "1":
            apps = [app for app in apps if app.get("current_stage") in {"new_resume", "pending_screen"}
                    and app.get("status") == "in_progress"]
            if not apps:
                return None
        if args.get("category") == "pending" and "待定" not in (candidate.get("tags") or ""):
            return None
        if args.get("source"):
            if candidate.get("source") != args["source"]:
                apps = [app for app in apps if app.get("source") == args["source"]]
                if not apps:
                    return None
        if args.get("category") == "recommended" or args.get("source_group") == "talent_recommendation":
            if candidate.get("source") not in TALENT_RECOMMENDATION_SOURCES:
                apps = [app for app in apps if app.get("source") in TALENT_RECOMMENDATION_SOURCES]
                if not apps:
                    return None
        status = args.get("recommendation_status")
        if status == "pending":
            apps = [app for app in apps if app.get("current_stage") == "business_screen" and app.get("status") == "in_progress"]
            if not apps:
                return None
        elif status in {"passed", "failed"}:
            apps = [app for app in apps if app["_id"] in self._recommendation_ids(status)]
            if not apps:
                return None
        if args.get("action_state"):
            for app in apps:
                if app["_id"] not in self._states:
                    self._states[app["_id"]] = application_process_state(app)["key"]
            apps = [app for app in apps if self._states[app["_id"]] == args["action_state"]]
            if not apps:
                return None
        if args.get("locked") == "1":
            if candidate["_id"] not in self._locks:
                self._locks[candidate["_id"]] = bool(active_lock_for_candidate(candidate["_id"]))
            if not self._locks[candidate["_id"]]:
                return None
        return apps

    def filter(self, args):
        return [(candidate, apps[0] if apps else None) for candidate in self.candidates
                if (apps := self.matching_applications(candidate, args)) is not None]

    def summary(self, args):
        # Facet buttons replace one another, but never discard the selected stage or visible field filters.
        base = {key: value for key, value in args.items() if key not in SUBCATEGORY_FILTERS}
        stage_base = {key: value for key, value in base.items() if key != "stage"}
        stages = {stage_bucket(app) for applications in self.apps.values() for app in applications}
        stages.update(stage_bucket({"current_stage": stage}) for stage in STAGE_NAMES)
        stages.add("pending_screen")
        return {
            "total": len(self.filter(base)),
            "unassigned": len(self.filter({**base, "unassigned": "1"})),
            "stage_counts": {stage: len(self.filter({**stage_base, "stage": stage})) for stage in stages},
            "categories": {
                "unprocessed": len(self.filter({**base, "unprocessed": "1"})),
                "pending": len(self.filter({**base, "category": "pending"})),
                "recommended": len(self.filter({**base, "category": "recommended"})),
            },
        }
