"""文件服务：统一上传入口（存储 + MongoDB 元数据），供文件接口与简历上传复用。"""
import io
import logging
from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId

from common.mongo import FILES_COLLECTION, MongoUnavailable, get_collection
from common.storage import StorageError, build_object_key, validate_upload

logger = logging.getLogger(__name__)


def get_storage(app):
    storage = app.extensions.get("storage")
    if storage is None:
        raise StorageError("文件存储未初始化")
    return storage


def meta_to_dict(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "originalName": doc.get("originalName", ""),
        "objectKey": doc.get("objectKey", ""),
        "url": f"/api/files/{doc['_id']}/download",
        "mimeType": doc.get("mimeType", ""),
        "size": doc.get("size", 0),
        "uploadedBy": doc.get("uploadedBy", {}),
        "bizType": doc.get("bizType", ""),
        "storage": doc.get("storage", ""),
        "createdAt": doc["createdAt"].strftime("%Y-%m-%d %H:%M:%S") if doc.get("createdAt") else "",
    }


def save_uploaded_file(app, file_storage, biz_type: str,
                       operator_id: str, operator_name: str,
                       allowed_exts=None, max_size=None) -> dict:
    """校验 → 上传存储 → 写 MongoDB 元数据。任一步失败都清理已产生资源。"""
    storage = get_storage(app)
    filename = file_storage.filename or ""
    file_storage.seek(0, 2)
    size = file_storage.tell()
    file_storage.seek(0)

    ext = validate_upload(filename, size, allowed_exts, max_size)
    object_key = build_object_key(getattr(storage, "prefix", "") if storage.name == "oss" else "", ext)

    storage.upload(file_storage, object_key)
    doc = {
        "originalName": filename,
        "objectKey": object_key,
        "url": "",  # 落库后回填
        "mimeType": file_storage.mimetype or "",
        "size": size,
        "uploadedBy": {"id": operator_id, "name": operator_name},
        "bizType": biz_type,
        "storage": storage.name,
        "createdAt": datetime.now(),
    }
    try:
        collection = get_collection(app, FILES_COLLECTION)
        result = collection.insert_one(doc)
    except (MongoUnavailable, Exception) as e:
        storage.delete(object_key)  # 元数据写入失败：回滚已上传文件
        if isinstance(e, MongoUnavailable):
            raise
        raise StorageError(f"文件元数据保存失败: {e}") from e
    doc["_id"] = result.inserted_id
    meta = meta_to_dict(doc)
    collection.update_one({"_id": result.inserted_id}, {"$set": {"url": meta["url"]}})
    return meta


def find_meta(app, file_id: str):
    try:
        oid = ObjectId(file_id)
    except (InvalidId, TypeError):
        return None
    try:
        return get_collection(app, FILES_COLLECTION).find_one({"_id": oid})
    except MongoUnavailable:
        raise
    except Exception as e:
        raise StorageError(f"文件元数据查询失败: {e}") from e


def read_file_bytes(app, file_path_or_key: str) -> io.BytesIO:
    """兼容新旧存储读取：本地绝对路径直读；对象 Key 经存储层读取（OSS 临时文件用后清理）。"""
    import os

    if os.path.isabs(file_path_or_key) and os.path.exists(file_path_or_key):
        with open(file_path_or_key, "rb") as f:
            return io.BytesIO(f.read())
    storage = get_storage(app)
    path = storage.local_path(file_path_or_key)
    try:
        with open(path, "rb") as f:
            return io.BytesIO(f.read())
    finally:
        storage.cleanup_local(path, file_path_or_key)


def resolve_local(app, path_or_key: str):
    """返回 (本地可读路径, 是否临时文件)。绝对路径直读；对象 Key 经存储层解析。"""
    import os

    if os.path.isabs(path_or_key) and os.path.exists(path_or_key):
        return path_or_key, False
    storage = get_storage(app)
    return storage.local_path(path_or_key), storage.name != "local"


def delete_stored_file(app, path_or_key: str):
    """删除存储对象：兼容旧的本地绝对路径与新的对象 Key。"""
    import os

    if os.path.isabs(path_or_key):
        if os.path.exists(path_or_key):
            os.remove(path_or_key)
        return
    get_storage(app).delete(path_or_key)
