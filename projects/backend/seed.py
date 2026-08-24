"""演示数据初始化（MongoDB 版，幂等）。

系统参数、字典、默认流程模板、评价模板示例、Offer 审批人配置、操作日志示例。
"""
import json
from datetime import datetime, timedelta

from common.db import col, next_id
from common.stages import (
    DEFAULT_STAGES,
    LOCK_DAYS_FALLBACK,
    ONBOARDING_CHECKLIST_FALLBACK,
    OPTIONAL_STAGES,
    PARAM_LOCK_DAYS_DEFAULT,
    PARAM_ONBOARDING_CHECKLIST_DEFAULT,
    STAGE_RULE_FALLBACK,
)

DICT_SEED = {
    "source_channel": [
        ("website", "官网投递"), ("referral", "内部推荐"), ("headhunt", "猎头"),
        ("job_site", "招聘网站"), ("campus", "校园招聘"), ("manual", "手动录入"),
    ],
    "request_type": [("new_headcount", "新增编制"), ("replacement", "替补"), ("temp_project", "临时项目")],
    "job_level": [("P4", "P4"), ("P5", "P5"), ("P6", "P6"), ("P7", "P7"), ("P8", "P8")],
    "eliminate_reason": [
        ("skill_mismatch", "能力不匹配"), ("salary_mismatch", "薪资不匹配"),
        ("personal_reason", "个人原因"), ("bg_check_failed", "背调不通过"), ("other", "其他"),
    ],
    "pool_category": [("tech", "技术类"), ("product", "产品类"), ("sales", "销售类"), ("general", "综合类")],
    "job_type": [("full_time", "全职"), ("part_time", "兼职"), ("intern", "实习"), ("outsource", "外包")],
}


def seed_demo_data():
    now = datetime.now()

    if col("operation_logs").count_documents({}) == 0:
        col("operation_logs").insert_one({
            "_id": next_id("operation_logs"),
            "biz_type": "system", "biz_id": "seed", "action": "seed_demo_data",
            "operator_id": "system", "operator_name": "系统",
            "detail": "初始化演示数据", "created_at": now,
        })

    # 系统参数：锁定期默认天数（模板与看板以此为准，不写死）
    if col("sys_params").find_one({"_id": PARAM_LOCK_DAYS_DEFAULT}) is None:
        col("sys_params").insert_one({
            "_id": PARAM_LOCK_DAYS_DEFAULT,
            "value": json.dumps(LOCK_DAYS_FALLBACK, ensure_ascii=False),
            "remark": "各阶段锁定期默认天数（0=不锁定）",
        })
    if col("sys_params").find_one({"_id": PARAM_ONBOARDING_CHECKLIST_DEFAULT}) is None:
        col("sys_params").insert_one({
            "_id": PARAM_ONBOARDING_CHECKLIST_DEFAULT,
            "value": json.dumps(ONBOARDING_CHECKLIST_FALLBACK, ensure_ascii=False),
            "remark": "入职资料清单默认条目",
        })

    # 字典
    if col("dict_items").count_documents({}) == 0:
        docs = []
        for type_, entries in DICT_SEED.items():
            for sort, (code, name) in enumerate(entries):
                docs.append({
                    "_id": next_id("dict_items"), "type": type_, "code": code,
                    "name": name, "enabled": True, "sort": sort,
                    "created_at": now, "updated_at": now,
                })
        col("dict_items").insert_many(docs)

    # 默认流程模板：PRD v1.1 九阶段 + 可选插入环节（旧 v1.0 模板停用保留，不删除）
    lock_raw = col("sys_params").find_one({"_id": PARAM_LOCK_DAYS_DEFAULT})
    lock_defaults = json.loads(lock_raw["value"]) if lock_raw else dict(LOCK_DAYS_FALLBACK)
    if col("pipeline_templates").find_one({"name": "默认招聘流程模板（v1.1）"}) is None:
        stages = []
        for order, (key, name, category, _d, required, skippable, remind) in enumerate(DEFAULT_STAGES, 1):
            stages.append({
                "stage_key": key, "name": name, "category": category,
                "sort_order": order, "lock_days": int(lock_defaults.get(key, 0)),
                **STAGE_RULE_FALLBACK.get(key, {}),
                "required": required, "skippable": skippable,
                "reminder_type": remind, "optional_flag": False,
            })
        for key, name, category, _lock in OPTIONAL_STAGES:
            stages.append({
                "stage_key": key, "name": name, "category": category,
                "sort_order": 0, "lock_days": int(lock_defaults.get(key, 0)),
                "required": False, "skippable": False, "reminder_type": "",
                "optional_flag": True,
            })
        col("pipeline_templates").insert_one({
            "_id": next_id("pipeline_templates"),
            "name": "默认招聘流程模板（v1.1）", "status": "active",
            "remark": "PRD v1.1 默认九阶段流程",
            "stage_rules_enabled": True,
            "stages": stages, "created_at": now, "updated_at": now,
        })
        # 旧 v1.0 默认模板停用但保留（历史职位仍按 template_id 引用）
        col("pipeline_templates").update_many(
            {"name": "默认招聘流程模板"}, {"$set": {"status": "disabled", "updated_at": now}})

    # 历史 v1.1 模板补齐阶段规则字段，并将默认客保时长迁移到新规则。
    v11_name = "默认招聘流程模板（v1.1）"
    for tpl in col("pipeline_templates").find({"name": v11_name}):
        stages = list(tpl.get("stages", []))
        changed = False
        for stage in stages:
            key = stage.get("stage_key", "")
            defaults = STAGE_RULE_FALLBACK.get(key, {})
            for field, value in defaults.items():
                if field not in stage:
                    stage[field] = value
                    changed = True
            if "lock_days" not in stage or not tpl.get("stage_rules_enabled"):
                if key in LOCK_DAYS_FALLBACK and stage.get("lock_days") != LOCK_DAYS_FALLBACK[key]:
                    stage["lock_days"] = LOCK_DAYS_FALLBACK[key]
                    changed = True
        if not tpl.get("stage_rules_enabled"):
            changed = True
        if changed:
            col("pipeline_templates").update_one(
                {"_id": tpl["_id"]},
                {"$set": {"stages": stages, "stage_rules_enabled": True, "updated_at": now}},
            )

    # 评价模板示例
    if col("eval_templates").count_documents({}) == 0:
        samples = [
            ("通用面试评价模板", ["专业能力", "沟通表达", "业务理解", "团队协作", "价值观匹配"],
             [("", "一面")]),
            ("技术序列终面评价模板", ["专业能力", "架构能力", "业务理解", "价值观匹配"],
             [("", "三面"), ("", "HR面试")]),
        ]
        for name, dims, binds in samples:
            col("eval_templates").insert_one({
                "_id": next_id("eval_templates"),
                "name": name, "remark": "",
                "dimensions": [{"name": d, "sort_order": i + 1} for i, d in enumerate(dims)],
                "bindings": [{"job_id": "", "job_name": jn, "round": r} for jn, r in binds],
                "created_at": now, "updated_at": now,
            })

    # Offer 审批人配置（默认取 Mock 平台对应角色）
    if col("offer_approver_config").find_one({"_id": 1}) is None:
        col("offer_approver_config").insert_one({
            "_id": 1,
            "org_approver_id": "org-001", "org_approver_name": "陈静",
            "gm_id": "gm-001", "gm_name": "赵敏",
            "chairman_id": "chairman-001", "chairman_name": "孙浩",
            "offer_sender_id": "offer-001", "offer_sender_name": "周婷",
            "created_at": now, "updated_at": now,
        })

    # 业务演示数据：只在开发环境生成一次，避免重启时重复堆积。
    # 这些数据相互关联，覆盖招聘需求、职位、候选人、流程、面试、Offer、
    # 审批、入职、人才库、通知、报表和操作日志等页面。
    seed_demo_business_data(now)


DEMO_BUSINESS_MARKER = "demo_business_data_v1"


def _demo_insert(collection: str, document: dict, created_at: datetime):
    """插入一条带统一时间字段的演示数据，并使用项目自增 ID。"""
    document = dict(document)
    document.setdefault("_id", next_id(collection))
    document.setdefault("created_at", created_at)
    document.setdefault("updated_at", created_at)
    col(collection).insert_one(document)
    return document


def _demo_log(now: datetime, biz_type: str, biz_id, action: str,
              detail: str, operator_id: str = "hr-001", operator_name: str = "张薇"):
    _demo_insert("operation_logs", {
        "biz_type": biz_type, "biz_id": str(biz_id), "action": action,
        "operator_id": operator_id, "operator_name": operator_name,
        "detail": detail,
    }, now)


def seed_demo_business_data(now: datetime | None = None):
    """创建可从前端各菜单直接查看的业务演示数据（幂等）。"""
    now = now or datetime.now()
    if col("sys_params").find_one({"_id": DEMO_BUSINESS_MARKER}):
        # 兼容已初始化过旧演示数据的本地数据库：补齐后续版本新增字段。
        col("jobs").update_many(
            {"code": {"$in": ["JOB-DEMO-BE", "JOB-DEMO-FE", "JOB-DEMO-SALES"]},
             "interview_rounds": {"$exists": False}},
            {"$set": {"interview_rounds": ["一面", "二面", "三面"]}},
        )
        return

    day = timedelta(days=1)
    template = col("pipeline_templates").find_one(
        {"name": "默认招聘流程模板（v1.1）", "status": "active"})
    template_id = template.get("_id") if template else None

    # 1. 招聘需求：覆盖草稿、待确认、招聘中、暂停、已完成、已关闭。
    requirement_specs = [
        ("研发中心后端扩编", "dept-backend", "后端研发组", 3, "new_headcount", "high", "recruiting", now + 21 * day),
        ("产品经理替补招聘", "dept-tech", "技术中心", 1, "replacement", "mid", "pending_confirm", now + 30 * day),
        ("暑期实习生招聘", "dept-hr", "人力资源部", 5, "temp_project", "low", "draft", now + 60 * day),
        ("销售团队补充招聘", "dept-tech", "技术中心", 2, "new_headcount", "high", "paused", now + 7 * day),
        ("数据平台年度招聘", "dept-tech", "技术中心", 2, "new_headcount", "mid", "completed", now - 10 * day),
        ("已关闭的设计岗位", "dept-tech", "技术中心", 1, "replacement", "low", "closed", now - 40 * day),
    ]
    requirements = {}
    for index, (name, dept_id, dept_name, headcount, request_type, priority,
                status, due_date) in enumerate(requirement_specs, 1):
        req = _demo_insert("requirements", {
            "name": name, "dept_id": dept_id, "dept_name": dept_name,
            "headcount": headcount, "request_type": request_type,
            "priority": priority, "due_date": due_date,
            "owner_id": "hr-001", "owner_name": "张薇",
            "reason": "业务团队扩张与关键岗位补充",
            "requirements": "熟悉相关业务，有良好的沟通协作能力；具备 3 年以上相关经验。",
            "remark": f"演示需求 {index}", "status": status,
        }, now - (12 - index) * day)
        requirements[f"r{index}"] = req

    # 2. 职位：至少一个可公开投递的招聘中职位，并覆盖其他状态。
    job_specs = [
        ("JOB-DEMO-BE", "高级后端工程师", requirements["r1"], "recruiting", "上海", "P6", 2, "35-50K"),
        ("JOB-DEMO-FE", "前端工程师", requirements["r1"], "recruiting", "上海", "P5", 2, "25-38K"),
        ("JOB-DEMO-PM", "产品经理", requirements["r2"], "pending_publish", "上海", "P6", 1, "30-45K"),
        ("JOB-DEMO-INTERN", "人力资源实习生", requirements["r3"], "draft", "北京", "P4", 5, "150-200/天"),
        ("JOB-DEMO-SALES", "大客户销售经理", requirements["r4"], "paused", "深圳", "P6", 2, "20-35K"),
        ("JOB-DEMO-CLOSED", "交互设计师", requirements["r6"], "closed", "上海", "P5", 1, "25-35K"),
    ]
    jobs = {}
    for index, (code, name, req, status, location, level, headcount, salary) in enumerate(job_specs, 1):
        job = _demo_insert("jobs", {
            "code": code, "name": name, "dept_id": req["dept_id"],
            "dept_name": req["dept_name"], "location": location,
            "job_type": "full_time", "level": level, "report_to": "技术总监",
            "headcount": headcount, "salary_range": salary,
            "description": f"负责{ name }相关工作，参与核心项目建设和团队协作。",
            "qualification": "本科及以上学历，相关专业，具备良好的学习和沟通能力。",
            "skill_tags": "Python, MongoDB, 团队协作" if "后端" in name else "业务分析, 沟通协作",
            "interview_rounds": ["一面", "二面", "三面"] if index in (1, 2, 5) else ["一面"],
            "template_id": template_id, "channels": "官网投递,内部推荐",
            "requirement_id": req["_id"], "owner_id": "hr-001", "owner_name": "张薇",
            "status": status, "public_token": f"demo-public-{index}",
            "stage_configs": [
                {"stage_key": "assessment", "enabled": index == 1, "required": False, "after_key": "pending_screen"},
                {"stage_key": "background_check", "enabled": index == 1, "required": False, "after_key": "interview_passed"},
            ],
        }, now - (10 - index) * day)
        jobs[f"j{index}"] = job

    # 3. 候选人主档：有完整简历解析结果字段，便于查看和编辑维护。
    candidate_specs = [
        ("林远", "男", "13810000001", "lin.yuan@example.com", "上海", "内部推荐", "后端,Python,高潜"),
        ("周宁", "女", "13810000002", "zhou.ning@example.com", "杭州", "官网投递", "后端,Java"),
        ("陈默", "男", "13810000003", "chen.mo@example.com", "上海", "招聘网站", "全栈,React"),
        ("赵晴", "女", "13810000004", "zhao.qing@example.com", "苏州", "猎头", "后端,架构"),
        ("孙哲", "男", "13810000005", "sun.zhe@example.com", "上海", "内部推荐", "后端,管理"),
        ("韩雪", "女", "13810000006", "han.xue@example.com", "上海", "官网投递", "产品,数据分析"),
        ("吴昊", "男", "13810000007", "wu.hao@example.com", "南京", "招聘网站", "产品,AI"),
        ("杨帆", "女", "13810000008", "yang.fan@example.com", "上海", "校园招聘", "前端,TypeScript"),
        ("郑凯", "男", "13810000009", "zheng.kai@example.com", "深圳", "猎头", "销售,ToB"),
        ("蒋欣", "女", "13810000010", "jiang.xin@example.com", "北京", "内部推荐", "设计,交互"),
        ("何川", "男", "13810000011", "he.chuan@example.com", "上海", "官网投递", "后端,云原生"),
        ("顾婉", "女", "13810000012", "gu.wan@example.com", "上海", "手动录入", "HR,招聘"),
        ("徐立", "男", "13810000013", "xu.li@example.com", "上海", "招聘网站", "后端,微服务"),
        ("许安", "女", "13810000014", "xu.an@example.com", "杭州", "内部推荐", "后端,数据"),
    ]
    candidates = {}
    for index, (name, gender, phone, email, city, source, tags) in enumerate(candidate_specs, 1):
        candidate = _demo_insert("candidates", {
            "name": name, "gender": gender, "phone": phone, "email": email,
            "city": city, "tags": tags, "source": source,
            "remark": "演示候选人，可在详情页维护简历信息。",
            "owner_id": "hr-001", "owner_name": "张薇",
            "education": [{"school": "华东理工大学", "major": "计算机科学与技术", "degree": "本科",
                           "start_date": "2016-09", "end_date": "2020-06"}],
            "work_experience": [{"company": "示例科技有限公司", "position": "高级工程师",
                                 "start_date": "2020-07", "end_date": "至今",
                                 "description": "负责招聘系统和数据平台建设。"}],
        }, now - (18 - min(index, 12)) * day)
        candidates[f"c{index}"] = candidate

    # 4. 应聘记录：铺满流程看板各主要阶段和终态。
    app_specs = [
        ("c1", "j1", "pending_screen", "in_progress", 5),
        ("c2", "j1", "hr_screen_passed", "in_progress", 4),
        ("c3", "j1", "pending_interview", "in_progress", 3),
        ("c4", "j1", "interviewing", "in_progress", 3),
        ("c5", "j1", "interview_passed", "in_progress", 2),
        ("c6", "j1", "offer_pending", "in_progress", 2),
        ("c7", "j1", "pending_onboard", "pending_onboard", 1),
        ("c8", "j2", "onboarded", "onboarded", 20),
        ("c9", "j1", "eliminated", "eliminated", 15),
        ("c10", "j1", "talent_pool", "closed", 12),
        ("c11", "j5", "pending_screen", "in_progress", 4),
        ("c12", "j2", "new_resume", "in_progress", 1),
        ("c13", "j1", "offer_pending", "in_progress", 2),
        ("c14", "j1", "interview_passed", "in_progress", 4),
    ]
    applications = {}
    for index, (candidate_key, job_key, stage, status, age_days) in enumerate(app_specs, 1):
        created = now - age_days * day
        app = _demo_insert("applications", {
            "candidate_id": candidates[candidate_key]["_id"], "job_id": jobs[job_key]["_id"],
            "source": candidates[candidate_key].get("source", "manual"),
            "current_stage": stage, "owner_id": "hr-001", "owner_name": "张薇",
            "stage_entered_at": created + day, "status": status,
            "eliminate_reason": "技术栈与岗位要求不匹配" if stage == "eliminated" else "",
            "expected_salary": "35K", "onboard_time": "2026-09-15" if stage == "pending_onboard" else "",
            "version": 2 if stage != "new_resume" else 1,
        }, created)
        applications[f"a{index}"] = app

    # 阶段流转历史，供候选人详情、报表招聘周期和审计查看。
    main_stage_order = ["new_resume", "pending_screen", "hr_screen_passed", "pending_interview",
                        "interviewing", "interview_passed", "offer_pending", "pending_onboard", "onboarded"]
    for app_key, app in applications.items():
        current = app["current_stage"]
        if current in main_stage_order:
            target_index = main_stage_order.index(current)
            path = main_stage_order[:target_index + 1]
        elif current in ("eliminated", "talent_pool"):
            path = main_stage_order[:3] + [current]
        else:
            path = ["new_resume", current]
        for step, (from_stage, to_stage) in enumerate(zip(path, path[1:]), 1):
            _demo_insert("stage_transitions", {
                "application_id": app["_id"], "from_stage": from_stage, "to_stage": to_stage,
                "reason": "演示流程推进", "operator_id": "hr-001", "operator_name": "张薇",
            }, app["created_at"] + step * day / 2)

    # 客保锁定：三个不同阶段的有效锁，便于验证锁定提示和强制解锁。
    for app_key, stage_key, days in (("a1", "pending_screen", 3), ("a5", "interview_passed", 20), ("a7", "pending_onboard", 35)):
        app = applications[app_key]
        _demo_insert("lock_records", {
            "application_id": app["_id"], "candidate_id": app["candidate_id"],
            "stage_key": stage_key, "start_at": now - day,
            "end_at": now + days * day, "released": False,
            "auto_released": False, "force_unlocked": False,
            "unlock_reason": "", "unlock_operator_id": "", "unlock_operator_name": "",
        }, now - day)

    # 5. 面试：覆盖待安排、已邀请、已确认、已完成、已取消、已改期和反馈。
    interview_specs = [
        ("a3", "一面", "video", "confirmed", now + day, "刘洋"),
        ("a4", "一面", "onsite", "completed", now - 3 * day, "刘洋"),
        ("a5", "二面", "video", "pending", now + 2 * day, "王强"),
        ("a2", "HR面试", "phone", "invited", now + timedelta(hours=4), "张薇"),
        ("a9", "一面", "onsite", "cancelled", now - 2 * day, "刘洋"),
        ("a12", "一面", "video", "rescheduled", now + 3 * day, "刘洋"),
    ]
    interviews = {}
    for index, (app_key, round_name, iv_type, status, start_at, interviewer) in enumerate(interview_specs, 1):
        app = applications[app_key]
        iv = _demo_insert("interviews", {
            "candidate_id": app["candidate_id"], "job_id": app["job_id"], "application_id": app["_id"],
            "round": round_name, "type": iv_type, "start_at": start_at,
            "end_at": start_at + timedelta(hours=1), "location": "上海办公室" if iv_type == "onsite" else "",
            "meeting_link": "https://meeting.example.com/demo-room" if iv_type == "video" else "",
            "interviewer_name": interviewer, "interviewer_contact": "interviewer-001",
            "template_id": None, "remark": "演示面试记录", "status": status,
            "version": 1, "reschedule_history": [{"reason": "候选人时间调整", "updated_at": now - day}] if status == "rescheduled" else [],
        }, start_at - timedelta(hours=2))
        interviews[f"i{index}"] = iv
    _demo_insert("interview_feedback", {
        "interview_id": interviews["i2"]["_id"],
        "dimension_scores": [{"name": "专业能力", "score": 4}, {"name": "沟通表达", "score": 5}],
        "conclusion": "pass", "comment": "技术基础扎实，沟通清晰，建议进入下一阶段。",
        "risk_note": "暂无", "suggested_salary": "40K", "evaluator_id": "interviewer-001",
        "evaluator_name": "刘洋", "skip_eval": False,
    }, now - 2 * day)

    # 6. Offer：覆盖草稿、待发送、已发送、已接受、已拒绝、已过期。
    offer_specs = [
        ("a5", "draft", "高级后端工程师", "40K", now + 14 * day, now + 20 * day),
        ("a6", "pending_send", "高级后端工程师", "42K", now + 10 * day, now + 12 * day),
        ("a13", "sent", "高级后端工程师", "45K", now + 7 * day, now + 2 * day),
        ("a7", "accepted", "高级后端工程师", "43K", now + 5 * day, now + 30 * day),
        ("a8", "accepted", "前端工程师", "32K", now - 5 * day, now + 30 * day),
        ("a14", "rejected", "高级后端工程师", "38K", now + 8 * day, now + 5 * day),
        ("a10", "expired", "高级后端工程师", "36K", now - 8 * day, now - 2 * day),
    ]
    offers = {}
    for index, (app_key, status, position, salary, onboard_date, valid_until) in enumerate(offer_specs, 1):
        app = applications[app_key]
        offer = _demo_insert("offers", {
            "candidate_id": app["candidate_id"], "job_id": app["job_id"], "application_id": app["_id"],
            "dept": "技术中心", "position": position, "onboard_date": onboard_date,
            "location": "上海", "salary": salary, "probation": "3个月",
            "contract_term": "3年", "benefits": "五险一金、补充医疗、年度奖金",
            "valid_until": valid_until, "remark": "演示 Offer，可测试状态流转。",
            "status": status, "response_reason": "候选人已接受" if status == "accepted" else ("候选人暂不考虑" if status == "rejected" else ""),
            "file_id": None, "sent_at": now - day if status in ("sent", "accepted", "rejected") else None,
            "responded_at": now - timedelta(hours=6) if status in ("accepted", "rejected") else None,
            "version": 1, "created_by": "hr-001",
        }, now - (7 - min(index, 6)) * day)
        offers[f"o{index}"] = offer

    # 7. Offer 审批：一个待组织审批、一个已到总经理节点。
    config = col("offer_approver_config").find_one({"_id": 1}) or {}
    def approval_steps(current_index=0):
        names = [("org", "组织统筹审批", "org_approver_id", "org_approver_name"),
                 ("gm", "总经理审批", "gm_id", "gm_name"),
                 ("chairman", "董事长审批", "chairman_id", "chairman_name")]
        steps = []
        for index, (key, name, id_field, name_field) in enumerate(names):
            steps.append({"key": key, "name": name, "role": key + "_approver",
                          "approver_id": config.get(id_field, ""), "approver_name": config.get(name_field, ""),
                          "status": "approved" if index < current_index else ("pending" if index == current_index else "waiting"),
                          "reason": "演示审批已通过" if index < current_index else "", "acted_at": now - day if index < current_index else None})
        return steps
    for index, (offer_key, current_index) in enumerate((("o2", 0), ("o3", 1)), 1):
        offer = offers[offer_key]
        _demo_insert("offer_approvals", {
            "offer_id": offer["_id"], "status": "pending", "current_index": current_index,
            "version": 1 + current_index, "steps": approval_steps(current_index),
            "created_by": "hr-001",
        }, now - (2 - index) * day)

    # 8. 入职办理：一条资料进行中、一条已完成。
    checklist_names = ["证件照", "学历证明", "离职证明", "体检报告", "银行卡信息", "入职登记表"]
    for app_key, offer_key, status in (("a7", "o4", "in_progress"), ("a8", "o5", "completed")):
        app = applications[app_key]
        checklist = []
        for index, name in enumerate(checklist_names, 1):
            item_status = "verified" if status == "completed" or index <= 2 else ("submitted" if index == 3 else "pending")
            checklist.append({"key": f"item_{index}", "name": name, "status": item_status,
                              "remark": "演示资料已核验" if item_status == "verified" else "",
                              "updated_at": now - day if item_status != "pending" else None,
                              "verified_at": now - day if item_status == "verified" else None})
        _demo_insert("onboarding_records", {
            "application_id": app["_id"], "candidate_id": app["candidate_id"], "job_id": app["job_id"],
            "offer_id": offers[offer_key]["_id"], "planned_date": now + (5 if status != "completed" else -5) * day,
            "status": status, "checklist": checklist,
            "notes": "入职资料演示记录", "owner_id": "ssc-001", "owner_name": "吴迪",
        }, now - day)

    # 9. 人才库：淘汰入库、Offer 拒绝入库、手动入库三种来源。
    pool_specs = [
        ("c9", "tech", ["后端", "可回访"], "elimination_added", "当前岗位匹配度不足，保留后续机会", jobs["j1"]["_id"]),
        ("c10", "product", ["产品", "优秀候选人"], "manual", "候选人主动进入人才库", jobs["j3"]["_id"]),
        ("c14", "tech", ["后端", "Offer拒绝"], "offer_rejected", "薪资期望差异，建议三个月后回访", jobs["j1"]["_id"]),
    ]
    for candidate_key, category, tags, source, reason, recommended_job_id in pool_specs:
        _demo_insert("talent_pool", {
            "candidate_id": candidates[candidate_key]["_id"], "category": category,
            "tags": tags, "source": source, "reason": reason,
            "recommended_job_id": recommended_job_id, "last_contact_at": now - 2 * day,
            "status": "active", "added_by": "hr-001",
        }, now - 3 * day)

    # 10. 站内通知：让工作台、通知铃铛和通知列表一打开就有内容。
    notification_specs = [
        ("new_candidate", "新候选人进入流程", "林远投递了高级后端工程师，请安排筛选", "candidate", candidates["c1"]["_id"], f"/candidates/{candidates['c1']['_id']}", None),
        ("interview_remind", "面试即将开始", "陈默的一面将在明天开始，请提前准备", "interview", interviews["i1"]["_id"], "/interviews", None),
        ("feedback_pending", "面试反馈待填写", "请补充已完成面试的评价结论", "interview", interviews["i2"]["_id"], "/interviews", now - day),
        ("offer_expiring", "Offer 即将过期", "已发送 Offer 的有效期即将截止，请跟进候选人", "offer", offers["o3"]["_id"], "/offers", None),
        ("requirement_overdue", "招聘需求已逾期", "研发中心后端扩编需求需要跟进", "requirement", requirements["r1"]["_id"], f"/requirements/{requirements['r1']['_id']}", None),
    ]
    for index, (scene, title, content, biz_type, biz_id, route, read_at) in enumerate(notification_specs, 1):
        for receiver_id in ("hr-001", "hr-002"):
            _demo_insert("notifications", {
                "receiver_id": receiver_id, "scene": scene, "title": title,
                "content": content, "biz_type": biz_type, "biz_id": str(biz_id),
                "route": route, "dedupe_key": f"demo:{index}:{receiver_id}",
                "read_at": read_at,
            }, now - index * timedelta(hours=2))

    # 11. 额外操作日志，让需求详情、候选人详情、审计日志和工作台活动流有内容。
    _demo_log(now - 2 * day, "requirement", requirements["r1"]["_id"], "submit", "提交后端扩编招聘需求")
    _demo_log(now - day, "job", jobs["j1"]["_id"], "publish", "职位已发布到官网投递渠道")
    _demo_log(now - timedelta(hours=8), "candidate", candidates["c1"]["_id"], "update", "补充教育经历和工作经历")
    _demo_log(now - timedelta(hours=4), "interview", interviews["i2"]["_id"], "feedback", "面试反馈：通过")
    _demo_log(now - timedelta(hours=2), "offer", offers["o3"]["_id"], "send", "已发送 Offer，等待候选人响应")

    # 12. 补充一个非默认评价模板，便于模板页面查看多条记录。
    if col("eval_templates").find_one({"name": "产品岗位结构化面试模板"}) is None:
        _demo_insert("eval_templates", {
            "name": "产品岗位结构化面试模板", "remark": "演示评价模板",
            "dimensions": [{"name": name, "sort_order": index} for index, name in enumerate(
                ["产品思维", "数据分析", "沟通推动", "用户洞察"], 1)],
            "bindings": [{"job_id": jobs["j3"]["_id"], "job_name": jobs["j3"]["name"], "round": "一面"}],
        }, now - day)

    col("sys_params").insert_one({
        "_id": DEMO_BUSINESS_MARKER,
        "value": "1",
        "remark": "开发环境业务演示数据已初始化",
        "created_at": now,
        "updated_at": now,
    })
