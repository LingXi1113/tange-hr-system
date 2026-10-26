"""Public application parsing must preserve text without overwriting user input."""
from copy import deepcopy

import pytest

from common import resume_service as service


@pytest.fixture
def isolated_service(monkeypatch):
    documents = {
        ("attachments", 1): {"file_path": "resume-key", "file_name": "resume.docx"},
        ("candidates", 2): {"name": "Manual name", "city": ""},
    }
    updates, logs, cleanups = [], [], []

    def update(collection, doc_id, values):
        updates.append((collection, doc_id, deepcopy(values)))
        documents[(collection, doc_id)].update(values)

    class Storage:
        def cleanup_local(self, *args):
            cleanups.append(args)

    monkeypatch.setattr(service, "get_by_id", lambda collection, doc_id: documents.get((collection, doc_id)))
    monkeypatch.setattr(service, "update_doc", update)
    monkeypatch.setattr(service, "write_log", lambda *args, **kwargs: logs.append((args, kwargs)))
    monkeypatch.setattr(service, "resolve_local", lambda *args: ("unused-local.docx", False))
    monkeypatch.setattr(service, "get_storage", lambda app: Storage())
    return documents, updates, logs, cleanups


def test_success_preserves_text_and_only_fills_empty_candidate_fields(monkeypatch, isolated_service):
    documents, _, logs, _ = isolated_service
    fields = {**deepcopy(service.EMPTY_FIELDS), "name": "Parsed name", "city": "Test city"}
    monkeypatch.setattr(service, "parse_resume_file_with_text",
                        lambda *args: (fields, "system", "Original resume text"))
    result, status = service.auto_parse_attachment(object(), 1, 2)
    assert status == "system"
    assert result == fields
    assert documents[("attachments", 1)]["parsed_text"] == "Original resume text"
    assert documents[("attachments", 1)]["parsed_fields"] == fields
    assert documents[("candidates", 2)]["name"] == "Manual name"
    assert documents[("candidates", 2)]["city"] == "Test city"
    assert len(logs) == 1


def test_failed_parse_keeps_available_text_without_updating_candidate(monkeypatch, isolated_service):
    documents, _, logs, _ = isolated_service
    fields = deepcopy(service.EMPTY_FIELDS)
    monkeypatch.setattr(service, "parse_resume_file_with_text",
                        lambda *args: (fields, "failed", "Partial extracted text"))
    assert service.auto_parse_attachment(object(), 1, 2)[1] == "failed"
    assert documents[("attachments", 1)]["parsed_text"] == "Partial extracted text"
    assert documents[("candidates", 2)] == {"name": "Manual name", "city": ""}
    assert not logs


def test_parser_exception_records_failure_and_cleans_temporary_file(monkeypatch, isolated_service):
    documents, _, _, cleanups = isolated_service
    monkeypatch.setattr(service, "resolve_local", lambda *args: ("temporary.docx", True))

    def fail(*args):
        raise RuntimeError("Synthetic parse failure")

    monkeypatch.setattr(service, "parse_resume_file_with_text", fail)
    assert service.auto_parse_attachment(object(), 1, 2)[1] == "failed"
    assert documents[("attachments", 1)]["parsed_text"] == ""
    assert documents[("attachments", 1)]["parse_status"] == "failed"
    assert cleanups == [("temporary.docx", "resume-key")]


def test_resolve_exception_does_not_escape(monkeypatch, isolated_service):
    documents, _, _, _ = isolated_service

    def fail(*args):
        raise RuntimeError("Synthetic storage failure")

    monkeypatch.setattr(service, "resolve_local", fail)
    assert service.auto_parse_attachment(object(), 1, 2)[1] == "failed"
    assert documents[("attachments", 1)]["parsed_text"] == ""


def test_cleanup_exception_does_not_discard_successful_parse(monkeypatch, isolated_service):
    documents, _, _, _ = isolated_service
    monkeypatch.setattr(service, "resolve_local", lambda *args: ("temporary.docx", True))
    monkeypatch.setattr(service, "parse_resume_file_with_text",
                        lambda *args: (deepcopy(service.EMPTY_FIELDS), "system", "Extracted text"))

    class BrokenStorage:
        def cleanup_local(self, *args):
            raise RuntimeError("Synthetic cleanup failure")

    monkeypatch.setattr(service, "get_storage", lambda app: BrokenStorage())
    assert service.auto_parse_attachment(object(), 1, 2)[1] == "system"
    assert documents[("attachments", 1)]["parsed_text"] == "Extracted text"


def test_missing_attachment_does_not_parse_or_write(monkeypatch, isolated_service):
    _, updates, logs, _ = isolated_service

    def unexpected(*args):
        pytest.fail("Missing attachments must not invoke the parser")

    monkeypatch.setattr(service, "parse_resume_file_with_text", unexpected)
    assert service.auto_parse_attachment(object(), 999, 2)[1] == "failed"
    assert not updates
    assert not logs
