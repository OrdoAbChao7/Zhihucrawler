from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_and_licenses_exist():
    assert (ROOT / "src" / "zhihu_app" / "__init__.py").is_file()
    assert (ROOT / "README.md").is_file()
    assert (ROOT / "LICENSE.MediaCrawler.txt").is_file()
    assert (ROOT / "LICENSE.Apache-2.0.txt").is_file()
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "MediaCrawler" in notices
    assert "Zhihu-Collection-Downloader" in notices


def test_readme_describes_all_zhihu_modes():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for keyword in ("关键词搜索", "指定问题", "创作者", "收藏夹"):
        assert keyword in readme
