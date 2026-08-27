from __future__ import annotations

import threading
from collections.abc import Callable

from .models import TaskResult, ZhihuTask


class TaskRunner:
    def __init__(self, worker: Callable[[ZhihuTask, Callable[[str], None], threading.Event], TaskResult]) -> None:
        self.worker = worker
        self.on_log: Callable[[str], None] = lambda message: None
        self.on_done: Callable[[TaskResult], None] = lambda result: None
        self.on_error: Callable[[Exception], None] = lambda error: None
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def submit(self, task: ZhihuTask) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("已有任务正在运行")
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, args=(task,), daemon=True)
        self._thread.start()

    def _run(self, task: ZhihuTask) -> None:
        try:
            self.on_done(self.worker(task, self.on_log, self._cancel))
        except Exception as exc:
            self.on_error(exc)

    def cancel(self) -> None:
        self._cancel.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

