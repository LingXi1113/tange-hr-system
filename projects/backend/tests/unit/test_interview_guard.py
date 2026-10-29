from datetime import datetime
from threading import Lock

import pytest
from pymongo.errors import DuplicateKeyError

from common import interview_guard as guard
from common.errors import BizError


class LeaseCollection:
    def __init__(self):
        self.lock = Lock()
        self.docs = {}
        self.acquired = []
        self.released = []

    def find_one_and_update(self, query, update, **kwargs):
        key = query["_id"]
        with self.lock:
            old = self.docs.get(key)
            owner = update["$set"]["owner"]
            if old and old["lease_until"] > datetime.now() and old["owner"] != owner:
                raise DuplicateKeyError("leased")
            self.docs[key] = dict(update["$set"])
            self.acquired.append(key)
            return self.docs[key]

    def update_one(self, query, update):
        with self.lock:
            key = query["_id"]
            assert self.docs[key]["owner"] == query["owner"]
            self.docs[key].update(update["$set"])
            self.released.append(key)


@pytest.fixture
def leases(monkeypatch):
    collection = LeaseCollection()
    monkeypatch.setattr(guard, "col", lambda name: collection)
    return collection


def test_candidate_and_interviewer_acquire_release_same_keys(leases):
    with guard.candidate_schedule_guard(42), guard.interviewer_schedule_guard("user-a"):
        assert leases.acquired == [42, "interviewer:user-a"]
    assert leases.released == ["interviewer:user-a", 42]


def test_exception_releases_namespaced_interviewer_lease(leases):
    with pytest.raises(ValueError):
        with guard.interviewer_schedule_guard("user-a"):
            raise ValueError("failed write")
    assert leases.released == ["interviewer:user-a"]


def test_same_interviewer_is_locked_across_different_candidates(leases):
    with guard.candidate_schedule_guard(1), guard.interviewer_schedule_guard("shared"):
        with guard.candidate_schedule_guard(2):
            with pytest.raises(BizError):
                with guard.candidate_schedule_guard("interviewer:shared", timeout_seconds=0.03):
                    pass
    with guard.interviewer_schedule_guard("shared"):
        pass
    assert leases.acquired.count("interviewer:shared") == 2


def test_unassigned_interviewer_does_not_create_lease(leases):
    with guard.interviewer_schedule_guard(None):
        pass
    assert not leases.acquired
