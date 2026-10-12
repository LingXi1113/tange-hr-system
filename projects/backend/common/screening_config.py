"""Database-backed matching dimensions used by intelligent resume screening."""
from __future__ import annotations

from datetime import datetime

from common.db import col, insert_doc, next_id
from common.screening import (
    DEFAULT_MATCH_ITEMS,
    EVALUATOR_NAMES,
    MATCH_SCOPE_NAMES,
    POSITION_TEMPLATES,
    match_scope_base_profile,
)


CONFIG_MARKER_ID = "screening_match_items_v1"
POSITION_CONFIG_MARKER_ID = "screening_position_match_items_v1"


def _seed_scope(scope: str, base_profile: str) -> None:
    for sort, item in enumerate(DEFAULT_MATCH_ITEMS[base_profile], start=1):
        if col("screening_match_items").find_one({"profile": scope, "key": item["key"]}):
            continue
        insert_doc("screening_match_items", {
            **item,
            "profile": scope,
            "base_profile": base_profile,
            "terms": list(item.get("terms") or []),
            "enabled": True,
            "sort": sort * 10,
            "is_default": True,
        })


def ensure_default_match_items() -> None:
    marker = col("system_config_markers").find_one({"_id": CONFIG_MARKER_ID})
    if not marker:
        for profile in DEFAULT_MATCH_ITEMS:
            _seed_scope(profile, profile)
        col("system_config_markers").update_one(
            {"_id": CONFIG_MARKER_ID},
            {"$setOnInsert": {"created_at": datetime.now()}},
            upsert=True,
        )
    position_marker = col("system_config_markers").find_one({"_id": POSITION_CONFIG_MARKER_ID})
    if not position_marker:
        for scope, template in POSITION_TEMPLATES.items():
            _seed_scope(scope, template["base_profile"])
        col("system_config_markers").update_one(
            {"_id": POSITION_CONFIG_MARKER_ID},
            {"$setOnInsert": {"created_at": datetime.now()}},
            upsert=True,
        )


def match_item_view(item: dict) -> dict:
    return {
        "id": item["_id"],
        "profile": item.get("profile", "tech"),
        "profile_name": MATCH_SCOPE_NAMES.get(item.get("profile"), ""),
        "base_profile": item.get("base_profile") or match_scope_base_profile(item.get("profile", "")),
        "key": item.get("key", ""),
        "name": item.get("name", ""),
        "weight": item.get("weight", 0),
        "evaluator": item.get("evaluator", "custom_terms"),
        "evaluator_name": EVALUATOR_NAMES.get(item.get("evaluator"), "自定义关键词"),
        "target_count": item.get("target_count", 1),
        "terms": list(item.get("terms") or []),
        "enabled": bool(item.get("enabled", True)),
        "sort": item.get("sort", 0),
        "is_default": bool(item.get("is_default", False)),
    }


def list_match_items(profile: str = "", *, enabled_only: bool = False) -> list[dict]:
    ensure_default_match_items()
    query: dict = {}
    if profile:
        query["profile"] = profile
    if enabled_only:
        query["enabled"] = True
    return list(col("screening_match_items").find(query).sort([
        ("profile", 1), ("sort", 1), ("_id", 1),
    ]))


def next_custom_match_item_id() -> tuple[int, str]:
    item_id = next_id("screening_match_items")
    return item_id, f"custom_{item_id}"
