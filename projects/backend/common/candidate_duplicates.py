"""Two-level candidate identity checks and HR-bound confirmation challenges."""
import hashlib
import json
import re

from flask import current_app, g
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from common.candidate_identity import normalize_email, normalize_phone
from common.db import col
from common.errors import BizError
from common.logstore import write_log
from common.response import BizCode


def identity(payload):
    return {
        "name": re.sub(r"\s+", "", str(payload.get("name") or "")).casefold(),
        "phone": normalize_phone(payload.get("phone")),
        "email": normalize_email(payload.get("email")),
    }


def full_identity_key(payload):
    values = identity(payload)
    if not all(values.values()):
        return None
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def find_matches(payload, exclude_id=None):
    """A shared name or contact is a potential link; empty values never match."""
    incoming = identity(payload)
    conditions = []
    for field, value in incoming.items():
        if value:
            # Also find legacy/exempt profiles without normalized index keys.
            pattern = r"^\s*" + r"\s*".join(re.escape(c) for c in value) + r"\s*$"
            conditions.append({field: re.compile(pattern, re.IGNORECASE)})
    if not conditions:
        return []
    query = {"$or": conditions}
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    result = []
    for candidate in col("candidates").find(query).sort("_id", 1):
        previous = identity(candidate)
        matched = [k for k, v in incoming.items() if v and previous[k] == v]
        if matched:
            result.append((candidate, matched))
    exact = [item for item in result if len(item[1]) == 3]
    return exact[:1] or result


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="candidate-identity-review-v1")


def _fingerprint(payload, matches, exclude_id):
    clean = {k: v for k, v in payload.items() if k not in {"duplicate_review", "force"}}
    document = {
        "payload": clean, "exclude_id": exclude_id,
        "operator": g.current_user.user_id,
        "matches": [{"id": c["_id"], "version": c.get("version", 1), "identity": identity(c)}
                    for c, _ in matches],
    }
    return hashlib.sha256(json.dumps(document, sort_keys=True, default=str).encode()).hexdigest()


def review_token(payload, matches, exclude_id=None):
    return _serializer().dumps(_fingerprint(payload, matches, exclude_id))


def validate_review(payload, matches, exclude_id=None):
    """Return decisions only for an unchanged server-issued challenge."""
    review = payload.get("duplicate_review")
    if not isinstance(review, dict):
        return None
    try:
        signed = _serializer().loads(str(review.get("token") or ""), max_age=1800)
    except (BadSignature, SignatureExpired):
        return None
    if signed != _fingerprint(payload, matches, exclude_id):
        return None
    decisions = review.get("decisions")
    if not isinstance(decisions, dict) or set(decisions) != {str(c["_id"]) for c, _ in matches}:
        return None
    if any(v not in {"same", "different"} for v in decisions.values()):
        return None
    if list(decisions.values()).count("same") > 1:
        raise BizError(BizCode.PARAM_INVALID, "只能选择一个已有主档作为同一人")
    if any(len(fields) == 3 and decisions[str(c["_id"])] != "same" for c, fields in matches):
        raise BizError(BizCode.PARAM_INVALID, "姓名、手机、邮箱全部重合，请合并到已有主档")
    return decisions


def log_review(matches, decisions, candidate_id):
    for candidate, fields in matches:
        decision = decisions[str(candidate["_id"])]
        write_log(
            "candidate", "duplicate_confirm_same" if decision == "same" else "duplicate_confirm_different",
            g.current_user.user_id, g.current_user.name, biz_id=str(candidate_id),
            detail=f"历史候选人ID={candidate['_id']}；重合项={','.join(fields)}；"
                   f"HR确认={'同一人' if decision == 'same' else '非同一人'}",
        )
