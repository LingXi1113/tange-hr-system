"""简历自动解析与候选人草稿回填。"""

import logging

from common.db import get_by_id, update_doc
from common.file_service import get_storage, resolve_local
from common.logstore import write_log
from common.resume_parser import parse_resume_file

logger = logging.getLogger(__name__)

EMPTY_FIELDS = {"name": "", "phone": "", "email": "", "city": "", "education": []}


def auto_parse_attachment(app, attachment_id: int, candidate_id: int):
    """解析附件并只回填候选人当前为空的基础字段。

    解析失败只更新附件状态，不抛出业务异常，保证公开投递已经成功的事实不被回滚。
    返回值为 (fields, status)；status 为 processing 结束后的 system 或 failed。
    """
    attachment = get_by_id("attachments", attachment_id)
    if attachment is None:
        return dict(EMPTY_FIELDS), "failed"

    update_doc("attachments", attachment_id, {"parse_status": "processing"})
    local_path = None
    is_tmp = False
    fields = dict(EMPTY_FIELDS)
    status = "failed"
    try:
        local_path, is_tmp = resolve_local(app, attachment.get("file_path", ""))
        fields, status = parse_resume_file(local_path, attachment.get("file_name", ""))
    except Exception:
        logger.exception("公开投递简历自动解析失败 attachment_id=%s candidate_id=%s",
                         attachment_id, candidate_id)
    finally:
        if is_tmp and local_path:
            try:
                get_storage(app).cleanup_local(local_path, attachment.get("file_path", ""))
            except Exception:
                logger.exception("清理简历解析临时文件失败 attachment_id=%s", attachment_id)

    update_doc("attachments", attachment_id, {
        "parse_status": status,
        "parsed_fields": fields,
    })

    if status == "system":
        candidate = get_by_id("candidates", candidate_id)
        if candidate:
            updates = {
                key: value for key, value in fields.items()
                if key in EMPTY_FIELDS and value and not candidate.get(key)
            }
            if updates:
                update_doc("candidates", candidate_id, updates)
                write_log("candidate", "resume_auto_parse", "", "系统",
                          biz_id=str(candidate_id),
                          detail="公开投递简历自动回填: " + ", ".join(updates.keys()))
    return fields, status
