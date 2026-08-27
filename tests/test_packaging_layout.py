from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_packaging_files_exist_and_spec_has_runtime_data():
    spec = (ROOT / "packaging" / "zhihu_crawler.spec").read_text(encoding="utf-8")
    assert "src" in spec
    assert "vendor" in spec
    assert "Playwright" in spec or "playwright" in spec
    for name in ("build.ps1", "create_shortcut.ps1", "smoke_test.ps1"):
        assert (ROOT / "packaging" / name).is_file()


def test_build_script_bundles_playwright_browser():
    script = (ROOT / "packaging" / "build.ps1").read_text(encoding="utf-8")
    assert "PLAYWRIGHT_BROWSERS_PATH" in script
    assert ".local-browsers" in script


def test_packaged_launcher_has_authenticated_selfcheck_mode():
    launcher = (ROOT / "packaging" / "launcher.py").read_text(encoding="utf-8")
    assert "ZHIHU_CRAWLER_SELFTEST" in launcher
    assert "verify_login" in launcher
