"""Extract source-backed employers and associate their employment periods."""
import re
import unicodedata


_MONTH = r"(?:1[0-2]|0?[1-9])(?!\d)"
_DAY = r"(?:3[01]|[12]\d|0?[1-9])(?!\d)"
_MONTH_NAMES = (
    "January February March April May June July August September October November December".split()
)
_EN_MONTH = "(?:" + "|".join(name[:3] + "(?:" + name[3:] + ")?" for name in _MONTH_NAMES) + ")"
_WORK_DATE = (
    rf"(?:(?:19|20)\d{{2}}(?:\s*[年./-]\s*{_MONTH}"
    rf"(?:\s*[月./-]\s*{_DAY}\s*日?|\s*月)?)?"
    rf"|{_EN_MONTH}\.?\s+(?:19|20)\d{{2}})"
)
WORK_PERIOD_RE = re.compile(
    rf"(?<!\d)(?P<start>{_WORK_DATE})\s*"
    rf"(?:[-‐‑‒–—―~～−﹣－]+\s*|至\s*(?!今)|到\s*|to\s+|(?=至今|现在|目前))"
    rf"(?P<end>{_WORK_DATE}|至今|现在|目前|present|current|now)(?!\d)", re.I,
)

WORK_HEADINGS = {
    "工作经历", "工作经验", "职业经历", "工作履历", "任职经历", "实习经历", "实习经验",
    "employment", "employment history", "work experience", "professional experience", "career history",
    "internship", "internships", "internship experience",
}
_OTHER_HEADINGS = {
    "教育经历", "教育背景", "学历背景", "学习经历", "项目经历", "项目经验", "项目背景",
    "个人信息", "基本信息", "个人优势", "个人简介", "自我评价", "求职意向", "专业技能",
    "技能特长", "资格证书", "荣誉奖项", "校园经历", "语言能力", "兴趣爱好", "证书奖励",
    "education", "education background", "projects", "project experience", "skills",
    "certifications", "personal information", "summary", "awards",
}
_COMPANY_LABEL = re.compile(
    r"(?:公司名称|所在公司|任职公司|所属公司|工作单位|单位名称|雇主名称|公司|单位|雇主|company(?: name)?|employer|organization)"
    r"(?:\s*[：:|｜=]\s*|\s+)", re.I,
)
_ROLE_LABEL = re.compile(r"(?:职位名称|岗位名称|职位|岗位|职务|position|job title|title)\s*[：:|｜]\s*", re.I)
_ORG_SUFFIX = (
    r"(?:有限责任公司|股份有限公司|有限公司|公司|集团|工作室|事务所|研究院|研究所|银行|证券|基金|医院|"
    r"信息技术|电子商务|网络科技|科技|传媒|资本|控股|实业|软件|电商|咨询|投资|网络|互联网|"
    r"Co\.,?\s*Ltd\.?|Limited|Ltd\.?|Inc\.?|LLC|Corp\.?|Corporation|Technologies|Technology|Group)"
)
_ORG_RE = re.compile(rf"^(.{{2,100}}?{_ORG_SUFFIX})(?=$|[\s|｜,，;；（(])", re.I)
_NARRATIVE_RE = re.compile(
    r"^(?:负责|参与|主导|协助|承担|完成|实现|制定|搭建|推动|维护|服务|对接|开发了|为.+提供|"
    r"熟悉|掌握|精通|擅长|累计|成功|独立|主要负责|工作(?:内容|职责|描述|成果)|主要(?:工作|职责|业绩)|"
    r"项目(?:名称|经验|经历|描述|背景|职责|内容|业绩)?[：:]|客户(?:名称|包括|涵盖|为|是|有|[:：])|"
    r"公司(?:介绍|规模|性质|简介)|单位性质|所在部门|所属部门|所属行业|行业|汇报对象|薪资|"
    r"离职原因|任职要求|技术栈|使用技术|工作期间|在职期间|业绩|营收|销售额|团队规模|教育|学历|专业|毕业|"
    r"responsibilit|achievement|project\b|client\b|customer\b|skills?\b|industry\b)", re.I,
)
_ROLE_RE = re.compile(
    r"(?:工程师|经理|主管|总监|专员|助理|顾问|分析师|研究员|负责人|合伙人|实习生|"
    r"开发|设计师|运营|销售|客服|教师|讲师|投资人|创始人|总裁|董事长|秘书|会计|出纳|程序员|"
    r"\b(?:engineer|manager|analyst|director|associate|consultant|developer|specialist|intern|lead|officer)\b)", re.I,
)
_METADATA_RE = re.compile(
    r"^(?:\d+\s*(?:年|个月|月)|\d+\s*[-~至]\s*\d+\s*人|\d+人|保密|全职|兼职|实习|"
    r"民营|私营|国企|外企|上市|未上市|股份制|外商独资|合资|工作经验|工作经历|工作时间|任职时间|起止时间)$",
)
_BARE_BLOCKLIST = {
    "科技", "公司", "集团", "软件", "互联网", "网络", "投资", "战略投资", "市场", "部门",
    "本科", "硕士", "博士", "至今", "现在", "目前", "工作内容", "工作描述", "工作职责",
    "金融", "金融业", "互联网金融", "制造业", "上市公司", "未上市公司", "电子商务",
    "公司名称", "单位名称", "工作单位", "职位", "岗位", "职务", "任职时间", "工作时间",
    "React", "TypeScript", "JavaScript", "Python", "Java", "MongoDB", "MySQL", "SQL",
    "PHP", "HTML", "CSS", "C++", "Linux", "Excel", "Word", "PowerPoint",
}


def _heading(line):
    value = re.sub(r"^[\s•●▪◆*\d一二三四五六七八九十.、)）-]+", "", line.strip()).lower()
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    for heading in sorted(WORK_HEADINGS | _OTHER_HEADINGS, key=len, reverse=True):
        if re.fullmatch(re.escape(heading) + r"\s*(?:[（(].*?[)）])?\s*[：:|｜]?", value):
            return heading
    return ""


def normalize_work_date(value):
    value = value.strip()
    if re.fullmatch(r"至今|现在|目前|present|current|now", value, re.I):
        return "至今"
    english = re.match(r"([A-Za-z]+)\.?\s+((?:19|20)\d{2})", value)
    if english:
        month = next(i + 1 for i, name in enumerate(_MONTH_NAMES) if name[:3].lower() == english[1][:3].lower())
        return f"{english[2]}-{month:02d}"
    matched = re.match(r"((?:19|20)\d{2})(?:\s*[年./-]\s*(\d{1,2}))?", value)
    if not matched:
        return value
    return f"{matched[1]}-{int(matched[2]):02d}" if matched[2] else matched[1]


def _join_split_periods(lines):
    result = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not WORK_PERIOD_RE.search(line):
            for count in (2, 3, 4):
                if index + count > len(lines) or any(_heading(v) for v in lines[index:index + count]):
                    break
                joined = " ".join(lines[index:index + count])
                period = WORK_PERIOD_RE.search(joined)
                # Only join a period that starts on this line and crosses its newline.
                if period and period.start() < len(line) < period.end():
                    line = joined
                    index += count - 1
                    break
        result.append(line)
        index += 1
    return result


def _sections(text):
    lines = []
    for line in (line.strip() for line in text.splitlines() if line.strip()):
        inline_heading = next((matched for heading in WORK_HEADINGS | _OTHER_HEADINGS
                               if (matched := re.match(rf"^({re.escape(heading)})\s*[:：|｜]\s*(.+)$", line, re.I))), None)
        lines.extend([inline_heading[1], inline_heading[2]] if inline_heading else [line])
    has_work_heading = any(_heading(line) in WORK_HEADINGS for line in lines)
    sections = []
    active = []
    collecting = not has_work_heading
    for line in lines:
        heading = _heading(line)
        if heading:
            if active:
                sections.append((active, has_work_heading))
                active = []
            collecting = heading in WORK_HEADINGS
        elif collecting:
            active.append(line)
    if active:
        sections.append((active, has_work_heading))
    return [(_join_split_companies(_join_split_periods(lines)), scoped) for lines, scoped in sections]


def _clean(value):
    value = WORK_PERIOD_RE.sub(" ", value)
    value = re.sub(r"[（(]\s*\d+\s*(?:年|个月|月)[^）)]*[）)]", "", value)
    value = re.sub(r"^[\s•●▪◆*]+|^\d+[.、]\s*", "", value)
    return value.strip(" ：:，,;；|｜/\\-—~～")


def _role(value):
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    return bool(_ROLE_RE.search(value)) and not _NARRATIVE_RE.search(value) and len(value) <= 60


def _join_split_companies(lines):
    result = []
    suffixes = {"有限公司", "有限责任公司", "股份有限公司", "公司", "集团", "科技有限公司", "网络科技有限公司"}
    for line in lines:
        compact = re.sub(r"\s+", "", line)
        if compact in suffixes and result:
            previous = _clean(result[-1])
            if (2 <= len(previous) <= 70 and not _role(previous)
                    and not _NARRATIVE_RE.search(previous) and not _METADATA_RE.fullmatch(previous)
                    and not WORK_PERIOD_RE.search(result[-1]) and not _heading(previous)):
                result[-1] = result[-1] + compact
                continue
        result.append(line)
    return result


def _company_value(value, *, explicit=False, scoped=False):
    value = _clean(_ROLE_LABEL.split(value)[0])
    if not value or len(value) > 120 or "@" in value or _heading(value):
        return "", 0
    if _NARRATIVE_RE.search(value) or _METADATA_RE.fullmatch(value.strip("（）() ")):
        return "", 0
    # Keep the source suffix even when a job title follows on the same row.
    match = _ORG_RE.match(value)
    if match:
        name = match[1].strip()
        name = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", name)
        if name not in _BARE_BLOCKLIST:
            return name, 3 if explicit else 2
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    match = _ORG_RE.fullmatch(value)
    if match and value not in _BARE_BLOCKLIST:
        return value, 3 if explicit else 2
    if value in _BARE_BLOCKLIST or _role(value) or re.search(r"大学|学院|学校|[：:，,。；;!?！？]", value):
        return "", 0
    if re.fullmatch(r"[\d\s.年月日/~～—–-]+", value):
        return "", 0
    # Short brands need an actual work-section context; labels are stronger evidence.
    if re.search(r"项目|提升|增长|达成|获奖|荣誉", value) and not explicit:
        return "", 0
    if ((scoped or explicit) and 2 <= len(value) <= 60
            and re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9·&.（）()'’\s-]+", value)
            and (len(re.findall(r"[\u4e00-\u9fff]", value)) >= 2 or re.search(r"[A-Za-z]{2}", value))):
        return value, 3 if explicit else 1
    return "", 0


def _line_parts(line):
    value = _clean(line)
    parts = [part.strip() for part in re.split(r"[|｜;；\t]+|\s{2,}", value) if part.strip()]
    result = []
    for part in parts:
        company = _ORG_RE.match(part)
        if company and _role(part[company.end():].strip()):
            result.extend([company[1], part[company.end():].strip()])
            continue
        # Preserve multi-word English brands before a recognizable role phrase.
        english_role = re.match(
            r"^(.+?)\s+((?:(?:senior|junior|lead|staff|principal|investment|sales|marketing|software|"
            r"product|account|business|data|operations|financial|research)\s+)*"
            r"(?:engineer|manager|analyst|director|associate|consultant|developer|specialist|intern))$", part, re.I,
        )
        if english_role:
            result.extend([english_role[1], english_role[2]])
            continue
        # Separate a Chinese brand and job title written with one ordinary space.
        split = re.match(r"^(.+?)\s+(.+)$", part)
        if (split and len(split[1].strip()) >= 2 and re.search(r"[\u4e00-\u9fff]", split[2])
                and _role(split[2]) and not _ORG_RE.match(part)):
            result.extend([split[1], split[2]])
        else:
            result.append(part)
    return result


def _employers(lines, scoped):
    employers = []
    for index, line in enumerate(lines):
        labeled = _COMPANY_LABEL.search(line)
        if labeled:
            raw = _ROLE_LABEL.split(line[labeled.end():])[0]
            raw = re.split(r"[|｜;；]|\s{2,}", raw, maxsplit=1)[0]
            company, strength = _company_value(raw, explicit=True, scoped=scoped)
            if company:
                employers.append({"index": index, "company": company, "strength": strength})
                continue
        if _NARRATIVE_RE.search(_clean(line)):
            continue
        candidates = []
        for part in _line_parts(line):
            company, strength = _company_value(part, scoped=scoped)
            if company:
                candidates.append((strength, company))
        if candidates:
            strength, company = max(candidates, key=lambda item: item[0])
            employers.append({"index": index, "company": company, "strength": strength})
    return employers


def extract_work_experience(text):
    records = []
    for lines, scoped in _sections(unicodedata.normalize("NFKC", text)):
        employers = _employers(lines, scoped)
        periods = {i: match for i, line in enumerate(lines) if (match := WORK_PERIOD_RE.search(line))}
        # Weak brand names need a nearby period or a job title, never just prose.
        employers = [e for e in employers if e["strength"] > 1 or any(
            abs(i - e["index"]) <= 8 for i in periods
        ) or any(_role(_clean(line)) for line in lines[e["index"] + 1:e["index"] + 3])]
        if not employers:
            continue
        assigned = {e["index"]: e["index"] for e in employers if e["index"] in periods}
        used = set(assigned.values())
        remaining_companies = [e["index"] for e in employers if e["index"] not in assigned]
        remaining_dates = [i for i in periods if i not in used]
        company_first = bool(remaining_companies and remaining_dates and remaining_companies[0] < remaining_dates[0])
        for n, employer in enumerate(employers):
            index = employer["index"]
            if index in assigned:
                continue
            previous = employers[n - 1]["index"] if n else -1
            following = employers[n + 1]["index"] if n + 1 < len(employers) else len(lines)
            before = [i for i in periods if previous < i < index and i not in used]
            after = [i for i in periods if index < i < following and i not in used]
            preferred = (after or before) if company_first else (before or after)
            if preferred:
                date_index = min(preferred, key=lambda i: abs(i - index))
                assigned[index] = date_index
                used.add(date_index)
        for n, employer in enumerate(employers):
            index = employer["index"]
            date_index = assigned.get(index)
            # Outside a work section, a suffix alone is not enough without a period.
            if date_index is None and not scoped and employer["strength"] < 3:
                continue
            period = periods.get(date_index)
            start, end = (normalize_work_date(period["start"]), normalize_work_date(period["end"])) if period else ("", "")
            if company_first or date_index is None:
                left = min(index, date_index) if date_index is not None else index
                right = employers[n + 1]["index"] if n + 1 < len(employers) else len(lines)
            else:
                left = min(date_index, index)
                right = next((i for i in periods if i > max(date_index, index)), len(lines))
                if n + 1 < len(employers):
                    right = min(right, employers[n + 1]["index"])
            context = lines[left:right]
            position = ""
            descriptions = []
            for line in context:
                labeled = _ROLE_LABEL.search(line)
                if labeled and not position:
                    position = re.split(r"[|｜;；]", _clean(line[labeled.end():]), maxsplit=1)[0]
                for part in _line_parts(line):
                    if not position and _role(part) and employer["company"] not in part:
                        position = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", part)
                    if _NARRATIVE_RE.search(part):
                        descriptions.append(part)
            records.append({"company": employer["company"], "position": position,
                            "start": start, "end": end, "desc": " ".join(descriptions)[:500]})
    unique = []
    for record in records:
        key = (record["company"], record["start"], record["end"])
        previous = next((r for r in unique if (r["company"], r["start"], r["end"]) == key), None)
        if previous:
            if not previous["position"]:
                previous["position"] = record["position"]
        else:
            unique.append(record)
    return unique
