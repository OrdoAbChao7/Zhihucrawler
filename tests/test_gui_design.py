from zhihu_app.gui.app import build_output_hint, task_type_label
from pathlib import Path


def test_task_type_labels_are_user_friendly():
    assert task_type_label("search") == "搜索内容"
    assert task_type_label("creator") == "用户回答 / 文章"
    assert task_type_label("collection") == "收藏夹 / 用户文章"


def test_output_hint_mentions_markdown_directory():
    hint = build_output_hint("E:/portable/output")
    assert str(Path("E:/portable/output")) in hint
    assert "markdown" in hint
