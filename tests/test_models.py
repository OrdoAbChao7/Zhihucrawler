import pytest

from zhihu_app.engine.models import TaskType, ZhihuTask, classify_target


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.zhihu.com/question/123", TaskType.QUESTION),
        ("https://www.zhihu.com/people/demo", TaskType.CREATOR),
        ("https://www.zhihu.com/collection/123", TaskType.COLLECTION),
    ],
)
def test_classify_target(url, expected):
    assert classify_target(url) is expected


def test_task_rejects_empty_target():
    with pytest.raises(ValueError, match="target"):
        ZhihuTask(task_type=TaskType.QUESTION, target="")

