"""业务异常与全局错误处理。"""
from flask import jsonify

from .response import BizCode, fail


class BizError(Exception):
    """业务异常：HTTP 200 + code!=0（鉴权类除外）。"""

    def __init__(self, code: int, msg: str, http_status: int = 200):
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.http_status = http_status


def register_error_handlers(app):
    @app.errorhandler(BizError)
    def handle_biz_error(e: BizError):
        return fail(e.code, e.msg, e.http_status)

    @app.errorhandler(404)
    def handle_404(e):
        return fail(BizCode.NOT_FOUND, "接口不存在", 404)

    @app.errorhandler(405)
    def handle_405(e):
        return fail(BizCode.PARAM_INVALID, "请求方法不允许", 405)

    @app.errorhandler(500)
    def handle_500(e):
        app.logger.exception("internal error")
        return jsonify({"code": 500, "msg": "服务器内部错误", "data": None}), 500
