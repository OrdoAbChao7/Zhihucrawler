from pathlib import Path
from threading import Event

from zhihu_app.config.settings import AppSettings
from zhihu_app.engine.collection_downloader import item_to_markdown, should_skip_existing
from zhihu_app.engine.collection_downloader import CollectionDownloader
from zhihu_app.engine.models import TaskType, ZhihuTask


def test_item_to_markdown_contains_frontmatter_and_content():
    item = {"type": "answer", "id": "1", "question": {"title": "测试"}, "url": "https://www.zhihu.com/answer/1", "content": "<p>正文</p>"}
    text = item_to_markdown(item)
    assert text.startswith("---\n")
    assert "url: https://www.zhihu.com/answer/1" in text
    assert "正文" in text


def test_should_skip_existing_only_when_url_and_updated_time_match(tmp_path):
    path = tmp_path / "item.md"
    path.write_text("---\nurl: https://www.zhihu.com/answer/1\nupdated_time: 10\n---\n", encoding="utf-8")
    assert should_skip_existing(path, "https://www.zhihu.com/answer/1", 10)
    assert not should_skip_existing(path, "https://www.zhihu.com/answer/2", 10)


def test_collection_downloader_routes_requests_through_authenticated_client(tmp_path):
    class ApiClient:
        def get(self, uri, params=None):
            assert uri == "/api/v4/collections/123/items"
            return {"data": [], "paging": {"is_end": True}}

    task = ZhihuTask(TaskType.COLLECTION, "https://www.zhihu.com/collection/123", output_dir=tmp_path)
    result = CollectionDownloader(AppSettings(tmp_path), api_client=ApiClient()).run(task, lambda _: None, Event())
    assert result.status == "completed"


def test_same_title_different_urls_do_not_overwrite(tmp_path):
    downloader = CollectionDownloader(AppSettings(tmp_path), session=object())
    items = [
        {"id": "1", "title": "同名", "url": "https://www.zhihu.com/p/1", "content": "一"},
        {"id": "2", "title": "同名", "url": "https://www.zhihu.com/p/2", "content": "二"},
    ]
    assert downloader.download_items(items, tmp_path, lambda _: None) == 2
    assert len(list((tmp_path / "markdown").glob("同名-*.md"))) == 2


def test_items_without_title_or_url_use_content_identity(tmp_path):
    downloader = CollectionDownloader(AppSettings(tmp_path), session=object())
    items = [
        {"content": "第一篇收藏内容"},
        {"content": "第二篇收藏内容"},
    ]

    assert downloader.download_items(items, tmp_path, lambda _: None) == 2
    files = list((tmp_path / "markdown").glob("*.md"))
    assert len(files) == 2
    assert len({path.read_text(encoding="utf-8") for path in files}) == 2


def test_image_download_uses_cookie_free_session_and_interval(tmp_path):
    class Response:
        content = b"image"
        def raise_for_status(self): pass

    class ApiSession:
        def get(self, *args, **kwargs):
            raise AssertionError("authenticated API session must not download images")

    class ImageSession:
        def __init__(self): self.urls = []
        def get(self, url, **kwargs):
            self.urls.append(url)
            return Response()

    image_session = ImageSession()
    sleeps = []
    downloader = CollectionDownloader(
        AppSettings(tmp_path), session=ApiSession(), image_session=image_session, sleep=sleeps.append,
    )
    downloader.image_interval = 1.5
    items = [{
        "id": "1", "title": "图片", "url": "https://www.zhihu.com/p/1",
        "content": '<img src="https://example.com/a.jpg"><img src="https://example.com/b.png">',
    }]
    downloader.download_items(items, tmp_path, lambda _: None)
    assert image_session.urls == ["https://example.com/a.jpg", "https://example.com/b.png"]
    assert sleeps == [1.5]


def test_dict_content_is_converted_without_replace_error():
    text = item_to_markdown({"content": {"html": "<p>正文</p>"}, "title": "测试"})
    assert "正文" in text


def test_collection_run_fetches_full_article_body(tmp_path):
    class ApiClient:
        def get(self, uri, params=None):
            if uri == "/api/v4/collections/123/items":
                return {"data": [{"type": "article", "id": "9", "title": "文章", "url": "https://www.zhihu.com/p/9"}], "paging": {"is_end": True}}
            if uri == "/api/v4/articles/9":
                return {"type": "article", "id": "9", "title": "文章", "url": "https://www.zhihu.com/p/9", "content": "<p>完整正文</p>"}
            raise AssertionError(uri)

    task = ZhihuTask(TaskType.COLLECTION, "https://www.zhihu.com/collection/123", output_dir=tmp_path)
    result = CollectionDownloader(AppSettings(tmp_path), api_client=ApiClient()).run(task, lambda _: None, Event())
    assert result.items_processed == 1
    assert "完整正文" in next((tmp_path / "markdown").glob("*.md")).read_text(encoding="utf-8")


def test_failed_image_downloads_are_also_throttled(tmp_path):
    import requests

    class ImageSession:
        def get(self, *args, **kwargs):
            raise requests.RequestException("failed")

    sleeps = []
    downloader = CollectionDownloader(
        AppSettings(tmp_path), session=object(), image_session=ImageSession(), sleep=sleeps.append,
    )
    downloader.image_interval = 1.0
    downloader.download_items([{
        "id": "1", "content": '<img src="https://example.com/a.jpg"><img src="https://example.com/b.jpg">',
    }], tmp_path, lambda _: None)
    assert sleeps == [1.0]
