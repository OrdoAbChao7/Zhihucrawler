from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse
from pathlib import Path


class TaskType(str, Enum):
    SEARCH = "search"
    QUESTION = "question"
    CREATOR = "creator"
    COLLECTION = "collection"


@dataclass
class ZhihuTask:
    task_type: TaskType
    target: str
    include_comments: bool = False
    max_items: int = 50
    interval_seconds: float = 1.5
    proxy: str = ""
    output_dir: Path | None = None

    def __post_init__(self) -> None:
        self.task_type = TaskType(self.task_type)
        self.target = self.target.strip()
        if not self.target:
            raise ValueError("target must not be empty")
        if self.max_items < 1:
            raise ValueError("max_items must be positive")
        if self.interval_seconds < 0.5:
            raise ValueError("interval must be at least 0.5 seconds")
        if self.output_dir is not None:
            self.output_dir = Path(self.output_dir)


@dataclass
class TaskResult:
    status: str
    items_processed: int = 0
    output_dir: Path | None = None
    error_message: str = ""


def classify_target(url: str) -> TaskType:
    parsed = urlparse(url.strip())
    if parsed.netloc not in {"www.zhihu.com", "zhihu.com", "zhuanlan.zhihu.com"}:
        raise ValueError("target must be a Zhihu URL")
    path = parsed.path.rstrip("/")
    if path.startswith("/question/"):
        return TaskType.QUESTION
    if path.startswith("/people/"):
        return TaskType.CREATOR
    if path.startswith("/collection/"):
        return TaskType.COLLECTION
    raise ValueError("unsupported Zhihu URL")

