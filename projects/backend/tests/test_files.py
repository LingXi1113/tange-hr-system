"""文件服务：MongoDB 连接、文件上传/查询/下载/删除、OSS 行为（Fake Bucket）。"""
import io

import pytest
from conftest import login

from common.mongo import FILES_COLLECTION, get_db
from common.storage import OssStorage, StorageError, build_object_key, validate_upload


@pytest.fixture()
def mongo_db(app):
    db = get_db(app)
    yield db
    db[FILES_COLLECTION].delete_many({})


def test_mongo_connection_roundtrip(app, mongo_db):
    """MongoDB 连接与异常处理：写入/读取/删除。"""
    coll = mongo_db[FILES_COLLECTION]
    result = coll.insert_one({"originalName": "a.txt", "size": 1})
    assert coll.find_one({"_id": result.inserted_id})["originalName"] == "a.txt"
    coll.delete_one({"_id": result.inserted_id})
    assert coll.find_one({"_id": result.inserted_id}) is None


def _upload(client, name="文档.docx", content=b"hello", biz_type="general"):
    return client.post("/api/files/upload", data={
        "file": (io.BytesIO(content), name),
        "biz_type": biz_type,
    }, content_type="multipart/form-data")


def test_upload_query_download_delete(client, mongo_db):
    login(client, "hr-001")
    body = _upload(client).get_json()
    assert body["code"] == 0, body
    meta = body["data"]
    # MongoDB 元数据字段齐全
    for key in ("id", "originalName", "objectKey", "url", "mimeType", "size", "uploadedBy", "createdAt"):
        assert key in meta
    assert meta["originalName"] == "文档.docx"
    assert meta["size"] == 5
    assert meta["uploadedBy"]["id"] == "hr-001"
    assert meta["url"] == f"/api/files/{meta['id']}/download"
    assert mongo_db[FILES_COLLECTION].find_one({"objectKey": meta["objectKey"]}) is not None

    # 列表与详情
    lst = client.get("/api/files", query_string={"biz_type": "general"}).get_json()["data"]
    assert any(f["id"] == meta["id"] for f in lst["list"])
    got = client.get(f"/api/files/{meta['id']}").get_json()["data"]
    assert got["objectKey"] == meta["objectKey"]

    # 下载（本地兜底走后端代理，不暴露密钥）
    dl = client.get(f"/api/files/{meta['id']}/download")
    assert dl.status_code == 200
    assert dl.data == b"hello"

    # 删除：OSS/本地对象 + MongoDB 元数据同时删除
    assert client.delete(f"/api/files/{meta['id']}").get_json()["code"] == 0
    assert mongo_db[FILES_COLLECTION].find_one({"objectKey": meta["objectKey"]}) is None
    assert client.get(f"/api/files/{meta['id']}").get_json()["code"] == 1002


def test_upload_validation(client):
    login(client, "hr-001")
    bad_type = _upload(client, name="virus.exe")
    assert bad_type.get_json()["code"] == 1001
    big = _upload(client, name="big.pdf", content=b"x" * (21 * 1024 * 1024))
    assert big.get_json()["code"] == 1001


def test_delete_permission(client):
    login(client, "hr-001")
    meta = _upload(client).get_json()["data"]
    login(client, "screen-001")  # 非上传者且非 HR
    assert client.delete(f"/api/files/{meta['id']}").get_json()["code"] == 1006


def test_object_key_unique_and_prefixed():
    k1 = build_object_key("hr-ats/", ".pdf")
    k2 = build_object_key("hr-ats/", ".pdf")
    assert k1.startswith("hr-ats/") and k1.endswith(".pdf")
    assert k1 != k2  # UUID 防冲突
    assert "/" in k1[len("hr-ats/"):]  # 含日期目录


def test_validate_upload():
    assert validate_upload("a.pdf", 10) == ".pdf"
    with pytest.raises(StorageError):
        validate_upload("a.exe", 10)
    with pytest.raises(StorageError):
        validate_upload("a.pdf", 99 * 1024 * 1024)


class FakeBucket:
    def __init__(self):
        self.store = {}
        self.deleted = []
        self.fail_put = False

    def put_object(self, key, data):
        if self.fail_put:
            raise RuntimeError("network down")
        self.store[key] = data

    def delete_object(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)

    def sign_url(self, method, key, expires, slash_safe=False):
        return f"https://fake-oss-signed/{key}?expires={expires}"

    def get_object_to_file(self, key, path):
        with open(path, "wb") as f:
            f.write(self.store[key])


@pytest.fixture()
def oss_storage(monkeypatch):
    fake = FakeBucket()
    import oss2

    monkeypatch.setattr(oss2, "Auth", lambda *a, **k: object())
    monkeypatch.setattr(oss2, "Bucket", lambda *a, **k: fake)
    storage = OssStorage("keyid", "keysecret", "bucket-x",
                         "https://oss-cn-hangzhou.aliyuncs.com", "hr-ats/")
    return storage, fake


def test_oss_upload_sign_delete(oss_storage):
    storage, fake = oss_storage
    stream = io.BytesIO(b"oss-data")
    storage.upload(stream, "hr-ats/20260821/abc.pdf")
    assert fake.store["hr-ats/20260821/abc.pdf"] == b"oss-data"
    url = storage.signed_url("hr-ats/20260821/abc.pdf", expires=300)
    assert url.startswith("https://fake-oss-signed/") and "expires=300" in url
    path = storage.local_path("hr-ats/20260821/abc.pdf")
    assert open(path, "rb").read() == b"oss-data"
    storage.cleanup_local(path, "hr-ats/20260821/abc.pdf")
    storage.delete("hr-ats/20260821/abc.pdf")
    assert "hr-ats/20260821/abc.pdf" in fake.deleted


def test_oss_upload_failure_cleans_up(oss_storage):
    storage, fake = oss_storage
    fake.fail_put = True
    with pytest.raises(StorageError):
        storage.upload(io.BytesIO(b"x"), "hr-ats/20260821/fail.pdf")
    # 失败后尝试清理可能产生的 OSS 对象
    assert "hr-ats/20260821/fail.pdf" in fake.deleted
