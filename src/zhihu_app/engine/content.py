from __future__ import annotations

from collections.abc import Callable
from typing import Any


def detail_uri(item: dict[str, Any]) -> str | None:
    item_id = item.get("id")
    item_type = item.get("type")
    if not item_id or item_type not in {"answer", "article", "zvideo"}:
        return None
    return f"/api/v4/{'zvideos' if item_type == 'zvideo' else item_type + 's'}/{item_id}"


def hydrate_content_items(items: list[dict[str, Any]], get: Callable[[str, dict[str, Any]], dict[str, Any]]) -> list[dict[str, Any]]:
    hydrated = []
    for item in items:
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            hydrated.append(item)
            continue
        uri = detail_uri(item)
        if not uri:
            hydrated.append(item)
            continue
        detail = get(uri, {})
        if isinstance(detail, dict) and isinstance(detail.get("data"), list) and detail["data"]:
            detail = detail["data"][0]
        merged = dict(item)
        if isinstance(detail, dict):
            merged.update(detail)
        hydrated.append(merged)
    return hydrated
