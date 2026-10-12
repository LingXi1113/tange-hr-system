"""Explainable resume-to-job matching for the AI commerce recruiting workflow.

The engine deliberately uses only job-related evidence.  Identity attributes such
as name, gender, age, photo and marital status never participate in scoring.
"""
from __future__ import annotations

from copy import deepcopy
import re
from datetime import datetime


PROFILE_NAMES = {
    "tech": "技术研发",
    "product_ops": "产品与电商运营",
    "sales": "销售与商务",
}

PROFILE_WEIGHTS = {
    "tech": [
        ("核心技术能力", 35), ("AI能力", 20), ("电商业务经验", 15),
        ("项目成果", 15), ("相关工作经验", 10), ("学历与专业", 5),
    ],
    "product_ops": [
        ("电商业务经验", 25), ("产品或运营能力", 25), ("AI应用经验", 15),
        ("数据分析能力", 15), ("项目成果", 15), ("学历与专业", 5),
    ],
    "sales": [
        ("销售业绩", 25), ("行业匹配", 20), ("客户类型匹配", 15),
        ("销售能力", 15), ("客户与渠道资源", 10), ("销售周期经验", 10),
        ("学历及其他条件", 5),
    ],
}

EVALUATOR_NAMES = {
    "job_skills": "职位技能匹配",
    "ai": "AI能力关键词",
    "ecommerce": "电商行业关键词",
    "project_metrics": "项目与量化成果",
    "experience": "工作年限",
    "education": "学历要求",
    "product_ops": "产品/运营能力",
    "data": "数据分析能力",
    "sales_performance": "销售业绩",
    "sales_industry": "销售行业匹配",
    "customer_type": "客户类型",
    "sales_process": "销售流程能力",
    "resources": "客户与渠道资源",
    "sales_cycle": "销售周期经验",
    "custom_terms": "自定义关键词",
}

DEFAULT_MATCH_ITEMS = {
    "tech": [
        {"key": "core_skills", "name": "核心技术能力", "weight": 35, "evaluator": "job_skills", "target_count": 3},
        {"key": "ai", "name": "AI能力", "weight": 20, "evaluator": "ai", "target_count": 3},
        {"key": "ecommerce", "name": "电商业务经验", "weight": 15, "evaluator": "ecommerce", "target_count": 3},
        {"key": "project", "name": "项目成果", "weight": 15, "evaluator": "project_metrics", "target_count": 3},
        {"key": "experience", "name": "相关工作经验", "weight": 10, "evaluator": "experience", "target_count": 1},
        {"key": "education", "name": "学历与专业", "weight": 5, "evaluator": "education", "target_count": 1},
    ],
    "product_ops": [
        {"key": "ecommerce", "name": "电商业务经验", "weight": 25, "evaluator": "ecommerce", "target_count": 3},
        {"key": "product_ops", "name": "产品或运营能力", "weight": 25, "evaluator": "product_ops", "target_count": 3},
        {"key": "ai", "name": "AI应用经验", "weight": 15, "evaluator": "ai", "target_count": 2},
        {"key": "data", "name": "数据分析能力", "weight": 15, "evaluator": "data", "target_count": 3},
        {"key": "project", "name": "项目成果", "weight": 15, "evaluator": "project_metrics", "target_count": 3},
        {"key": "education", "name": "学历与专业", "weight": 5, "evaluator": "education", "target_count": 1},
    ],
    "sales": [
        {"key": "performance", "name": "销售业绩", "weight": 25, "evaluator": "sales_performance", "target_count": 2},
        {"key": "industry", "name": "行业匹配", "weight": 20, "evaluator": "sales_industry", "target_count": 2},
        {"key": "customer", "name": "客户类型匹配", "weight": 15, "evaluator": "customer_type", "target_count": 2},
        {"key": "sales_skills", "name": "销售能力", "weight": 15, "evaluator": "sales_process", "target_count": 3},
        {"key": "resources", "name": "客户与渠道资源", "weight": 10, "evaluator": "resources", "target_count": 1},
        {"key": "cycle", "name": "销售周期经验", "weight": 10, "evaluator": "sales_cycle", "target_count": 2},
        {"key": "education", "name": "学历及其他条件", "weight": 5, "evaluator": "education", "target_count": 1},
    ],
}

# 岗位级模板继承三类通用模板，但可在系统设置中分别维护。aliases 用于把职位名称
# 自动路由到对应模板；未命中的新职位仍回退到三类通用模板。
POSITION_TEMPLATES = {
    "ai_application_engineer": {
        "name": "AI应用工程师", "base_profile": "tech", "aliases": ["AI应用工程师"],
    },
    "senior_product_manager": {
        "name": "高级产品经理", "base_profile": "product_ops", "aliases": ["高级产品经理"],
    },
    "product_manager": {
        "name": "产品经理", "base_profile": "product_ops", "aliases": ["产品经理"],
    },
    "java_backend_engineer": {
        "name": "Java后端工程师", "base_profile": "tech", "aliases": ["Java后端工程师", "Java后端开发"],
    },
    "senior_backend_engineer": {
        "name": "高级后端工程师", "base_profile": "tech", "aliases": ["高级后端工程师"],
    },
    "backend_developer": {
        "name": "后台/后端开发", "base_profile": "tech", "aliases": ["后台开发", "后端开发"],
    },
    "frontend_development_engineer": {
        "name": "前端开发工程师", "base_profile": "tech", "aliases": ["前端开发工程师", "前端开发"],
    },
    "frontend_engineer": {
        "name": "前端工程师", "base_profile": "tech", "aliases": ["前端工程师"],
    },
    "key_account_sales_manager": {
        "name": "大客户销售经理", "base_profile": "sales", "aliases": ["大客户销售经理"],
    },
    "marketing_specialist": {
        "name": "市场专员", "base_profile": "product_ops", "aliases": ["市场专员"],
    },
    "financial_analysis_engineer": {
        "name": "财务分析工程师", "base_profile": "tech", "aliases": ["财务分析工程师"],
    },
    "hr_intern": {
        "name": "人力资源实习生", "base_profile": "product_ops", "aliases": ["人力资源实习生"],
    },
    "interaction_designer": {
        "name": "交互设计师", "base_profile": "product_ops", "aliases": ["交互设计师"],
    },
    "seo": {
        "name": "SEO", "base_profile": "product_ops", "aliases": ["SEO"],
    },
    "online_customer_service": {
        "name": "在线客服", "base_profile": "product_ops", "aliases": ["在线客服"],
    },
    "public_opinion_specialist": {
        "name": "舆情管控", "base_profile": "product_ops", "aliases": ["舆情管控"],
    },
    "graphic_content_operator": {
        "name": "图文运营", "base_profile": "product_ops", "aliases": ["图文运营", "图文"],
    },
    "video_content_operator": {
        "name": "视频运营", "base_profile": "product_ops", "aliases": ["视频运营", "视频"],
    },
    "solution_consultant": {
        "name": "方案顾问", "base_profile": "sales", "aliases": ["方案顾问"],
    },
    "business_development": {
        "name": "BD/商务拓展", "base_profile": "sales", "aliases": ["商务拓展", "BD"],
    },
}

MATCH_SCOPE_NAMES = {
    **PROFILE_NAMES,
    **{key: value["name"] for key, value in POSITION_TEMPLATES.items()},
}


def match_scope_base_profile(scope: str) -> str:
    if scope in PROFILE_NAMES:
        return scope
    return POSITION_TEMPLATES.get(scope, {}).get("base_profile", "tech")


def detect_match_scope(job: dict, profile: str | None = None) -> str:
    job_name = str(job.get("name") or "").strip().casefold()
    matches = []
    for key, template in POSITION_TEMPLATES.items():
        for alias in template["aliases"]:
            normalized = alias.casefold()
            if normalized and normalized in job_name:
                matches.append((len(normalized), key))
    if matches:
        return max(matches)[1]
    return profile if profile in PROFILE_NAMES else detect_profile(job)


def default_match_items(profile: str) -> list[dict]:
    """Return an isolated copy so callers can safely enrich the defaults."""
    return deepcopy(DEFAULT_MATCH_ITEMS.get(profile, DEFAULT_MATCH_ITEMS["tech"]))

AI_TERMS = [
    "AI", "人工智能", "大模型", "LLM", "RAG", "Agent", "智能体",
    "Prompt", "提示词", "Embedding", "向量数据库", "模型微调", "PyTorch",
    "LangChain", "数字人", "智能客服", "智能推荐",
]
ECOMMERCE_TERMS = [
    "电商", "电子商务", "直播电商", "跨境电商", "社交电商", "本地生活",
    "商品", "订单", "支付", "库存", "营销", "推荐系统", "搜索系统",
    "供应链", "商家", "店铺", "GMV", "转化率", "复购率",
]
TECH_TERMS = [
    "Java", "Python", "TypeScript", "React", "Vue", "Spring Boot", "Flask",
    "FastAPI", "MySQL", "Redis", "Kafka", "微服务", "Docker", "Kubernetes",
    "PyTorch", "SQL", "数据仓库", "推荐系统",
]
PRODUCT_OPS_TERMS = [
    "产品经理", "需求分析", "原型", "用户研究", "产品规划", "运营",
    "用户增长", "活动运营", "商家运营", "内容运营", "数据运营", "A/B测试",
]
DATA_TERMS = [
    "GMV", "转化率", "客单价", "复购率", "留存率", "获客成本", "ROI",
    "投产比", "活跃商家", "订单量", "用户增长", "A/B测试", "数据分析",
]
SALES_INDUSTRY_TERMS = [
    "AI", "人工智能", "大模型", "SaaS", "软件", "企业服务", "电商",
    "直播电商", "跨境电商", "互联网",
]
CUSTOMER_TERMS = [
    "大客户", "KA", "品牌客户", "品牌商家", "平台客户", "企业客户",
    "商家", "MCN", "达人", "渠道商", "政府客户", "中小企业",
]
SALES_PROCESS_TERMS = [
    "客户开发", "获客", "需求挖掘", "解决方案", "商务谈判", "投标",
    "签约", "合同", "回款", "续费", "CRM", "线索", "商机",
]
RESOURCE_TERMS = ["客户资源", "渠道资源", "生态资源", "客户关系", "人脉资源", "渠道合作"]
SALES_CYCLE_TERMS = ["销售周期", "客单价", "合同额", "单笔合同", "续费率", "回款周期"]

SYNONYM_GROUPS = [
    {"AI", "人工智能"}, {"大模型", "LLM", "Large Language Model"},
    {"Agent", "智能体", "AI Agent"}, {"Prompt", "提示词", "提示词工程"},
    {"Spring Boot", "SpringBoot"}, {"Kubernetes", "K8s"},
    {"SaaS", "软件即服务"}, {"电子商务", "电商"},
    {"MCN", "直播机构"}, {"客户管理系统", "CRM"},
    {"投产比", "ROI"}, {"A/B测试", "AB测试", "A/B Test"},
]

EDUCATION_LEVELS = {
    "初中": 1, "高中": 2, "中专": 2, "大专": 3,
    "本科": 4, "学士": 4, "硕士": 5, "研究生": 5, "博士": 6,
}


def _list(value) -> list[str]:
    if isinstance(value, list):
        values = value
    else:
        values = re.split(r"[,，;；\n]", str(value or ""))
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def detect_profile(job: dict) -> str:
    text = " ".join(str(job.get(key, "")) for key in (
        "name", "dept_name", "description", "qualification", "skill_tags",
    )).lower()
    if any(word in text for word in ["销售", "商务", "渠道", "客户经理", "bd", "招商主管"]):
        return "sales"
    if any(word in text for word in ["产品", "运营", "增长", "平台招商", "商家运营"]):
        return "product_ops"
    return "tech"


def _infer_education(job_text: str) -> str:
    matches = [degree for degree in EDUCATION_LEVELS if degree in job_text]
    return max(matches, key=lambda item: EDUCATION_LEVELS[item], default="")


def _infer_years(job_text: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*年(?:以上|及以上|工作|相关)?", job_text)
    return float(match.group(1)) if match else 0.0


def normalize_screening_rules(raw: dict | None, job: dict | None = None) -> dict:
    job = job or {}
    raw = raw if isinstance(raw, dict) else {}
    job_text = " ".join(str(job.get(key, "")) for key in (
        "name", "description", "qualification", "skill_tags",
    ))
    profile = raw.get("profile")
    if profile not in PROFILE_NAMES:
        profile = detect_profile(job)
    required = _list(raw.get("required_skills"))
    if not required:
        required = _list(job.get("skill_tags"))
    pass_score = max(0, min(int(raw.get("pass_score") or 75), 100))
    pending_score = max(0, min(int(raw.get("pending_score") or 55), pass_score))
    try:
        min_years = max(float(raw.get("min_work_years") or _infer_years(job_text)), 0)
    except (TypeError, ValueError):
        min_years = _infer_years(job_text)
    return {
        "profile": profile,
        "profile_name": PROFILE_NAMES[profile],
        "min_education": str(raw.get("min_education") or _infer_education(job_text)).strip(),
        "min_work_years": min_years,
        "required_skills": required,
        "preferred_skills": _list(raw.get("preferred_skills")),
        "hard_skills": _list(raw.get("hard_skills")),
        "industry_tags": _list(raw.get("industry_tags")),
        "pass_score": pass_score,
        "pending_score": pending_score,
        "weights": {name: weight for name, weight in PROFILE_WEIGHTS[profile]},
    }


def _aliases(term: str) -> list[str]:
    lowered = term.casefold()
    for group in SYNONYM_GROUPS:
        if any(lowered == item.casefold() for item in group):
            return list(group)
    return [term]


def _contains(text: str, term: str) -> tuple[bool, str]:
    for alias in _aliases(term):
        if alias.casefold() in text.casefold():
            return True, alias
    return False, ""


def _snippet(text: str, term: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    position = normalized.casefold().find(term.casefold())
    if position < 0:
        return ""
    start = max(0, position - 34)
    end = min(len(normalized), position + len(term) + 52)
    return normalized[start:end].strip(" ，,。;；")


def _matches(text: str, terms: list[str]) -> tuple[list[str], list[str], list[str]]:
    matched, missing, evidence = [], [], []
    for term in _list(terms):
        found, alias = _contains(text, term)
        if found:
            matched.append(term)
            proof = _snippet(text, alias)
            evidence.append(f"{term}：{proof or '简历中已识别'}")
        else:
            missing.append(term)
    return matched, missing, evidence


def _work_years(candidate: dict) -> float:
    def month(value: str, default_now: bool = False):
        value = str(value or "").strip()
        if default_now and (not value or any(token in value for token in ["至今", "现在", "present", "current"])):
            now = datetime.now()
            return now.year * 12 + now.month
        match = re.search(r"(19\d{2}|20\d{2})(?:\D{0,3}(\d{1,2}))?", value)
        if not match:
            return None
        return int(match.group(1)) * 12 + int(match.group(2) or 1)

    months = 0
    for item in candidate.get("work_experience") or []:
        start = month(item.get("start", ""))
        end = month(item.get("end", ""), default_now=True)
        if start is not None and end is not None and end >= start:
            months += end - start + 1
    return round(min(months / 12, 50), 1)


def _candidate_text(candidate: dict, resume_text: str) -> str:
    values = [candidate.get("tags", ""), candidate.get("major", ""), resume_text]
    for item in candidate.get("education") or []:
        values.extend([item.get("school", ""), item.get("major", ""), item.get("degree", "")])
    for item in candidate.get("work_experience") or []:
        values.extend([item.get("company", ""), item.get("position", ""), item.get("desc", "")])
    return "\n".join(str(value) for value in values if value)


def _term_dimension(name: str, weight: int, text: str, terms: list[str], *, target=None) -> dict:
    terms = _list(terms)
    if not terms:
        return {"name": name, "score": 0, "max_score": weight, "status": "not_configured",
                "matched": [], "missing": [], "evidence": ["该维度尚未配置评价标准"]}
    matched, missing, evidence = _matches(text, terms)
    denominator = max(int(target or len(terms)), 1)
    ratio = min(len(matched) / denominator, 1)
    return {
        "name": name, "score": round(weight * ratio, 1), "max_score": weight,
        "status": "matched" if ratio >= .75 else "partial" if ratio > 0 else "missing",
        "matched": matched, "missing": missing, "evidence": evidence[:5],
    }


def _metric_dimension(name: str, weight: int, text: str, terms: list[str], target=2) -> dict:
    dimension = _term_dimension(name, weight, text, terms, target=target)
    numeric = re.findall(r"\d+(?:\.\d+)?\s*(?:%|万|亿|万元|元|家|人|个|QPS|单)", text, re.I)
    if numeric and dimension["matched"]:
        dimension["score"] = min(weight, round(dimension["score"] + weight * .25, 1))
        dimension["evidence"] = ([f"量化成果：{', '.join(numeric[:4])}"] + dimension["evidence"])[:5]
        if dimension["score"] >= weight * .75:
            dimension["status"] = "matched"
    return dimension


def _experience_dimension(name: str, weight: int, candidate: dict, minimum: float) -> dict:
    years = _work_years(candidate)
    if minimum <= 0:
        return {"name": name, "score": 0, "max_score": weight,
                "status": "not_configured", "matched": [], "missing": [],
                "evidence": [f"识别到约 {years:g} 年工作经历，职位未设置最低年限"]}
    ratio = min(years / minimum, 1)
    return {
        "name": name, "score": round(weight * ratio, 1), "max_score": weight,
        "status": "matched" if ratio >= 1 else "partial" if ratio > 0 else "missing",
        "matched": [f"{years:g}年工作经历"] if years else [],
        "missing": [] if ratio >= 1 else [f"要求至少{minimum:g}年，识别到{years:g}年"],
        "evidence": [f"根据工作经历时间识别约 {years:g} 年，职位要求 {minimum:g} 年"],
    }


def _education_dimension(name: str, weight: int, candidate: dict, minimum: str) -> dict:
    actual = str(candidate.get("highest_education") or "").strip()
    if not minimum:
        return {"name": name, "score": 0, "max_score": weight, "status": "not_configured",
                "matched": [], "missing": [], "evidence": [f"候选人学历：{actual or '未识别'}；职位未设置最低学历"]}
    actual_level = EDUCATION_LEVELS.get(actual, 0)
    required_level = EDUCATION_LEVELS.get(minimum, 0)
    ratio = 1 if actual_level >= required_level and required_level else .5 if actual_level == required_level - 1 else 0
    return {
        "name": name, "score": round(weight * ratio, 1), "max_score": weight,
        "status": "matched" if ratio == 1 else "partial" if ratio else "missing",
        "matched": [f"{actual}学历"] if ratio == 1 else [],
        "missing": [] if ratio == 1 else [f"最低学历要求{minimum}，当前识别为{actual or '未知'}"],
        "evidence": [f"候选人学历：{actual or '未识别'}；职位要求：{minimum}"],
    }


def _evaluate_match_item(item: dict, profile: str, text: str, candidate: dict,
                         rules: dict, required: list[str]) -> dict:
    name = str(item.get("name") or "未命名匹配项")
    try:
        weight = max(float(item.get("weight") or 0), 0)
    except (TypeError, ValueError):
        weight = 0
    try:
        target = max(int(item.get("target_count") or 1), 1)
    except (TypeError, ValueError):
        target = 1
    evaluator = item.get("evaluator") or "custom_terms"

    if evaluator == "experience":
        dimension = _experience_dimension(name, weight, candidate, rules["min_work_years"])
    elif evaluator == "education":
        dimension = _education_dimension(name, weight, candidate, rules["min_education"])
    else:
        preferred = rules["preferred_skills"]
        evaluator_terms = {
            "job_skills": required + preferred,
            "ai": AI_TERMS,
            "ecommerce": rules["industry_tags"] or ECOMMERCE_TERMS,
            "product_ops": required + preferred or PRODUCT_OPS_TERMS,
            "data": DATA_TERMS,
            "sales_performance": ["销售额", "业绩", "目标", "回款", "客户", "合同"],
            "sales_industry": rules["industry_tags"] or SALES_INDUSTRY_TERMS,
            "customer_type": CUSTOMER_TERMS,
            "sales_process": required + preferred or SALES_PROCESS_TERMS,
            "resources": RESOURCE_TERMS,
            "sales_cycle": SALES_CYCLE_TERMS,
            "custom_terms": _list(item.get("terms")),
        }
        terms = evaluator_terms.get(evaluator, _list(item.get("terms")))
        if evaluator == "project_metrics":
            terms = (
                TECH_TERMS + AI_TERMS + ECOMMERCE_TERMS if profile == "tech"
                else PRODUCT_OPS_TERMS + DATA_TERMS if profile == "product_ops"
                else SALES_PROCESS_TERMS + SALES_INDUSTRY_TERMS
            )
            dimension = _metric_dimension(name, weight, text, terms, target=target)
        elif evaluator == "sales_performance":
            dimension = _metric_dimension(name, weight, text, terms, target=target)
        else:
            dimension = _term_dimension(name, weight, text, terms, target=target)
    dimension["key"] = str(item.get("key") or "")
    dimension["evaluator"] = evaluator
    return dimension


def screen_candidate(candidate: dict, job: dict, raw_rules: dict | None = None,
                     resume_text: str = "", match_items: list[dict] | None = None) -> dict:
    rules = normalize_screening_rules(raw_rules, job)
    profile = rules["profile"]
    text = _candidate_text(candidate, resume_text)
    required = rules["required_skills"]
    if not required:
        known = TECH_TERMS if profile == "tech" else PRODUCT_OPS_TERMS if profile == "product_ops" else SALES_PROCESS_TERMS
        job_text = " ".join(str(job.get(key, "")) for key in ("description", "qualification", "skill_tags"))
        required = [term for term in known if _contains(job_text, term)[0]]

    active_items = [
        item for item in (match_items if match_items is not None else default_match_items(profile))
        if item.get("enabled", True)
    ]
    dimensions = [
        _evaluate_match_item(item, profile, text, candidate, rules, required)
        for item in sorted(active_items, key=lambda value: (value.get("sort", 0), value.get("id", 0)))
    ]
    rules["weights"] = {item["name"]: item["max_score"] for item in dimensions}

    assessed = [item for item in dimensions if item["status"] != "not_configured"]
    assessed_weight = sum(item["max_score"] for item in assessed)
    score = round(sum(item["score"] for item in assessed) / assessed_weight * 100) if assessed_weight else 0
    hard_matched, hard_missing, hard_evidence = _matches(text, rules["hard_skills"])
    if assessed_weight < 40:
        decision = "insufficient"
    elif hard_missing:
        decision = "pending"
    elif score >= rules["pass_score"]:
        decision = "pass"
    elif score >= rules["pending_score"]:
        decision = "pending"
    else:
        decision = "reject"

    decision_labels = {
        "pass": "建议通过", "pending": "建议待定",
        "reject": "匹配度较低", "insufficient": "信息不足",
    }
    matched_items = list(dict.fromkeys(
        hard_matched + [item for dim in dimensions for item in dim["matched"]]
    ))[:12]
    missing_items = list(dict.fromkeys(
        [f"硬性技能待确认：{item}" for item in hard_missing]
        + [item for dim in dimensions for item in dim["missing"] if dim.get("evaluator") in {"job_skills", "sales_process", "education", "experience"}]
    ))[:12]
    risk_items = [
        f"{dim['name']}证据不足（{dim['score']:g}/{dim['max_score']}）"
        for dim in assessed if dim["score"] < dim["max_score"] * .5
    ][:8]
    return {
        "profile": profile, "profile_name": PROFILE_NAMES[profile],
        "score": score, "decision": decision, "decision_label": decision_labels[decision],
        "assessed_weight": assessed_weight, "dimensions": dimensions,
        "matched_items": matched_items, "missing_items": missing_items,
        "risk_items": risk_items, "hard_skill_evidence": hard_evidence,
        "rules": rules,
        "summary": (
            f"候选人与“{job.get('name', '当前职位')}”的综合匹配度为 {score}%，"
            f"系统结论为“{decision_labels[decision]}”。请结合分项证据由 HR 最终确认。"
        ),
    }
