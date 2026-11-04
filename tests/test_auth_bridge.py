from pathlib import Path

import pytest

from zhihu_app.auth.session import CookieStore, has_zhihu_auth
from zhihu_app.engine.http_client import NodeZhihuSigner, ZhihuApiClient
from zhihu_app.engine.errors import ZhihuRateLimitError, ZhihuRiskControlError


AUTH_COOKIES = [
    {"name": "z_c0", "value": "z-token", "domain": ".zhihu.com", "path": "/"},
    {"name": "d_c0", "value": "d-token", "domain": ".zhihu.com", "path": "/"},
    {"name": "SESSIONID", "value": "session-token", "domain": ".zhihu.com", "path": "/"},
]


def test_cookie_store_round_trips_authenticated_browser_cookies(tmp_path):
    store = CookieStore(tmp_path / "cookies.json")
    store.save(AUTH_COOKIES)

    assert has_zhihu_auth(store.load())
    assert store.as_requests_dict() == {
        "z_c0": "z-token",
        "d_c0": "d-token",
        "SESSIONID": "session-token",
    }


def test_auth_cookies_are_scoped_to_zhihu_domains(tmp_path):
    import requests

    store = CookieStore(tmp_path / "cookies.json")
    store.save(AUTH_COOKIES)
    session = requests.Session()
    store.apply_to_session(session)

    zhihu = session.prepare_request(requests.Request("GET", "https://www.zhihu.com/api/v4/me"))
    external = session.prepare_request(requests.Request("GET", "https://example.com/image.jpg"))
    assert "z_c0=" in zhihu.headers.get("Cookie", "")
    assert "z_c0=" not in external.headers.get("Cookie", "")


def test_cookie_store_rejects_snapshot_without_authentication(tmp_path):
    store = CookieStore(tmp_path / "cookies.json")
    with pytest.raises(ValueError, match="z_c0.*d_c0"):
        store.save([{"name": "q_c1", "value": "anonymous", "domain": ".zhihu.com", "path": "/"}])


def test_corrupt_cookie_file_is_treated_as_logged_out(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text("not-json", encoding="utf-8")
    assert CookieStore(path).load() == []


def test_api_client_injects_saved_cookies_and_signature(tmp_path):
    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = '{"uid":"1","name":"tester"}'
        def raise_for_status(self): pass
        def json(self): return {"uid": "1", "name": "tester"}

    class RecordingSession:
        def __init__(self):
            import requests
            self.cookies = requests.cookies.RequestsCookieJar()
            self.headers = {}
            self.calls = []
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return Response()

    class FixedSigner:
        def sign(self, uri, cookie_header):
            assert uri == "/api/v4/me?include=email%2Cis_active"
            assert "d_c0=d-token" in cookie_header
            return {"x-zst-81": "signed-zst", "x-zse-96": "signed-zse"}

    store = CookieStore(tmp_path / "cookies.json")
    store.save(AUTH_COOKIES)
    session = RecordingSession()
    client = ZhihuApiClient(store, signer=FixedSigner(), session=session)

    result = client.get("/api/v4/me", {"include": "email,is_active"})

    assert result["name"] == "tester"
    assert session.cookies.get("z_c0") == "z-token"
    sent_headers = session.calls[0][1]["headers"]
    assert sent_headers["x-zse-96"] == "signed-zse"


def test_real_node_signer_returns_required_headers():
    root = Path(__file__).resolve().parents[1]
    signer = NodeZhihuSigner(
        node_path=root / ".venv" / "Lib" / "site-packages" / "playwright" / "driver" / "node.exe",
        script_path=root / "vendor" / "mediacrawler" / "libs" / "zhihu.js",
    )
    result = signer.sign("/api/v4/me?include=email", "d_c0=test-token; z_c0=test-login")
    assert result["x-zst-81"]
    assert result["x-zse-96"].startswith("2.0_")


def test_api_client_respects_minimum_request_interval(tmp_path):
    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"ok": True}

    class Session:
        def __init__(self):
            import requests
            self.cookies = requests.cookies.RequestsCookieJar()
        def get(self, *args, **kwargs): return Response()

    class Signer:
        def sign(self, *args): return {"x-zst-81": "a", "x-zse-96": "b"}

    times = iter([10.0, 10.2, 11.0])
    sleeps = []
    store = CookieStore(tmp_path / "cookies.json")
    store.save(AUTH_COOKIES)
    client = ZhihuApiClient(
        store, signer=Signer(), session=Session(), min_interval=1.0,
        clock=lambda: next(times), sleep=sleeps.append,
    )
    client.get("/first")
    client.get("/second")
    assert sleeps == [pytest.approx(0.8)]


def test_api_client_reports_zhihu_risk_control_instead_of_expired_login(tmp_path):
    class Response:
        status_code = 403
        def json(self): return {"error": {"code": 40362, "message": "当前请求存在异常"}}

    class Session:
        def __init__(self):
            import requests
            self.cookies = requests.cookies.RequestsCookieJar()
        def get(self, *args, **kwargs): return Response()

    class Signer:
        def sign(self, *args): return {"x-zst-81": "a", "x-zse-96": "b"}

    store = CookieStore(tmp_path / "cookies.json")
    store.save(AUTH_COOKIES)
    client = ZhihuApiClient(store, signer=Signer(), session=Session())
    with pytest.raises(ZhihuRiskControlError, match="风控.*40362"):
        client.get("/api/v4/questions/1/answers")


def test_api_client_warms_browser_once_and_retries_risk_control(tmp_path):
    class Response:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self.payload = payload

        def json(self): return self.payload
        def raise_for_status(self): pass

    class Session:
        def __init__(self):
            import requests
            self.cookies = requests.cookies.RequestsCookieJar()
            self.responses = [
                Response(403, {"error": {"code": 40362}}),
                Response(200, {"data": [{"id": "1"}]}),
            ]
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return self.responses.pop(0)

    class Signer:
        def sign(self, *args): return {"x-zst-81": "a", "x-zse-96": "b"}

    store = CookieStore(tmp_path / "cookies.json")
    store.save(AUTH_COOKIES)
    warmed = []
    session = Session()
    client = ZhihuApiClient(
        store, signer=Signer(), session=session,
        browser_warmup=lambda uri: warmed.append(uri) or True,
    )

    assert client.get("/api/v4/questions/123/answers") == {"data": [{"id": "1"}]}
    assert warmed == ["/api/v4/questions/123/answers"]
    assert session.calls[0][1]["headers"]["referer"].endswith("/question/123")
    assert session.calls[0][1]["headers"]["origin"] == "https://www.zhihu.com"
