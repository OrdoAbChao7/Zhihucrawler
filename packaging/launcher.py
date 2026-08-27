import os

from zhihu_app.gui.app import create_app


def run_authenticated_selfcheck() -> None:
    from zhihu_app.auth.session import CookieStore
    from zhihu_app.config.settings import AppSettings
    from zhihu_app.engine.http_client import ZhihuApiClient

    settings = AppSettings.defaults()
    store = CookieStore(settings.profile_dir.parent / "cookies.json")
    ZhihuApiClient(store, proxy=settings.proxy).verify_login()


if __name__ == "__main__":
    if os.environ.get("ZHIHU_CRAWLER_SELFTEST") == "1":
        run_authenticated_selfcheck()
    else:
        create_app().run()
