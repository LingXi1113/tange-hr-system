"""Local OCR fallback for scanned resumes.

RapidOCR ships its own Chinese/English ONNX models. PDF pages are rendered by
pypdfium2 so the backend does not depend on a separately installed Tesseract
binary or a GPL/AGPL PDF renderer.
"""
import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _recognize_image(image) -> tuple[str, float]:
    # The angle classifier can rotate an upright long bilingual line by mistake.
    # Resume pages are usually upright; try orientation correction only when the
    # initial result is short or weak, and select the better supported result.
    result, _ = _engine()(image, use_cls=False)
    def strength(items):
        return sum(len(str(item[1])) * float(item[2]) for item in (items or []) if len(item) >= 3)

    if strength(result) < 60:
        rotated_result, _ = _engine()(image, use_cls=True)
        if strength(rotated_result) > strength(result):
            result = rotated_result
    if not result:
        return "", 0.0
    lines = []
    scores = []
    for item in result:
        if len(item) < 3:
            continue
        value = str(item[1] or "").strip()
        if value:
            lines.append(value)
            try:
                scores.append(float(item[2]))
            except (TypeError, ValueError):
                pass
    return "\n".join(lines), (sum(scores) / len(scores) if scores else 0.0)


def recognize_resume(file_path: str) -> tuple[str, float]:
    """Return OCR text and average OCR confidence; failures are non-fatal."""
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            import numpy as np
            import pypdfium2 as pdfium

            maximum = max(1, int(os.environ.get("HRATS_RESUME_OCR_MAX_PAGES", "8")))
            scale = max(1.5, min(float(os.environ.get("HRATS_RESUME_OCR_SCALE", "2.2")), 3.0))
            document = pdfium.PdfDocument(file_path)
            page_texts = []
            confidences = []
            try:
                for page_index in range(min(len(document), maximum)):
                    page = document[page_index]
                    bitmap = page.render(scale=scale)
                    image = bitmap.to_pil().convert("RGB")
                    text, confidence = _recognize_image(np.asarray(image))
                    if text:
                        page_texts.append(text)
                        confidences.append(confidence)
                    image.close()
                    bitmap.close()
                    page.close()
            finally:
                document.close()
            average = sum(confidences) / len(confidences) if confidences else 0.0
            return "\n\n".join(page_texts), average

        return _recognize_image(file_path)
    except (ImportError, OSError, ValueError):
        logger.exception("本地 OCR 不可用 file=%s", os.path.basename(file_path))
        return "", 0.0
    except Exception:
        logger.exception("简历 OCR 识别失败 file=%s", os.path.basename(file_path))
        return "", 0.0

