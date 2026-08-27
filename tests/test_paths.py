from datetime import datetime

import pytest

from zhihu_app.engine.models import TaskType, ZhihuTask
from zhihu_app.engine.paths import build_output_paths, build_task_output_paths
from zhihu_app.config.settings import AppSettings


def test_build_output_paths_stays_under_root(tmp_path):
    paths = build_output_paths(tmp_path, TaskType.QUESTION, "问题:测试", datetime(2026, 8, 27))
    assert paths.task_dir.is_relative_to(tmp_path)
    assert paths.raw_dir == paths.task_dir / "raw"
    assert paths.markdown_dir == paths.task_dir / "markdown"
    assert paths.image_dir == paths.task_dir / "images"
    assert ":" not in paths.task_dir.name


def test_rejects_path_traversal_label(tmp_path):
    with pytest.raises(ValueError, match="label"):
        build_output_paths(tmp_path, TaskType.SEARCH, "../../escape", datetime.now())


def test_output_paths_do_not_collide_for_repeated_tasks(tmp_path):
    first = build_output_paths(tmp_path, TaskType.SEARCH, "same", datetime(2026, 8, 27, 10, 0, 0, 1))
    second = build_output_paths(tmp_path, TaskType.SEARCH, "same", datetime(2026, 8, 27, 10, 0, 0, 2))
    assert first.task_dir != second.task_dir


def test_task_output_paths_accept_url_targets(tmp_path):
    task = ZhihuTask(TaskType.QUESTION, "https://www.zhihu.com/question/123")
    paths = build_task_output_paths(tmp_path, task, datetime(2026, 8, 27, 10, 0))
    assert paths.task_dir.is_relative_to(tmp_path)
    assert "question" in paths.task_dir.parts


def test_frozen_app_writes_output_beside_executable(monkeypatch, tmp_path):
    import zhihu_app.config.settings as settings_module

    monkeypatch.setattr(settings_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(settings_module.sys, "executable", str(tmp_path / "知乎采集器.exe"))
    settings = AppSettings.defaults()

    assert settings.output_dir == tmp_path / "output"
    assert settings.profile_dir != settings.output_dir / "data" / "browser_profile"
