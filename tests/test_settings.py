import pytest
import sys

from zhihu_app.config.settings import AppSettings


def test_settings_have_safe_defaults(tmp_path):
    settings = AppSettings.load(tmp_path / "missing.json")
    assert settings.output_dir == tmp_path / "output"
    assert settings.interval_seconds == 1.5
    assert settings.max_items == 50


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    original = AppSettings(output_dir=tmp_path / "out", interval_seconds=2.0, max_items=8)
    original.save(path)
    loaded = AppSettings.load(path)
    assert loaded == original


def test_settings_reject_unsafe_values(tmp_path):
    with pytest.raises(ValueError, match="interval"):
        AppSettings(output_dir=tmp_path, interval_seconds=0.1)
    with pytest.raises(ValueError, match="max_items"):
        AppSettings(output_dir=tmp_path, max_items=0)


def test_frozen_defaults_keep_output_beside_exe_and_profile_in_app_data(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "executable", str(tmp_path / "portable" / "知乎采集器.exe"))
    settings = AppSettings.defaults()
    assert settings.output_dir == tmp_path / "portable" / "output"
    assert settings.profile_dir == tmp_path / "ZhihuCrawler" / "browser_profile"
