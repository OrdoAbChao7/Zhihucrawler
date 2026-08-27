import json
from threading import Event

from zhihu_app.engine.mediacrawler_adapter import normalise_content_items
from zhihu_app.config.settings import AppSettings
from zhihu_app.engine.mediacrawler_adapter import MediaCrawlerAdapter
from zhihu_app.engine.models import TaskType, ZhihuTask


def test_normalise_content_items_returns_common_records(tmp_path):
    payload = json.loads((tmp_path / "fixture.json").write_text("{}", encoding="utf-8") and "{}")
    del payload
    records = normalise_content_items(
        [{"type": "answer", "id": "1", "question": {"title": "问题"}, "url": "https://www.zhihu.com/answer/1"}]
    )
    assert records[0]["kind"] == "answer"
    assert records[0]["url"].endswith("/answer/1")


def test_normalise_search_items_unwraps_objects_and_drops_non_content():
    records = normalise_content_items([
        {"type": "ai_zhida", "object": {"type": "query"}},
        {"type": "search_result", "object": {
            "type": "answer", "id": 2, "url": "https://www.zhihu.com/answer/2",
            "question": {"title": "有效结果"},
        }},
    ])
    assert len(records) == 1
    assert records[0]["id"] == "2"
    assert records[0]["title"] == "有效结果"


def test_media_adapter_writes_raw_and_markdown_outputs(tmp_path):
    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"data": [{"type": "answer", "id": "1", "url": "https://www.zhihu.com/answer/1", "content": "<p>正文</p>"}]}
    class Session:
        def get(self, *args, **kwargs): return Response()
    task = ZhihuTask(TaskType.SEARCH, "测试", output_dir=tmp_path)
    result = MediaCrawlerAdapter(AppSettings(tmp_path), Session()).run(task, lambda _: None, Event())
    assert result.items_processed == 1
    assert list((tmp_path / "raw").glob("*.json"))
    assert list((tmp_path / "markdown").glob("*.md"))


def test_media_adapter_routes_requests_through_authenticated_client(tmp_path):
    class ApiClient:
        def __init__(self): self.calls = []
        def get(self, uri, params=None):
            self.calls.append((uri, params))
            return {"data": [{"type": "answer", "id": "1", "url": "https://www.zhihu.com/answer/1"}]}

    api = ApiClient()
    task = ZhihuTask(TaskType.SEARCH, "测试", output_dir=tmp_path)
    result = MediaCrawlerAdapter(AppSettings(tmp_path), api_client=api).run(task, lambda _: None, Event())
    assert result.items_processed == 1
    assert api.calls[0][0] == "/api/v4/search_v3"


def test_question_mode_paginates_until_max_items(tmp_path):
    class ApiClient:
        def __init__(self): self.calls = []
        def get(self, uri, params=None):
            self.calls.append((uri, dict(params or {})))
            offset = params.get("offset", 0)
            return {
                "data": [{"type": "answer", "id": str(offset + 1), "url": f"https://www.zhihu.com/answer/{offset + 1}"}],
                "paging": {"is_end": offset >= 1},
            }

    api = ApiClient()
    task = ZhihuTask(TaskType.QUESTION, "https://www.zhihu.com/question/123", max_items=2, output_dir=tmp_path)
    result = MediaCrawlerAdapter(AppSettings(tmp_path), api_client=api).run(task, lambda _: None, Event())
    assert result.items_processed == 2
    assert [call[1]["offset"] for call in api.calls] == [0, 1]


def test_question_request_uses_zhihu_compatible_include_fields(tmp_path):
    class ApiClient:
        def __init__(self): self.params = None
        def get(self, uri, params=None):
            self.params = params
            return {"data": [], "paging": {"is_end": True}}

    api = ApiClient()
    task = ZhihuTask(TaskType.QUESTION, "https://www.zhihu.com/question/123", output_dir=tmp_path)
    MediaCrawlerAdapter(AppSettings(tmp_path), api_client=api).run(task, lambda _: None, Event())
    assert "excerpt" in api.params["include"]
    assert "sort_by" in api.params


def test_task_proxy_is_applied_to_http_session(tmp_path):
    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"data": []}
    class Session:
        def __init__(self): self.proxies = {}
        def get(self, *args, **kwargs): return Response()

    session = Session()
    task = ZhihuTask(TaskType.SEARCH, "测试", proxy="http://127.0.0.1:7890", output_dir=tmp_path)
    MediaCrawlerAdapter(AppSettings(tmp_path), session=session).run(task, lambda _: None, Event())
    assert session.proxies["https"] == task.proxy


def test_creator_mode_round_robins_content_types(tmp_path):
    class ApiClient:
        def get(self, uri, params=None):
            kind = "answer" if "/answers" in uri else "article" if "/articles" in uri else "zvideo"
            if uri.split("/")[-1] not in {"answers", "articles", "zvideos"}:
                return {"type": kind, "id": kind, "url": f"https://www.zhihu.com/{kind}/1", "content": "正文"}
            return {
                "data": [{"type": kind, "id": kind, "url": f"https://www.zhihu.com/{kind}/1"}],
                "paging": {"is_end": True},
            }

    task = ZhihuTask(TaskType.CREATOR, "https://www.zhihu.com/people/demo", max_items=3, output_dir=tmp_path)
    MediaCrawlerAdapter(AppSettings(tmp_path), api_client=ApiClient()).run(task, lambda _: None, Event())
    records = json.loads((tmp_path / "raw" / "items.json").read_text(encoding="utf-8"))
    assert [record["kind"] for record in records] == ["answer", "article", "zvideo"]


def test_creator_mode_fetches_full_article_body_from_detail_endpoint(tmp_path):
    class ApiClient:
        def get(self, uri, params=None):
            if uri.endswith("/articles"):
                return {"data": [{"type": "article", "id": "9", "title": "文章", "url": "https://www.zhihu.com/p/9"}], "paging": {"is_end": True}}
            if uri == "/api/v4/articles/9":
                return {"type": "article", "id": "9", "title": "文章", "url": "https://www.zhihu.com/p/9", "content": "<p>完整正文</p>"}
            return {"data": [], "paging": {"is_end": True}}

    task = ZhihuTask(TaskType.CREATOR, "https://www.zhihu.com/people/demo", max_items=1, output_dir=tmp_path)
    MediaCrawlerAdapter(AppSettings(tmp_path), api_client=ApiClient()).run(task, lambda _: None, Event())
    raw = json.loads((tmp_path / "raw" / "items.json").read_text(encoding="utf-8"))
    assert raw[0]["content"] == "<p>完整正文</p>"


def test_creator_mode_continues_when_one_detail_is_risk_controlled(tmp_path):
    from zhihu_app.engine.errors import ZhihuRiskControlError

    class ApiClient:
        def get(self, uri, params=None):
            if uri.endswith("/answers"):
                return {"data": [{"type": "answer", "id": "1", "url": "https://www.zhihu.com/a/1", "excerpt": "回答摘要"}], "paging": {"is_end": True}}
            if uri.endswith("/articles"):
                return {"data": [{"type": "article", "id": "2", "url": "https://www.zhihu.com/p/2", "excerpt": "文章摘要"}], "paging": {"is_end": True}}
            if uri.endswith("/zvideos"):
                return {"data": [], "paging": {"is_end": True}}
            if uri == "/api/v4/answers/1":
                raise ZhihuRiskControlError("40362")
            if uri == "/api/v4/articles/2":
                return {"type": "article", "id": "2", "url": "https://www.zhihu.com/p/2", "content": "<p>文章正文</p>"}
            raise AssertionError(uri)

    task = ZhihuTask(TaskType.CREATOR, "https://www.zhihu.com/people/demo", max_items=2, output_dir=tmp_path)
    result = MediaCrawlerAdapter(AppSettings(tmp_path), api_client=ApiClient()).run(task, lambda _: None, Event())
    assert result.items_processed == 2
    raw = json.loads((tmp_path / "raw" / "items.json").read_text(encoding="utf-8"))
    assert any(item["content"] == "<p>文章正文</p>" for item in raw)
