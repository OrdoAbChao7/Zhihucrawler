import threading
import time

from zhihu_app.engine.models import TaskResult, TaskType, ZhihuTask
from zhihu_app.engine.runner import TaskRunner


def test_runner_completes_task_and_can_cancel():
    done = []
    runner = TaskRunner(lambda task, emit, cancel: TaskResult("completed", 1))
    runner.on_done = done.append
    runner.submit(ZhihuTask(TaskType.SEARCH, "test"))
    runner.join(timeout=2)
    assert done[0].items_processed == 1
    runner.cancel()

