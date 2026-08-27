from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import TaskType, ZhihuTask


@dataclass(frozen=True)
class OutputPaths:
    task_dir: Path
    raw_dir: Path
    markdown_dir: Path
    image_dir: Path


def _safe_label(label: str) -> str:
    value = label.strip()
    if not value or value in {".", ".."} or ".." in value or "/" in value or "\\" in value:
        raise ValueError("label must be a safe single path component")
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    return value[:100] or "task"


def build_output_paths(root: Path, task_type: TaskType, label: str, now: datetime) -> OutputPaths:
    root = Path(root).resolve()
    task_dir = root / task_type.value / now.strftime("%Y-%m-%d") / f"{now:%H%M%S%f}-{_safe_label(label)}"
    if not task_dir.is_relative_to(root):
        raise ValueError("output path escapes root")
    return OutputPaths(task_dir, task_dir / "raw", task_dir / "markdown", task_dir / "images")


def build_task_output_paths(root: Path, task: ZhihuTask, now: datetime | None = None) -> OutputPaths:
    digest = hashlib.sha256(task.target.encode("utf-8")).hexdigest()[:12]
    return build_output_paths(root, task.task_type, digest, now or datetime.now())
