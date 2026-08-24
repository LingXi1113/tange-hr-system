"""文件管理接口：上传/查询/下载预览/删除（存储走 OSS，元数据在 MongoDB）。"""
from flask import Blueprint, Response, current_app, g, redirect, request

from common.decorators import login_required
from common.access import file_access_allowed
from common.errors import BizError
from common.file_service import find_meta, get_storage, meta_to_dict, save_uploaded_file
from common.mongo import FILES_COLLECTION, MongoUnavailable, get_collection
from common.response import BizCode, ok, paged
from common.roles import HR
from common.storage import StorageError
from common.logstore import write_log

bp = Blueprint("file_api", __name__, url_prefix="/api/files")


def _err(e: Exception):
    if isinstance(e, MongoUnavailable):
        return BizError(5001, "文件服务不可用：MongoDB 未连接")
    if isinstance(e, StorageError):
        return BizError(BizCode.PARAM_INVALID, str(e))
    return BizError(500, f"文件操作失败: {e}", http_status=500)


@bp.post("/upload")
@login_required
def upload_file():
    if g.current_user.role != HR:
        raise BizError(BizCode.FORBIDDEN, "仅 HR 可通过通用文件接口上传文件")
    file = request.files.get("file")
    if file is None or not file.filename:
        raise BizError(BizCode.PARAM_INVALID, "请上传文件")
    biz_type = request.form.get("biz_type", "general")
    try:
        meta = save_uploaded_file(
            current_app, file, biz_type,
            operator_id=g.current_user.user_id, operator_name=g.current_user.name,
        )
    except (MongoUnavailable, StorageError, Exception) as e:
        raise _err(e)
    write_log("file", "upload", g.current_user.user_id, g.current_user.name,
              biz_id=meta["id"], detail=meta["originalName"])
    return ok(meta)


@bp.get("")
@login_required
def list_files():
    biz_type = request.args.get("biz_type", "")
    if biz_type:
        probe = {"bizType": biz_type}
        if not file_access_allowed(probe):
            raise BizError(BizCode.FORBIDDEN, "当前角色无权查看该类文件")
        query = probe
    elif g.current_user.role == HR:
        query = {}
    else:
        # 非 HR 不允许通过不带 biz_type 的列表接口枚举所有文件元数据。
        allowed = []
        for candidate_type in ("resume", "offer"):
            if file_access_allowed({"bizType": candidate_type}):
                allowed.append(candidate_type)
        if not allowed:
            raise BizError(BizCode.FORBIDDEN, "当前角色无权查看文件")
        query = {"bizType": {"$in": allowed}}
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 10)), 1), 100)
    try:
        collection = get_collection(current_app, FILES_COLLECTION)
        total = collection.count_documents(query)
        cursor = collection.find(query).sort("createdAt", -1) \
            .skip((page - 1) * page_size).limit(page_size)
        items = [meta_to_dict(doc) for doc in cursor]
    except (MongoUnavailable, StorageError, Exception) as e:
        raise _err(e)
    return paged(items, total, page, page_size)


@bp.get("/<file_id>")
@login_required
def get_file_meta(file_id: str):
    try:
        doc = find_meta(current_app, file_id)
    except (MongoUnavailable, StorageError, Exception) as e:
        raise _err(e)
    if doc is None:
        raise BizError(BizCode.NOT_FOUND, "文件不存在")
    if not file_access_allowed(doc):
        raise BizError(BizCode.FORBIDDEN, "当前角色无权查看该文件")
    write_log("file", "view", g.current_user.user_id, g.current_user.name,
              biz_id=file_id, detail=doc.get("originalName", ""))
    return ok(meta_to_dict(doc))


@bp.get("/<file_id>/download")
@login_required
def download_file(file_id: str):
    """下载/预览：OSS 返回签名 URL 跳转（不暴露密钥），本地存储走后端代理。"""
    try:
        doc = find_meta(current_app, file_id)
        if doc is None:
            raise BizError(BizCode.NOT_FOUND, "文件不存在")
        if not file_access_allowed(doc):
            raise BizError(BizCode.FORBIDDEN, "当前角色无权下载该文件")
        storage = get_storage(current_app)
        url = storage.signed_url(doc["objectKey"], expires=600)
        if url:
            write_log("file", "download", g.current_user.user_id, g.current_user.name,
                      biz_id=file_id, detail=doc.get("originalName", ""))
            return redirect(url)
        from common.file_service import read_file_bytes

        data = read_file_bytes(current_app, doc["objectKey"])
        write_log("file", "download", g.current_user.user_id, g.current_user.name,
                  biz_id=file_id, detail=doc.get("originalName", ""))
        return Response(
            data.getvalue(),
            mimetype=doc.get("mimeType") or "application/octet-stream",
            headers={"Content-Disposition":
                     f"inline; filename*=UTF-8''{doc.get('originalName', '')}"},
        )
    except BizError:
        raise
    except (MongoUnavailable, StorageError, Exception) as e:
        raise _err(e)


@bp.delete("/<file_id>")
@login_required
def delete_file(file_id: str):
    try:
        doc = find_meta(current_app, file_id)
        if doc is None:
            raise BizError(BizCode.NOT_FOUND, "文件不存在")
        if not file_access_allowed(doc, action="delete"):
            raise BizError(BizCode.FORBIDDEN, "仅 HR 可删除文件")
        storage = get_storage(current_app)
        storage.delete(doc["objectKey"])  # 删除 OSS/本地对象
        get_collection(current_app, FILES_COLLECTION).delete_one({"_id": doc["_id"]})
    except BizError:
        raise
    except (MongoUnavailable, StorageError, Exception) as e:
        raise _err(e)
    write_log("file", "delete", g.current_user.user_id, g.current_user.name,
              biz_id=file_id, detail=doc.get("originalName", ""))
    return ok(None)
