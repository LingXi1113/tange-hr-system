"""登录态 Token 签发与校验。

内嵌应用运行于第三方 iframe，浏览器拦截第三方 Cookie，session 无法稳定保持；
因此登录/切换用户时签发 HMAC 签名 Token，前端存 localStorage 并通过
X-Auth-Token 请求头携带。Token 无状态，使用 SECRET_KEY 签名，可跨重启校验。
"""
from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SALT = "hrats-auth-token"
TOKEN_MAX_AGE = 7 * 24 * 3600  # 7 天


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=SALT)


def generate_token(user_id: str) -> str:
    return _serializer().dumps({"user_id": user_id})


def parse_token(token: str):
    """返回 user_id；无效或过期返回 None。"""
    try:
        data = _serializer().loads(token, max_age=TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("user_id")
