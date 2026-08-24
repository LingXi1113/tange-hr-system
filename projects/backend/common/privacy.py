"""候选人个人信息彻底删除的级联服务。"""
from common.db import col, delete_doc
from common.file_service import delete_stored_file
from common.logstore import write_log


def _id_set(rows):
    return {row["_id"] for row in rows if row.get("_id") is not None}


def purge_candidate(app, candidate_id: int, operator_id: str, operator_name: str) -> dict:
    """删除候选人及所有招聘业务关联数据。

    删除前先清理文件对象；文件存储失败会中止数据库级联，避免留下可继续访问的
    简历对象。删除后的审计记录只保留候选人 ID 和删除统计，不保留姓名、手机号等信息。
    """
    attachments = list(col("attachments").find({"candidate_id": candidate_id}))
    object_keys = {att.get("file_path") for att in attachments if att.get("file_path")}
    file_ids = {str(att.get("file_id")) for att in attachments if att.get("file_id")}
    file_docs = []
    for file_doc in col("files").find({}):
        if str(file_doc.get("_id")) in file_ids or file_doc.get("objectKey") in object_keys:
            file_docs.append(file_doc)
            if file_doc.get("objectKey"):
                object_keys.add(file_doc["objectKey"])

    # 物理文件与文件元数据必须先清理；异常时不删除候选人主档。
    for object_key in object_keys:
        delete_stored_file(app, object_key)
    for file_doc in file_docs:
        col("files").delete_one({"_id": file_doc["_id"]})

    applications = list(col("applications").find({"candidate_id": candidate_id}))
    application_ids = _id_set(applications)
    interviews = list(col("interviews").find({"candidate_id": candidate_id}))
    interview_ids = _id_set(interviews)
    offers = list(col("offers").find({"candidate_id": candidate_id}))
    offer_ids = _id_set(offers)
    onboarding = list(col("onboarding_records").find({"candidate_id": candidate_id}))
    onboarding_ids = _id_set(onboarding)
    pool_entries = list(col("talent_pool").find({"candidate_id": candidate_id}))
    pool_ids = _id_set(pool_entries)

    if interview_ids:
        col("interview_feedback").delete_many({"interview_id": {"$in": list(interview_ids)}})
    if offer_ids:
        col("offer_approvals").delete_many({"offer_id": {"$in": list(offer_ids)}})
    if application_ids:
        col("stage_transitions").delete_many({"application_id": {"$in": list(application_ids)}})
        col("lock_records").delete_many({"application_id": {"$in": list(application_ids)}})
    col("interviews").delete_many({"candidate_id": candidate_id})
    col("offers").delete_many({"candidate_id": candidate_id})
    col("onboarding_records").delete_many({"candidate_id": candidate_id})
    col("applications").delete_many({"candidate_id": candidate_id})
    col("talent_pool").delete_many({"candidate_id": candidate_id})
    col("attachments").delete_many({"candidate_id": candidate_id})

    related = [{"biz_type": "candidate", "biz_id": str(candidate_id)}]
    related += [{"biz_type": "application", "biz_id": str(item)} for item in application_ids]
    related += [{"biz_type": "interview", "biz_id": str(item)} for item in interview_ids]
    related += [{"biz_type": "offer", "biz_id": str(item)} for item in offer_ids]
    related += [{"biz_type": "offer_approval", "biz_id": str(item)} for item in offer_ids]
    related += [{"biz_type": "onboarding", "biz_id": str(item)} for item in onboarding_ids]
    related += [{"biz_type": "talent_pool", "biz_id": str(item)} for item in pool_ids]
    col("notifications").delete_many({"$or": related})
    col("operation_logs").delete_many({"$or": related})
    delete_doc("candidates", candidate_id)

    stats = {
        "candidate_id": candidate_id,
        "attachments": len(attachments),
        "applications": len(applications),
        "interviews": len(interviews),
        "offers": len(offers),
        "onboarding": len(onboarding),
        "talent_pool": len(pool_entries),
    }
    write_log(
        "candidate", "delete", operator_id, operator_name,
        biz_id=str(candidate_id),
        detail="个人信息彻底删除；" + "; ".join(f"{key}={value}" for key, value in stats.items() if key != "candidate_id"),
    )
    return stats
