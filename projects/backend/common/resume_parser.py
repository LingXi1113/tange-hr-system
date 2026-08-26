"""Resume text extraction and conservative structured parsing.

The parser follows the useful parts of orgatAI/resume-parse-python:
extract PDF text with a layout-aware parser first, then associate nearby
dates, schools, degrees and majors into education records. It is deliberately
conservative: results are drafts and must remain editable by HR.
"""
import logging
import os
import re

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
PDF_EXTS = {".pdf"}
WORD_EXTS = {".docx", ".doc"}
logger = logging.getLogger(__name__)

DEGREE_RE = re.compile(
    r"博士后|博士研究生|博士在读|工商管理硕士|工程硕士|专业硕士|在职研究生|硕士研究生|研究生|本科|大专|高职|中专|高中|初中|博士|硕士|学士|MBA|EMBA",
)
SCHOOL_RE = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9·()（）&.\-]{2,50}(?:大学|学院|学校|分校|电大)",
)
DATE_RE = re.compile(
    r"(?:19|20)\d{2}\s*(?:年|[./-])\s*(?:\d{1,2}\s*月?)?|(?:至今|现在)",
)
MAJOR_LABEL_RE = re.compile(
    r"(?:专业|主修|研究方向|所学专业|专业方向)\s*[：:]\s*([^\r\n]{2,40})",
    flags=re.IGNORECASE,
)
GENDER_LABEL_RE = re.compile(
    r"(?:\u6027\u522b|gender|sex)\s*[\uFF1A:,\uFF0C\s]\s*(\u7537|\u5973|male|female|m|f)",
    flags=re.IGNORECASE,
)
DATE_TOKEN = r"(?:19|20)\d{2}\s*(?:[\u5E74./-]\s*\d{1,2}\s*\u6708?)?"
WORK_PERIOD_RE = re.compile(
    rf"(?P<start>{DATE_TOKEN})\s*(?:[-~\uFF5E\u2014\u2013]|\u81F3|\u5230)\s*"
    rf"(?P<end>{DATE_TOKEN}|\u81F3\u4ECA|\u73B0\u5728|\u76EE\u524D)",
    flags=re.IGNORECASE,
)
WORK_SECTION_HEADINGS = {
    "\u5DE5\u4F5C\u7ECF\u5386", "\u5DE5\u4F5C\u7ECF\u9A8C", "\u804C\u4E1A\u7ECF\u5386", "\u5DE5\u4F5C\u5C65\u5386", "\u4EFB\u804C\u7ECF\u5386", "employment",
    "work experience", "professional experience", "career history",
}
SECTION_HEADINGS = {
    "个人优势", "个人信息", "个人简介", "个人简历", "简历", "求职意向", "联系方式",
    "教育经历", "教育背景", "工作经历", "项目经历", "实习经历", "技能特长", "专业技能",
    "自我评价", "证书奖励", "荣誉奖项", "兴趣爱好", "语言能力", "校园经历", "基本信息",
    "resume", "curriculum vitae", "cv",
}
# Keep the section vocabulary Unicode-safe even when a legacy source file was
# checked out with a non-UTF-8 console encoding.
SECTION_HEADINGS = {
    "\u4E2A\u4EBA\u4F18\u52BF", "\u4E2A\u4EBA\u4FE1\u606F", "\u4E2A\u4EBA\u7B80\u4ECB", "\u4E2A\u4EBA\u7B80\u5386", "\u7B80\u5386",
    "\u6C42\u804C\u610F\u5411", "\u8054\u7CFB\u65B9\u5F0F", "\u6559\u80B2\u7ECF\u5386", "\u6559\u80B2\u80CC\u666F",
    "\u5DE5\u4F5C\u7ECF\u5386", "\u9879\u76EE\u7ECF\u5386", "\u5B9E\u4E60\u7ECF\u5386", "\u6280\u80FD\u7279\u957F", "\u4E13\u4E1A\u6280\u80FD",
    "\u81EA\u6211\u8BC4\u4EF7", "\u8BC1\u4E66\u5956\u52B1", "\u8363\u8A89\u5956\u9879", "\u5174\u8DA3\u7231\u597D", "\u8BED\u8A00\u80FD\u529B",
    "\u6821\u56ED\u7ECF\u5386", "\u57FA\u672C\u4FE1\u606F", "resume", "curriculum vitae", "cv",
}
ALL_SECTION_HEADINGS = SECTION_HEADINGS | WORK_SECTION_HEADINGS


class OcrService:
    """Image OCR hook; the current deployment does not bundle an OCR engine."""

    def recognize(self, file_path: str):  # noqa: D102
        return None


def _extract_pdf(file_path: str) -> str:
    """Extract PDF text with layout analysis, falling back to pypdf."""
    text = ""
    try:
        from pdfminer.high_level import extract_text
        from pdfminer.layout import LAParams

        text = extract_text(
            file_path,
            laparams=LAParams(char_margin=2.0, line_margin=0.4, word_margin=0.1),
        ) or ""
    except Exception:
        logger.exception("PDFMiner 文本提取失败 extension=pdf")

    if text.strip():
        return text

    try:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        logger.exception("pypdf 文本提取失败 extension=pdf")
        return ""


def _extract_docx(file_path: str) -> str:
    import docx

    document = docx.Document(file_path)
    return "\n".join(p.text for p in document.paragraphs)


def extract_text(file_path: str):
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext in PDF_EXTS:
            return _extract_pdf(file_path)
        if ext == ".docx":
            return _extract_docx(file_path)
        if ext in IMAGE_EXTS:
            return OcrService().recognize(file_path)
    except Exception:
        logger.exception("简历文本提取失败 extension=%s", ext)
        return None
    return None


def _normalize_date(value: str) -> str:
    value = re.sub(r"\s+", "", value)
    if value in {"至今", "现在"}:
        return "至今"
    matched = re.match(r"((?:19|20)\d{2})[年./-]?(\d{1,2})?", value)
    if not matched:
        return value
    year, month = matched.groups()
    return f"{year}-{int(month):02d}" if month else year


def _clean_school(value: str) -> str:
    value = re.sub(r"^(?:教育经历|教育背景|毕业院校|学校)\s*[：:，,]?", "", value)
    return value.strip(" ：:，,;；|·")


def _pick_degree(text: str) -> str:
    matches = DEGREE_RE.findall(text)
    if not matches:
        return ""
    return sorted(matches, key=lambda item: (-len(item), text.find(item)))[0]


def _pick_major(text: str) -> str:
    matched = MAJOR_LABEL_RE.search(text)
    if not matched:
        return ""
    return re.split(r"(?:学历|学位|学校|毕业时间)\s*[：:]", matched.group(1))[0].strip(" ：:，,;；|")


def _extract_education(text: str) -> list[dict]:
    """Associate nearby date/degree/major tokens with each school."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    records = []
    for index, line in enumerate(lines):
        schools = SCHOOL_RE.findall(line)
        if not schools:
            continue
        start = max(index - 2, 0)
        end = min(index + 3, len(lines))
        context = "\n".join(lines[start:end])
        dates = [_normalize_date(item) for item in DATE_RE.findall(context)]
        degree = _pick_degree(context)
        major = _pick_major(context)
        for school in schools:
            school = _clean_school(school)
            if not school:
                continue
            records.append({
                "school": school,
                "major": major,
                "degree": degree,
                "graduate_at": dates[-1] if dates else "",
            })

    unique = []
    seen = set()
    for record in records:
        key = tuple(record.values())
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return unique


def _name_from_filename(filename: str) -> str:
    if not filename:
        return ""
    stem = os.path.splitext(os.path.basename(filename))[0]
    # 常见简历命名：姓名_职位_城市、姓名-学校-学历、姓名1120。
    matched = re.match(r"([\u4e00-\u9fa5·]{2,6})", stem)
    if not matched:
        return ""
    candidate = matched.group(1).strip("·")
    return "" if candidate in SECTION_HEADINGS else candidate


def _normalize_gender(value: str) -> str:
    value = value.strip().lower()
    if value in {"\u7537", "male", "m"}:
        return "\u7537"
    if value in {"\u5973", "female", "f"}:
        return "\u5973"
    return ""


def _extract_gender(text: str, filename: str = "") -> str:
    compact = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    for source in (text, compact):
        matched = GENDER_LABEL_RE.search(source)
        if matched:
            return _normalize_gender(matched.group(1))
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip(" \uFF1A:，,;；|-")
        matched = re.fullmatch(
            r"(?:\u6027\u522b|gender|sex)\s*(?:[\uFF1A:]\s*)?(\u7537|\u5973|male|female|m|f)",
            line,
            re.I,
        )
        if matched:
            return _normalize_gender(matched.group(1))
    stem = os.path.splitext(os.path.basename(filename))[0]
    matched = re.search(r"(?:^|[_\-\s])([\u7537\u5973])(?:[_\-\s]|$)", stem)
    return matched.group(1) if matched else ""


def _normalize_work_date(value: str) -> str:
    value = re.sub(r"\s+", "", value)
    if value in {"\u81F3\u4ECA", "\u73B0\u5728", "\u76EE\u524D"}:
        return "\u81F3\u4ECA"
    matched = re.match(r"((?:19|20)\d{2})[\u5E74./-]?(\d{1,2})?", value)
    if not matched:
        return value
    year, month = matched.groups()
    return f"{year}-{int(month):02d}" if month else year


def _work_period(line: str):
    matched = WORK_PERIOD_RE.search(line)
    if not matched:
        return None
    return (
        _normalize_work_date(matched.group("start")),
        _normalize_work_date(matched.group("end")),
        matched,
    )


def _strip_work_metadata(value: str) -> str:
    value = WORK_PERIOD_RE.sub("", value)
    value = re.sub(
        r"(?:\u5DE5\u4F5C\u65F6\u95F4|\u4EFB\u804C\u65F6\u95F4|\u8D77\u6B62\u65F6\u95F4|\u516C\u53F8\u540D\u79F0|\u516C\u53F8|\u5355\u4F4D|\u96C7\u4E3B|\u804C\u4F4D|\u5C97\u4F4D|\u804C\u52A1)\s*[\uFF1A:]\s*",
        "",
        value,
    )
    return value.strip(" \uFF1A:，,;；|/\\-—~～")


def _is_section_heading(line: str) -> bool:
    normalized = re.sub(r"[\uFF1A:\s]+$", "", line.strip()).lower()
    return normalized in ALL_SECTION_HEADINGS


def _extract_work_experience(text: str) -> list[dict]:
    """Extract company, position and dates from common work-history layouts."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    sections = []
    for index, line in enumerate(lines):
        normalized = re.sub(r"[\uFF1A:\s]+$", "", line).lower()
        if normalized in WORK_SECTION_HEADINGS:
            end = len(lines)
            for next_index in range(index + 1, len(lines)):
                if _is_section_heading(lines[next_index]) and lines[next_index].lower() not in WORK_SECTION_HEADINGS:
                    end = next_index
                    break
            sections.append(lines[index + 1:end])
    if not sections:
        sections = [lines]

    records = []
    for section in sections:
        for index, line in enumerate(section):
            period = _work_period(line)
            if not period:
                continue
            start, end, matched = period
            residual = _strip_work_metadata(line[:matched.start()] + " " + line[matched.end():])
            context = []
            if residual:
                context.append(residual)
            following = []
            for next_line in section[index + 1:index + 5]:
                if _work_period(next_line) or _is_section_heading(next_line):
                    break
                following.append(next_line)
            if following:
                context.extend(following)
            elif not residual and index >= 2:
                context.extend(section[max(0, index - 2):index])

            company = ""
            position = ""
            company_labeled = False
            plain_candidates = []
            for context_line in context:
                company_match = re.search(
                    r"(?:\u516C\u53F8\u540D\u79F0|\u516C\u53F8|\u5355\u4F4D|\u96C7\u4E3B)\s*[\uFF1A:]\s*([^|｜;；]+)",
                    context_line,
                    re.I,
                )
                position_match = re.search(
                    r"(?:\u804C\u4F4D|\u5C97\u4F4D|\u804C\u52A1)\s*[\uFF1A:]\s*([^|｜;；]+)",
                    context_line,
                    re.I,
                )
                if company_match and not company:
                    company = _strip_work_metadata(company_match.group(1))
                    company_labeled = True
                if position_match and not position:
                    position = _strip_work_metadata(position_match.group(1))
                cleaned = _strip_work_metadata(context_line)
                if not cleaned or _is_section_heading(cleaned):
                    continue
                parts = [part.strip() for part in re.split(r"[|｜]", cleaned) if part.strip()]
                plain_candidates.extend(parts or [cleaned])

            plain_candidates = [
                candidate for candidate in plain_candidates
                if len(candidate) <= 80 and not re.fullmatch(
                    r"[\d\s./\u5E74\u6708\u65E5\u81F3\u4ECA\u73B0\u5728\u76EE\u524D~～—–\-]+",
                    candidate,
                )
            ]
            if not company and plain_candidates:
                company = plain_candidates[0]
            if not position and len(plain_candidates) > 1:
                position = plain_candidates[1]
            if company == position:
                position = ""
            desc = plain_candidates[2:] if len(plain_candidates) > 2 else []
            # Do not turn a date plus a job title/description into a fake employer.
            # An unlabeled company must visibly contain “公司”; an explicit 公司： label
            # is also accepted even when the value itself omits the suffix.
            has_company_evidence = company_labeled or "\u516C\u53F8" in company
            if has_company_evidence and company:
                records.append({
                    "company": company,
                    "position": position,
                    "start": start,
                    "end": end,
                    "desc": " ".join(desc)[:500],
                })

    unique = []
    seen = set()
    for record in records:
        key = tuple(record.values())
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return unique


def _sanitize_name(value: str) -> str:
    """Return only a likely person name, never a filename/section suffix."""
    value = re.sub(r"\s+", " ", str(value or "")).strip(" \uFF1A:，,;；|/")
    value = re.split(r"[_\-\[\]（）()（）]", value, maxsplit=1)[0].strip()
    value = re.sub(
        r"(?:\u4E2A\u4EBA)?\u7B80\u5386(?:\u6587\u4EF6|\u6587\u6863)?$|(?:resume|curriculum\s+vitae|cv)$",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip(" \uFF1A:，,;；|/")
    chinese = re.match(r"[\u4e00-\u9fff·]{2,6}", value)
    if chinese:
        candidate = chinese.group(0).strip("·")
        return "" if candidate in SECTION_HEADINGS else candidate
    english = re.match(r"[A-Za-z][A-Za-z .'-]{1,39}", value)
    return english.group(0).strip() if english else ""


def parse_resume_fields(text: str, filename: str = "") -> dict:
    """Extract name, contacts and education; city is intentionally omitted."""
    fields = {"name": "", "phone": "", "email": "", "city": "", "education": []}
    if not text:
        fields.update({"gender": "", "work_experience": []})
        return fields
    fields.update({"gender": "", "work_experience": []})

    compact = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    phone = re.search(r"1[3-9](?:[\s-]*\d){9}", text)
    if phone:
        fields["phone"] = re.sub(r"\D", "", phone.group(0))
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if email:
        fields["email"] = email.group(0)
    fields["gender"] = _extract_gender(text, filename)

    name_patterns = [
        r"(?:姓\s*名|名字|候选人|应聘者)\s*[：:]\s*([^\r\n]{2,30})",
        r"(?:Name|Candidate\s+Name)\s*[:：]\s*([^\r\n]{2,30})",
        r"(?:姓\s*名|名字)\s+([\u4e00-\u9fa5A-Za-z·]{2,20})",
    ]
    name_value = ""
    for pattern in name_patterns:
        matched = re.search(pattern, text, flags=re.IGNORECASE) or re.search(
            pattern, compact, flags=re.IGNORECASE,
        )
        if matched:
            name_value = matched.group(1)
            break
    if name_value:
        name_value = re.split(
            r"(?:性别|手机(?:号码)?|电话|邮箱|电子邮箱|城市|所在地|现居)\s*[：:]",
            name_value,
            maxsplit=1,
        )[0]
        name_value = re.sub(r"\s+", " ", name_value).strip(" ：:，,;；")
        name_match = re.match(r"[\u4e00-\u9fa5A-Za-z·][\u4e00-\u9fa5A-Za-z· .'-]{1,19}", name_value)
        if name_match:
            fields["name"] = name_match.group(0).strip()

    if not fields["name"]:
        fields["name"] = _name_from_filename(filename)

    if not fields["name"]:
        for line in (line.strip() for line in text.splitlines() if line.strip()):
            candidate = re.sub(r"\s+", " ", line).strip(" ：:，,;；")
            if candidate.lower() in SECTION_HEADINGS or len(candidate) > 20:
                continue
            if re.fullmatch(r"[\u4e00-\u9fa5·]{2,6}", candidate) or re.fullmatch(
                r"[A-Za-z][A-Za-z .'-]{1,30}", candidate,
            ):
                fields["name"] = candidate
                break

    fields["name"] = _sanitize_name(fields["name"])
    fields["education"] = _extract_education(text)
    fields["work_experience"] = _extract_work_experience(text)
    return fields


def _sanitize_name(value: str) -> str:
    """Normalize a name without carrying filename or section text into it."""
    value = re.sub(r"\s+", " ", str(value or "")).strip(" \uFF1A:\uFF0C,;\uFF1B|/")
    value = re.split(r"[_\-\[\]\uFF08\uFF09()]", value, maxsplit=1)[0].strip()
    value = re.sub(
        r"(?:\u4E2A\u4EBA)?\u7B80\u5386(?:\u6587\u4EF6|\u6587\u6863)?$|(?:resume|curriculum\s+vitae|cv)$",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip(" \uFF1A:\uFF0C,;\uFF1B|/")
    chinese = re.match(r"[\u4e00-\u9fff\u00b7]{2,6}", value)
    if chinese:
        candidate = chinese.group(0).strip("\u00b7")
        return "" if candidate in SECTION_HEADINGS else candidate
    english = re.match(r"[A-Za-z][A-Za-z .'-]{1,39}", value)
    return english.group(0).strip() if english else ""


def parse_resume_file(file_path: str, original_filename: str = ""):
    """Return (fields, parse_status): system=parsed, failed=manual review."""
    ext = os.path.splitext(file_path)[1].lower()
    empty = {"name": "", "phone": "", "email": "", "city": "", "education": []}
    empty.update({"gender": "", "work_experience": []})
    if ext in IMAGE_EXTS:
        return empty, "failed"
    text = extract_text(file_path)
    if not text or not text.strip():
        return empty, "failed"
    fields = parse_resume_fields(text, original_filename)
    if not any([
        fields["name"], fields["gender"], fields["phone"], fields["email"],
        fields["education"], fields["work_experience"],
    ]):
        return fields, "failed"
    return fields, "system"
