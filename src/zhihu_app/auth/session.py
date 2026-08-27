from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def has_zhihu_auth(cookies: list[dict[str, Any]]) -> bool:
    names = {cookie.get("name") for cookie in cookies}
    return {"z_c0", "d_c0"}.issubset(names)


@dataclass(frozen=True)
class CookieStore:
    path: Path

    def save(self, cookies: list[dict[str, Any]]) -> None:
        if not has_zhihu_auth(cookies):
            raise ValueError("登录 Cookie 缺少 z_c0 或 d_c0")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def as_requests_dict(self) -> dict[str, str]:
        return {
            str(cookie["name"]): str(cookie["value"])
            for cookie in self.load()
            if cookie.get("name") and cookie.get("value") is not None
        }

    def apply_to_session(self, session: Any) -> None:
        for cookie in self.load():
            name = cookie.get("name")
            value = cookie.get("value")
            if not name or value is None:
                continue
            domain = str(cookie.get("domain") or ".zhihu.com")
            if not (domain == "zhihu.com" or domain.endswith(".zhihu.com")):
                continue
            session.cookies.set(
                str(name), str(value), domain=domain,
                path=str(cookie.get("path") or "/"),
                secure=bool(cookie.get("secure", True)),
            )


class SessionManager:
    def __init__(self, profile_dir: Path, cookie_store: CookieStore | None = None) -> None:
        self.profile_dir = Path(profile_dir)
        self.cookie_store = cookie_store or CookieStore(self.profile_dir.parent / "cookies.json")
        self._browser = None

    async def login(self, timeout_seconds: float = 300) -> None:
        from playwright.async_api import async_playwright
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch_persistent_context(
                str(self.profile_dir), headless=False, args=["--no-sandbox"]
            )
            page = self._browser.pages[0] if self._browser.pages else await self._browser.new_page()
            await page.goto("https://www.zhihu.com", wait_until="domcontentloaded")
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout_seconds
            while loop.time() < deadline:
                cookies = await self._browser.cookies(["https://www.zhihu.com", "https://zhuanlan.zhihu.com"])
                if has_zhihu_auth(cookies):
                    self.cookie_store.save(cookies)
                    return
                await asyncio.sleep(1)
            raise TimeoutError("等待知乎登录超时，请重新点击登录")
        finally:
            await self.close()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if getattr(self, "_playwright", None):
            await self._playwright.stop()


def warmup_zhihu_browser(
    profile_dir: Path,
    cookie_store: CookieStore,
    target_uri: str = "/",
    proxy: str = "",
) -> bool:
    """Warm the saved browser session before retrying a risk-controlled API call.

    This follows the normal browser flow used by the reference crawlers: visit
    Zhihu first, then the relevant content owner page, and export the browser's
    current cookies. It is not a bypass; a platform-level 40362 remains an
    explicit error after the single retry.
    """
    from playwright.sync_api import sync_playwright

    if "/members/" in target_uri:
        token = target_uri.split("/members/", 1)[1].split("/", 1)[0]
        page_url = f"https://www.zhihu.com/people/{token}"
    elif "/questions/" in target_uri:
        question_id = target_uri.split("/questions/", 1)[1].split("/", 1)[0]
        page_url = f"https://www.zhihu.com/question/{question_id}"
    else:
        page_url = "https://www.zhihu.com/"

    launch_args = ["--no-sandbox"]
    try:
        with sync_playwright() as playwright:
            context_kwargs = {"headless": True, "args": launch_args}
            if proxy:
                context_kwargs["proxy"] = {"server": proxy}
            context = playwright.chromium.launch_persistent_context(str(profile_dir), **context_kwargs)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://www.zhihu.com/", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1200)
                if page_url != "https://www.zhihu.com/":
                    page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1200)
                cookies = context.cookies(["https://www.zhihu.com", "https://zhuanlan.zhihu.com"])
                if not has_zhihu_auth(cookies):
                    return False
                cookie_store.save(cookies)
                return True
            finally:
                context.close()
    except Exception:
        return False
