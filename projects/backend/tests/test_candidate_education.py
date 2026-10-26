"""Highest degree stays consistent across parsing, saving, detail and lists."""
import pytest

from common.db import col, insert_doc
from common.resume_parser import parse_resume_fields
from conftest import login
from helpers import make_candidate


EDUCATION = [
    {"school": "北京大学", "major": "金融信息服务", "degree": "硕士", "graduate_at": "2018-07"},
    {"school": "武汉大学", "major": "金融工程", "degree": "本科", "graduate_at": "2015-06"},
]


@pytest.mark.parametrize("highest", ["本科", "硕士", "博士"])
def test_save_uses_highest_evidenced_degree_without_downgrading_manual_higher_degree(client, highest):
    login(client, "hr-001")
    response = client.post("/api/candidates", json={
        "name": "学历同步验证", "phone": "13900009991", "highest_education": highest, "education": EDUCATION,
    }).get_json()
    assert response["code"] == 0, response
    cid = response["data"]["candidate"]["id"]
    expected = "博士" if highest == "博士" else "硕士"
    detail = client.get(f"/api/candidates/{cid}").get_json()["data"]
    assert detail["highest_education"] == expected
    assert detail["education"] == EDUCATION
    row = client.get("/api/candidates").get_json()["data"]["list"][0]
    assert row["highest_education"] == expected
    assert row["education_summary"]["degree"] == "硕士"


def test_old_undergraduate_summary_does_not_hide_master_in_history_or_filters(client):
    login(client, "hr-001")
    cid = make_candidate(client)
    with client.application.app_context():
        col("candidates").update_one({"_id": cid}, {"$set": {"education": EDUCATION, "highest_education": "本科"}})
    detail = client.get(f"/api/candidates/{cid}").get_json()["data"]
    assert detail["highest_education"] == "硕士"
    masters = client.get("/api/candidates", query_string={"highest_education": "硕士", "include_summary": "1"}).get_json()["data"]
    assert masters["total"] == 1
    assert masters["classification"]["total"] == 1
    assert client.get("/api/candidates", query_string={"highest_education": "本科"}).get_json()["data"]["total"] == 0
    with client.application.app_context():
        # Read-side correction must not silently rewrite the user's saved record.
        assert col("candidates").find_one({"_id": cid})["highest_education"] == "本科"


def test_parse_draft_then_confirm_updates_highest_degree(client, monkeypatch):
    import modules.candidate_api as api

    login(client, "hr-001")
    cid = make_candidate(client)
    with client.application.app_context():
        col("candidates").update_one({"_id": cid}, {"$set": {"highest_education": "本科"}})
        attachment = insert_doc("attachments", {"candidate_id": cid, "file_name": "education.pdf", "file_path": "education-stub"})
    text = "教育背景\n2016.09-2018.07 北京大学 金融信息服务 工科/硕士\n2011.09-2015.06 武汉大学 金融工程 理科/学士"
    fields = parse_resume_fields(text)
    monkeypatch.setattr(api, "resolve_local", lambda *args: ("unused.pdf", False))
    monkeypatch.setattr(api, "parse_resume_file_with_text", lambda *args: (fields, "system", text))
    parsed = client.post("/api/resume/parse", json={"attachment_id": attachment["_id"]}).get_json()
    assert parsed["code"] == 0
    assert parsed["data"]["fields"]["highest_education"] == "硕士"
    assert client.get(f"/api/candidates/{cid}").get_json()["data"]["highest_education"] == "本科"
    saved = client.put(f"/api/candidates/{cid}", json={
        "version": 1, "highest_education": "本科", "education": parsed["data"]["fields"]["education"],
    }).get_json()
    assert saved["code"] == 0, saved
    assert client.get(f"/api/candidates/{cid}").get_json()["data"]["highest_education"] == "硕士"


def test_doctorate_remains_highest_even_if_undergraduate_is_later(client):
    login(client, "hr-001")
    cid = make_candidate(client)
    education = [
        {"school": "北京大学", "degree": "博士", "graduate_at": "2020"},
        {"school": "武汉大学", "degree": "本科", "graduate_at": "2024"},
    ]
    client.put(f"/api/candidates/{cid}", json={"version": 1, "education": education, "highest_education": "本科"})
    row = client.get("/api/candidates").get_json()["data"]["list"][0]
    assert row["highest_education"] == "博士"
    assert row["education_summary"]["degree"] == "博士"
