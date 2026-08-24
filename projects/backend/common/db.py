"""MongoDB 数据访问基础层。

全部业务数据存 MongoDB（禁止 SQL 数据库）：
- 集合 _id 使用自增整数（counters 集合发号），保持既有 API 的整数 id 兼容；
- 分页、查询、更新、删除统一走本层助手；
- 连接与异常处理见 common/mongo.py。
"""
from datetime import datetime

from flask import current_app
from pymongo import ReturnDocument

from .mongo import get_db


def col(name: str):
    """当前应用上下文中的集合。"""
    return get_db(current_app)[name]


def next_id(name: str, session=None) -> int:
    """集合级自增 id（整数，兼容既有 API/前端）。"""
    doc = get_db(current_app)["counters"].find_one_and_update(
        {"_id": name}, {"$inc": {"seq": 1}},
        upsert=True, return_document=ReturnDocument.AFTER,
        session=session,
    )
    return int(doc["seq"])


def get_by_id(name: str, doc_id, session=None):
    try:
        doc_id = int(doc_id)
    except (TypeError, ValueError):
        return None
    return col(name).find_one({"_id": doc_id}, session=session)


def insert_doc(name: str, doc: dict, session=None) -> dict:
    """插入并分配整数 _id（调用方未提供时）。"""
    if "_id" not in doc:
        doc["_id"] = next_id(name, session=session)
    doc.setdefault("created_at", datetime.now())
    doc["updated_at"] = datetime.now()
    col(name).insert_one(doc, session=session)
    return doc


def update_doc(name: str, doc_id: int, fields: dict, session=None) -> bool:
    fields = {k: v for k, v in fields.items() if k != "_id"}
    fields["updated_at"] = datetime.now()
    result = col(name).update_one({"_id": doc_id}, {"$set": fields}, session=session)
    return result.matched_count > 0


def delete_doc(name: str, doc_id: int) -> bool:
    return col(name).delete_one({"_id": doc_id}).deleted_count > 0


def paginate(query, page: int, page_size: int):
    """内存分页（与既有 API 行为一致：先过滤后分页）。"""
    items = list(query)
    total = len(items)
    sliced = items[(page - 1) * page_size: page * page_size]
    return sliced, total, page, page_size


def dt(value):
    """datetime → 'YYYY-MM-DD HH:mm:ss'，空值 → ''。"""
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def date_str(value):
    return value.strftime("%Y-%m-%d") if value else ""
