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
SECTION_HEADINGS = {
    "个人优势", "个人信息", "个人简介", "个人简历", "简历", "求职意向", "联系方式",
    "教育经历", "教育背景", "工作经历", "项目经历", "实习经历", "技能特长", "专业技能",
    "自我评价", "证书奖励", "荣誉奖项", "兴趣爱好", "语言能力", "校园经历", "基本信息",
    "resume", "curriculum vitae", "cv",
}


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


def parse_resume_fields(text: str, filename: str = "") -> dict:
    """Extract name, contacts and education; city is intentionally omitted."""
    fields = {"name": "", "phone": "", "email": "", "city": "", "education": []}
    if not text:
        return fields

    compact = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    phone = re.search(r"1[3-9](?:[\s-]*\d){9}", text)
    if phone:
        fields["phone"] = re.sub(r"\D", "", phone.group(0))
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if email:
        fields["email"] = email.group(0)

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

    fields["education"] = _extract_education(text)
    return fields


def parse_resume_file(file_path: str, original_filename: str = ""):
    """Return (fields, parse_status): system=parsed, failed=manual review."""
    ext = os.path.splitext(file_path)[1].lower()
    empty = {"name": "", "phone": "", "email": "", "city": "", "education": []}
    if ext in IMAGE_EXTS:
        return empty, "failed"
    text = extract_text(file_path)
    if not text or not text.strip():
        return empty, "failed"
    fields = parse_resume_fields(text, original_filename)
    if not any([fields["name"], fields["phone"], fields["email"], fields["education"]]):
        return fields, "failed"
    return fields, "system"
