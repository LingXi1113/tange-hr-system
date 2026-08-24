"""招聘流程阶段定义。

默认流程：新简历→业务复筛→一面→二面→三面→HR面试→录用审批→Offer→待入职→入职；
终态分支：淘汰、人才库；可选插入环节：笔试、测评、背调、复试、自定义。
锁定期默认天数不在此写死，取自系统参数 lock_days_default（见 models/system.py）。
"""

# (stage_key, 名称, 环节类型, 是否默认阶段, 必选, 可跳过, 提醒类型)
# PRD v1.1 默认流程（9 阶段）
DEFAULT_STAGES = [
    ("new_resume", "新简历", "开始", True, True, False, "enter"),
    ("pending_screen", "待筛选", "筛选", True, True, False, "enter"),
    ("hr_screen_passed", "HR筛选通过", "筛选", True, True, False, "enter"),
    ("pending_interview", "待面试", "面试", True, True, False, "enter"),
    ("interviewing", "面试中", "面试", True, True, False, "enter"),
    ("interview_passed", "面试通过", "面试", True, True, False, "enter"),
    ("offer_pending", "Offer中", "Offer", True, True, False, "offer_expire"),
    ("pending_onboard", "待入职", "入职", True, True, False, "onboard"),
    ("onboarded", "已入职", "结束", True, True, False, ""),
]

# v1.0 旧阶段（兼容映射：历史数据保留，仍可展示与流转，不再作为新模板默认）
LEGACY_STAGES = [
    ("business_screen", "业务复筛", "筛选"),
    ("interview_1", "一面", "面试"),
    ("interview_2", "二面", "面试"),
    ("interview_3", "三面", "面试"),
    ("hr_interview", "HR面试", "面试"),
    ("offer_approval", "录用审批", "审批"),
    ("offer", "Offer", "Offer"),
]

# 可选插入环节（按职位配置插入）
OPTIONAL_STAGES = [
    ("written_test", "笔试", "可选插入", 3),
    ("assessment", "测评", "可选插入", 3),
    ("background_check", "背调", "可选插入", 7),
    ("re_interview", "复试", "可选插入", 5),
    ("custom", "自定义", "可选插入", 0),
]

# 终态分支（PRD v1.1：淘汰、放弃、人才库）
TERMINAL_STAGES = [
    ("eliminated", "淘汰", "终态"),
    ("abandoned", "放弃", "终态"),
    ("talent_pool", "人才库", "终态"),
]

# 合法阶段键 = v1.1 默认 + 可选环节 + 终态 + v1.0 旧阶段（兼容历史数据）
STAGE_KEYS = [s[0] for s in DEFAULT_STAGES] + [s[0] for s in OPTIONAL_STAGES] \
    + [s[0] for s in TERMINAL_STAGES] + [s[0] for s in LEGACY_STAGES]

STAGE_NAMES = {s[0]: s[1] for s in DEFAULT_STAGES} \
    | {s[0]: s[1] for s in OPTIONAL_STAGES} \
    | {s[0]: s[1] for s in TERMINAL_STAGES} \
    | {s[0]: s[1] for s in LEGACY_STAGES}

# 系统参数 key
PARAM_LOCK_DAYS_DEFAULT = "lock_days_default"
PARAM_ONBOARDING_CHECKLIST_DEFAULT = "onboarding_checklist_default"

# 锁定期默认天数（仅作为系统参数缺失时的最终兜底；正常运行以系统参数为准）
LOCK_DAYS_FALLBACK = {
    # v1.1 默认阶段（默认不锁定，可通过系统参数调整）
    "new_resume": 0, "pending_screen": 5, "hr_screen_passed": 0,
    "pending_interview": 7, "interviewing": 7, "interview_passed": 30,
    "offer_pending": 15, "pending_onboard": 45, "onboarded": 9999,
    # v1.0 旧阶段（兼容历史数据）
    "business_screen": 3,
    "interview_1": 5, "interview_2": 5, "interview_3": 5, "hr_interview": 3,
    "offer_approval": 7, "offer": 0,
    # 可选环节
    "written_test": 3, "assessment": 3, "background_check": 7,
    "re_interview": 5, "custom": 0,
}

# 招聘阶段规则默认值。规则直接保存在流程模板的 stages 数组中，
# 这里仅用于新建模板和兼容历史模板缺失字段的兜底。
STAGE_RULE_FALLBACK = {
    "new_resume": {"unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered"},
    "pending_screen": {"unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered"},
    "hr_screen_passed": {"unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered"},
    "pending_interview": {"unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered"},
    "interviewing": {
        "unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered",
        "requires_interview": True, "requires_feedback": True,
    },
    "interview_passed": {
        "unprocessed_days": 15, "expiry_action": "eliminated", "deadline_basis": "stage_entered",
        "enter_talent_pool": True, "reminder_days_before": 3,
    },
    "offer_pending": {"unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered"},
    "pending_onboard": {
        "unprocessed_days": 90, "expiry_action": "abandoned", "deadline_basis": "planned_onboard_date",
        "enter_talent_pool": True, "reminder_days_before": 7,
    },
    "onboarded": {"unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered"},
    "business_screen": {"unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered"},
    "interview_1": {
        "unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered",
        "requires_interview": True, "requires_feedback": True,
    },
    "interview_2": {
        "unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered",
        "requires_interview": True, "requires_feedback": True,
    },
    "interview_3": {
        "unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered",
        "requires_interview": True, "requires_feedback": True,
    },
    "hr_interview": {
        "unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered",
        "requires_interview": True, "requires_feedback": True,
    },
    "re_interview": {
        "unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered",
        "requires_interview": True, "requires_feedback": True,
    },
    "offer_approval": {
        "unprocessed_days": 15, "expiry_action": "eliminated", "deadline_basis": "stage_entered",
        "enter_talent_pool": True,
    },
    "offer": {"unprocessed_days": 0, "expiry_action": "none", "deadline_basis": "stage_entered"},
}

EXPIRY_ACTIONS = ("none", "eliminated", "abandoned", "talent_pool")
DEADLINE_BASES = ("stage_entered", "planned_onboard_date")

ONBOARDING_CHECKLIST_FALLBACK = [
    "证件照", "学历证明", "离职证明", "体检报告", "银行卡信息", "入职登记表",
]

INTERVIEW_ROUNDS = ["一面", "二面", "三面", "HR面试", "复试"]
