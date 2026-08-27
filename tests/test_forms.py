import pytest

from zhihu_app.gui.forms import build_task_from_form
from zhihu_app.engine.models import TaskType


def test_build_search_task_from_form():
    task = build_task_from_form({"task_type": "search", "target": "量子力学", "max_items": "10", "interval": "1.5"})
    assert task.task_type is TaskType.SEARCH
    assert task.max_items == 10


def test_form_rejects_missing_target():
    with pytest.raises(ValueError, match="目标"):
        build_task_from_form({"task_type": "question", "target": ""})

