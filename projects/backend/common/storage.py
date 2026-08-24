"""文件存储层：阿里云 OSS 优先，未配置 OSS 凭据时降级为本地存储（仅开发环境）。

- OSS 配置全部来自环境变量：OSS_ACCESSKEY_ID / OSS_ACCESSKEY_SECRET /
  OSS_BUCKET / OSS_PREFIX，以及可选的 OSS_ENDPOINT 或 OSS_REGION；
- 对象路径：{OSS_PREFIX}{yyyyMMdd}/{uuid}{ext}，避免文件名冲突；
- 上传失败时清理已产生的临时文件 / OSS 对象，并抛出 StorageError；
- 下载/预览不暴露密钥：OSS 使用签名 URL，本地使用后端代理。
"""
import logging
import os
import tempfile
import uuid
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)

# 允许上传的文件类型（文档/附件/图片）
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
}
DEFAULT_MAX_SIZE = 20 * 1024 * 1024  # 20MB


class StorageError(Exception):
    """存储层错误（携带面向用户的清晰信息）。"""


class StorageConfigError(Exception):
    """存储配置错误（生产环境禁止降级本地存储）。只提示变量名，不含密钥值。"""


def validate_upload(filename: str, size: int, allowed_exts=None, max_size=None):
    ext = os.path.splitext(filename or "")[1].lower()
    allowed = allowed_exts or ALLOWED_EXTENSIONS
    if ext not in allowed:
        raise StorageError(f"不支持的文件类型: {ext or '未知'}")
    limit = max_size or DEFAULT_MAX_SIZE
    if size > limit:
        raise StorageError(f"文件大小超过限制（最大 {limit // 1024 // 1024}MB）")
    return ext


def build_object_key(prefix: str, ext: str) -> str:
    date_part = datetime.now().strftime("%Y%m%d")
    prefix = prefix or ""
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return f"{prefix}{date_part}/{uuid.uuid4().hex}{ext}"


class StorageBackend(ABC):
    name = "abstract"

    @abstractmethod
    def upload(self, stream, object_key: str):
        """上传文件流；失败必须清理并抛出 StorageError。"""

    @abstractmethod
    def delete(self, object_key: str):
        """删除对象（幂等，失败仅记录日志）。"""

    @abstractmethod
    def signed_url(self, object_key: str, expires: int = 600):
        """返回可直接访问的签名 URL；不支持时返回 None（由后端代理下载）。"""

    @abstractmethod
    def local_path(self, object_key: str) -> str:
        """返回可读取的本地文件路径（OSS 时下载到临时文件）。"""

    def cleanup_local(self, path: str, object_key: str):
        """清理由 local_path 产生的临时文件（仅 OSS 场景需要）。"""


class LocalStorage(StorageBackend):
    """开发环境兜底：未配置 OSS 凭据时使用本地磁盘（行为等价、接口一致）。"""

    name = "local"

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def _full_path(self, object_key: str) -> str:
        path = os.path.join(self.root_dir, object_key)
        real_root = os.path.abspath(self.root_dir)
        if not os.path.abspath(path).startswith(real_root):
            raise StorageError("非法的对象路径")
        return path

    def upload(self, stream, object_key: str):
        path = self._full_path(object_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            stream.save(path)
        except Exception as e:
            if os.path.exists(path):
                os.remove(path)  # 清理残留临时文件
            raise StorageError(f"文件保存失败: {e}") from e

    def delete(self, object_key: str):
        try:
            path = self._full_path(object_key)
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.warning("本地文件删除失败 %s: %s", object_key, e)

    def signed_url(self, object_key: str, expires: int = 600):
        return None  # 本地存储走后端代理下载

    def local_path(self, object_key: str) -> str:
        path = self._full_path(object_key)
        if not os.path.exists(path):
            raise StorageError("文件不存在或已被删除")
        return path


class OssStorage(StorageBackend):
    name = "oss"

    def __init__(self, access_key_id: str, access_key_secret: str,
                 bucket: str, endpoint: str, prefix: str):
        import oss2

        self._oss2 = oss2
        self.prefix = prefix or ""
        auth = oss2.Auth(access_key_id, access_key_secret)
        self.bucket = oss2.Bucket(auth, endpoint, bucket)

    def upload(self, stream, object_key: str):
        try:
            data = stream.read()
            self.bucket.put_object(object_key, data)
        except Exception as e:
            # 上传失败：尽力删除可能已产生的 OSS 对象
            try:
                self.bucket.delete_object(object_key)
            except Exception as cleanup_error:
                logger.warning(
                    "OSS 上传失败后的对象清理失败 key=%s error=%s",
                    object_key, cleanup_error,
                )
            raise StorageError(f"OSS 上传失败: {e}") from e

    def delete(self, object_key: str):
        try:
            self.bucket.delete_object(object_key)
        except Exception as e:
            logger.warning("OSS 对象删除失败 %s: %s", object_key, e)

    def signed_url(self, object_key: str, expires: int = 600):
        try:
            return self.bucket.sign_url("GET", object_key, expires, slash_safe=True)
        except Exception as e:
            logger.warning("OSS 签名失败 %s: %s", object_key, e)
            return None

    def local_path(self, object_key: str) -> str:
        suffix = os.path.splitext(object_key)[1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            self.bucket.get_object_to_file(object_key, tmp.name)
        except Exception as e:
            os.remove(tmp.name)
            raise StorageError(f"OSS 文件读取失败: {e}") from e
        return tmp.name

    def cleanup_local(self, path: str, object_key: str):
        try:
            if path and path.startswith(tempfile.gettempdir()):
                os.remove(path)
        except OSError as exc:
            logger.warning("临时文件清理失败 key=%s error=%s", object_key, exc)


def create_storage(app) -> StorageBackend:
    """按配置创建存储后端。

    - OSS 凭据齐全：使用 OSS；
    - 生产环境（HRATS_ENV=production）凭据不完整：抛出 StorageConfigError，
      禁止静默降级本地存储；
    - 开发/测试环境：降级为本地存储兜底并告警。
    """
    cfg = app.config
    production = cfg.get("ENV_NAME") == "production" and not cfg.get("TESTING")
    key_id = cfg.get("OSS_ACCESSKEY_ID") or ""
    key_secret = cfg.get("OSS_ACCESSKEY_SECRET") or ""
    bucket = cfg.get("OSS_BUCKET") or ""

    missing = [name for name, value in (
        ("OSS_ACCESSKEY_ID", key_id),
        ("OSS_ACCESSKEY_SECRET", key_secret),
        ("OSS_BUCKET", bucket),
    ) if not value]
    endpoint = cfg.get("OSS_ENDPOINT") or ""
    if not endpoint and cfg.get("OSS_REGION"):
        endpoint = f"https://oss-{cfg['OSS_REGION']}.aliyuncs.com"
    if not endpoint:
        missing.append("OSS_END_POINT/OSS_ENDPOINT/OSS_REGION")

    if missing:
        if production:
            raise StorageConfigError(
                "生产环境 OSS 配置不完整，禁止降级本地存储，缺少：" + ", ".join(missing))
        logger.warning("未配置完整 OSS 凭据（缺少 %s），文件存储降级为本地模式（仅限开发环境）",
                       ", ".join(missing))
        return LocalStorage(os.path.join(cfg["UPLOAD_DIR"], "files"))

    if key_id and key_secret and bucket:
        return OssStorage(key_id, key_secret, bucket, endpoint, cfg.get("OSS_PREFIX") or "")
    # 理论上不可达（missing 已覆盖），兜底保持安全行为
    if production:
        raise StorageConfigError("生产环境 OSS 配置校验未通过")
    return LocalStorage(os.path.join(cfg["UPLOAD_DIR"], "files"))
