"""Candidate identity normalization and duplicate protection helpers."""
import re

from common.db import col


def normalize_phone(value) -> str:
    value = str(value or "").strip()
    return re.sub(r"\s+", "", value)


def normalize_email(value) -> str:
    return str(value or "").strip().lower()


def identity_keys(phone, email) -> dict:
    """Return stable, case-insensitive keys used by candidate unique indexes."""
    fields = {}
    phone_key = normalize_phone(phone)
    email_key = normalize_email(email)
    if phone_key:
        fields["phone_key"] = phone_key
    if email_key:
        fields["email_key"] = email_key
    return fields


def identity_update(phone, email, exempt: bool = False) -> tuple[dict, dict]:
    """Return ``$set`` and ``$unset`` fragments for a candidate identity."""
    if exempt:
        return {"dedupe_exempt": True}, {"phone_key": "", "email_key": ""}
    fields = identity_keys(phone, email)
    fields["dedupe_exempt"] = False
    unset = {}
    if "phone_key" not in fields:
        unset["phone_key"] = ""
    if "email_key" not in fields:
        unset["email_key"] = ""
    return fields, unset


def backfill_identity_keys() -> None:
    """Backfill safe keys for legacy candidates before unique indexes are built.

    Existing duplicate records are preserved. For a value already used by an
    earlier record, the key is left unset so index creation cannot destroy or
    reject historical data; normal API duplicate checks still report it.
    """
    seen_phone = set()
    seen_email = set()
    candidates = col("candidates").find({}).sort("_id", 1)
    for candidate in candidates:
        if candidate.get("dedupe_exempt"):
            continue
        set_fields = {}
        unset_fields = {}
        phone_key = normalize_phone(candidate.get("phone"))
        email_key = normalize_email(candidate.get("email"))
        if phone_key and phone_key not in seen_phone:
            seen_phone.add(phone_key)
            set_fields["phone_key"] = phone_key
        else:
            if phone_key:
                unset_fields["phone_key"] = ""
        if email_key and email_key not in seen_email:
            seen_email.add(email_key)
            set_fields["email_key"] = email_key
        else:
            if email_key:
                unset_fields["email_key"] = ""
        if "version" not in candidate:
            set_fields["version"] = 1
        if set_fields or unset_fields:
            update = {}
            if set_fields:
                update["$set"] = set_fields
            if unset_fields:
                update["$unset"] = unset_fields
            col("candidates").update_one({"_id": candidate["_id"]}, update)


def ensure_candidate_indexes() -> bool:
    """Backfill legacy keys and ensure candidate identity unique indexes."""
    from common.indexes import ensure_core_indexes

    backfill_identity_keys()
    return ensure_core_indexes()
