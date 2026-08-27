from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlencode

import requests

from ..auth.session import CookieStore, has_zhihu_auth
from .errors import ZhihuAuthError, ZhihuNetworkError, ZhihuParseError, ZhihuRateLimitError, ZhihuRiskControlError


class Signer(Protocol):
    def sign(self, uri: str, cookie_header: str) -> dict[str, str]: ...


class NodeZhihuSigner:
    _WRAPPER = (
        "const fs=require('fs');"
        "const input=JSON.parse(fs.readFileSync(0,'utf8'));"
        "eval(fs.readFileSync(process.argv[1],'utf8'));"
        "process.stdout.write(JSON.stringify(get_sign(input.url,input.cookies)));"
    )

    def __init__(self, node_path: Path | None = None, script_path: Path | None = None) -> None:
        self.node_path = node_path or self._default_node_path()
        self.script_path = script_path or self._default_script_path()

    @staticmethod
    def _default_node_path() -> Path:
        from playwright._impl._driver import compute_driver_executable
        node_path, _ = compute_driver_executable()
        return Path(node_path)

    @staticmethod
    def _default_script_path() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent / "_internal" / "vendor" / "mediacrawler" / "libs" / "zhihu.js"
        return Path(__file__).resolve().parents[3] / "vendor" / "mediacrawler" / "libs" / "zhihu.js"

    def sign(self, uri: str, cookie_header: str) -> dict[str, str]:
        if not self.node_path.is_file() or not self.script_path.is_file():
            raise ZhihuParseError("知乎签名运行时缺失，请重新构建应用")
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            completed = subprocess.run(
                [str(self.node_path), "-e", self._WRAPPER, str(self.script_path)],
                input=json.dumps({"url": uri, "cookies": cookie_header}),
                text=True,
                capture_output=True,
                check=True,
                timeout=15,
                creationflags=creation_flags,
            )
            result = json.loads(completed.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            raise ZhihuParseError(f"知乎请求签名失败：{exc}") from exc
        if not result.get("x-zse-96") or not result.get("x-zst-81"):
            raise ZhihuParseError("知乎签名结果不完整")
        return result


class ZhihuApiClient:
    BASE_URL = "https://www.zhihu.com"

    def __init__(
        self, cookie_store: CookieStore, signer: Signer | None = None, session=None,
        proxy: str = "", min_interval: float = 0.0,
        clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
        browser_warmup: Callable[[str], bool] | None = None,
    ) -> None:
        cookies = cookie_store.load()
        if not has_zhihu_auth(cookies):
            raise ZhihuAuthError("未找到有效登录态，请先点击“登录知乎”并等待登录完成")
        self.session = session or requests.Session()
        cookie_store.apply_to_session(self.session)
        self.signer = signer or NodeZhihuSigner()
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last_request_at: float | None = None
        self.cookie_store = cookie_store
        self.browser_warmup = browser_warmup
        if proxy and hasattr(self.session, "proxies"):
            self.session.proxies.update({"http": proxy, "https": proxy})

    def get(
        self, uri: str, params: dict[str, Any] | None = None, *, _warmup_attempted: bool = False
    ) -> dict[str, Any]:
        now = self._clock()
        if self._last_request_at is not None:
            remaining = self.min_interval - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last_request_at = now
        query = urlencode(params or {}, doseq=True)
        final_uri = f"{uri}?{query}" if query else uri
        cookie_header = "; ".join(f"{key}={value}" for key, value in self.session.cookies.get_dict().items())
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "cache-control": "no-cache",
            "origin": self.BASE_URL,
            "referer": self._referer_for(uri),
            "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "x-api-version": "3.0.91",
            "x-app-za": "OS=Web",
            "x-requested-with": "fetch",
            "x-zse-93": "101_3_3.0",
            **self.signer.sign(final_uri, cookie_header),
        }
        response = self._request(final_uri, headers)
        if response.status_code == 403:
            try:
                error = response.json().get("error", {})
            except (ValueError, AttributeError):
                error = {}
            if error.get("code") == 40362:
                if not _warmup_attempted and self.browser_warmup and self.browser_warmup(uri):
                    self.cookie_store.apply_to_session(self.session)
                    return self.get(uri, params, _warmup_attempted=True)
                raise ZhihuRiskControlError(
                    "知乎触发访问风控（错误码 40362），登录态仍有效；请暂停一段时间或更换正常网络后再试"
                )
            raise ZhihuAuthError("知乎拒绝了已登录请求，请重新登录后再试")
        if response.status_code == 401:
            raise ZhihuAuthError("知乎拒绝了已登录请求，请重新登录后再试")
        if response.status_code == 429:
            raise ZhihuRateLimitError("请求过于频繁，请提高请求间隔")
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise ZhihuParseError("知乎返回了非 JSON 内容") from exc

    def _request(self, final_uri: str, headers: dict[str, str]):
        try:
            return self.session.get(self.BASE_URL + final_uri, headers=headers, timeout=30)
        except requests.RequestException as exc:
            raise ZhihuNetworkError(str(exc)) from exc

    @staticmethod
    def _referer_for(uri: str) -> str:
        if "/members/" in uri:
            token = uri.split("/members/", 1)[1].split("/", 1)[0]
            return f"https://www.zhihu.com/people/{token}"
        if "/questions/" in uri:
            question_id = uri.split("/questions/", 1)[1].split("/", 1)[0]
            return f"https://www.zhihu.com/question/{question_id}"
        return "https://www.zhihu.com/"

    def verify_login(self) -> dict[str, Any]:
        result = self.get("/api/v4/me", {"include": "email,is_active,is_bind_phone"})
        if not result.get("uid") or not result.get("name"):
            raise ZhihuAuthError("知乎登录态验证失败，请重新登录")
        return result
