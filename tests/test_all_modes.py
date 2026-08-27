from zhihu_app.engine.collection_downloader import collection_api_for_target
from zhihu_app.engine.mediacrawler_adapter import creator_api_urls


def test_creator_mode_covers_answers_articles_and_videos():
    urls = creator_api_urls("https://www.zhihu.com/people/demo")
    assert urls == [
        "https://www.zhihu.com/api/v4/members/demo/answers",
        "https://www.zhihu.com/api/v4/members/demo/articles",
        "https://www.zhihu.com/api/v4/members/demo/zvideos",
    ]


def test_creator_mode_uses_url_path_without_query_as_token():
    assert creator_api_urls("https://www.zhihu.com/people/demo?tab=answers")[0].endswith("/members/demo/answers")


def test_collection_downloader_distinguishes_collection_and_member_posts():
    assert collection_api_for_target("https://www.zhihu.com/collection/123").endswith("collections/123/items")
    assert collection_api_for_target("https://www.zhihu.com/people/demo/posts").endswith("members/demo/articles")
