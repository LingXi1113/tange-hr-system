"""简历解析服务：PDF/Word 文本抽取 + 字段启发式解析；图片 OCR 预留接口。

解析结果为结构化草稿，HR 必须可人工修改；解析失败不阻断候选人创建。
"""
import logging
import os
import re

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
PDF_EXTS = {".pdf"}
WORD_EXTS = {".docx", ".doc"}
logger = logging.getLogger(__name__)


class OcrService:
    """图片简历 OCR 预留接口：当前环境无 OCR 能力，统一返回 None 转人工录入。"""

    def recognize(self, file_path: str):  # noqa: D102
        return None


def _extract_pdf(file_path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


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
        # 解析失败允许转人工，但不能丢失原因；只记录扩展名，避免日志写入简历内容。
        logger.exception("简历文本提取失败 extension=%s", ext)
        return None
    return None


def parse_resume_fields(text: str) -> dict:
    """启发式抽取基础字段（草稿，允许人工修改）。"""
    fields = {"name": "", "phone": "", "email": "", "city": ""}
    if not text:
        return fields
    phone = re.search(r"1[3-9]\d{9}", text)
    if phone:
        fields["phone"] = phone.group(0)
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if email:
        fields["email"] = email.group(0)
    name = re.search(r"姓\s*名[：:\s]*([\u4e00-\u9fa5A-Za-z·]{2,10})", text)
    if name:
        fields["name"] = name.group(1).strip()
    city = re.search(r"(?:城市|所在地|现居)[：:\s]*([\u4e00-\u9fa5]{2,8})", text)
    if city:
        fields["city"] = city.group(1).strip()
    return fields


def parse_resume_file(file_path: str):
    """返回 (fields, parse_status)：system=解析成功 / failed=转人工。"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in IMAGE_EXTS:
        return {"name": "", "phone": "", "email": "", "city": ""}, "failed"
    text = extract_text(file_path)
    if not text or not text.strip():
        return {"name": "", "phone": "", "email": "", "city": ""}, "failed"
    fields = parse_resume_fields(text)
    if not any(fields.values()):
        return fields, "failed"
    return fields, "system"
