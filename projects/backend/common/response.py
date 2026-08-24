"""统一响应结构：{code, msg, data}；code=0 成功，非 0 业务错误。"""
from flask import jsonify


class BizCode:
    OK = 0
    PARAM_INVALID = 1001
    NOT_FOUND = 1002
    STATE_INVALID = 1003
    DUPLICATED = 1004
    LOCKED = 1005
    FORBIDDEN = 1006
    CONFLICT = 1007


def ok(data=None, msg: str = "ok"):
    return jsonify({"code": BizCode.OK, "msg": msg, "data": data})


def fail(code: int, msg: str, http_status: int = 200):
    resp = jsonify({"code": code, "msg": msg, "data": None})
    resp.status_code = http_status
    return resp


def paged(items: list, total: int, page: int, page_size: int):
    return ok({"list": items, "total": total, "page": page, "page_size": page_size})
