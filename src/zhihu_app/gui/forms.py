from __future__ import annotations

from collections.abc import Mapping

from ..engine.models import TaskType, ZhihuTask


def build_task_from_form(values: Mapping[str, str]) -> ZhihuTask:
    target = values.get("target", "").strip()
    if not target:
        raise ValueError("目标不能为空")
    try:
        max_items = int(values.get("max_items", "50"))
        interval = float(values.get("interval", "1.5"))
    except ValueError as exc:
        raise ValueError("数量和间隔必须是数字") from exc
    return ZhihuTask(
        TaskType(values.get("task_type", "search")), target,
        values.get("include_comments", "0") in {"1", "true", "True"},
        max_items, interval, values.get("proxy", "").strip(),
    )

