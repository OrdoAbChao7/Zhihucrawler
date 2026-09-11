from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any

import requests
from urllib.parse import urlsplit

try:
    import html2text
except ImportError:  # Keep metadata/path tests runnable before optional install.
    html2text = None

from ..config.settings import AppSettings
from ..auth.session import CookieStore, warmup_zhihu_browser
from .errors import ZhihuAuthError, ZhihuNetworkError, ZhihuRateLimitError, ZhihuRiskControlError
from .models import TaskResult, ZhihuTask
from .http_client import ZhihuApiClient
from .content import hydrate_content_items


def item_to_markdown(item: dict[str, Any]) -> str:
    raw_content = item.get("content", "")
    if isinstance(raw_content, dict):
        raw_content = raw_content.get("html") or raw_content.get("content") or raw_content.get("text") or ""
    if not isinstance(raw_content, str):
        raw_content = str(raw_content)
    if html2text:
        content = html2text.html2text(raw_content)
    else:
        content = re.sub(
            r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', r'![](\1)', raw_content,
            flags=re.IGNORECASE,
        )
        content = re.sub(r"<[^>]+>", "", content)
    title = _item_title(item)
    url = item.get("url", "")
    updated = item.get("updated_time", 0)
    return f"---\ntitle: {title}\nurl: {url}\nupdated_time: {updated}\n---\n\n{content.strip()}\n"


def _content_preview(item: dict[str, Any]) -> str:
    raw_content = item.get("content", "")
    if isinstance(raw_content, dict):
        raw_content = raw_content.get("html") or raw_content.get("content") or raw_content.get("text") or ""
    if not isinstance(raw_content, str):
        raw_content = str(raw_content)
    preview = re.sub(r"<[^>]+>", " ", raw_content)
    preview = re.sub(r"\s+", " ", preview).strip()
    return preview


def _item_title(item: dict[str, Any]) -> str:
    question = item.get("question") if isinstance(item.get("question"), dict) else {}
    title = question.get("title") or item.get("title")
    if title:
        return str(title)
    preview = _content_preview(item)
    return preview[:80] + ("…" if len(preview) > 80 else "") if preview else "知乎内容"


def should_skip_existing(path: Path, url: str, updated_time: int) -> bool:
    if not path.is_file():
        return False
    # ⚡ Bolt: Read only the first 4KB of the file since the metadata
    # (url and updated_time) is located in the front matter at the top.
    # This prevents loading entire markdown files into memory and speeds up I/O significantly.
    with path.open("r", encoding="utf-8", errors="replace") as f:
        text = f.read(4096)
    return f"url: {url}" in text and f"updated_time: {updated_time}" in text


def _safe_filename(title: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip()[:120] or "知乎内容"


def collection_api_for_target(target: str) -> str:
    parts = target.rstrip("/").split("/")
    if "/collection/" in target:
        return f"https://www.zhihu.com/api/v4/collections/{parts[-1]}/items"
    if "/people/" in target and parts[-1] == "posts":
        return f"https://www.zhihu.com/api/v4/members/{parts[-2]}/articles"
    raise ValueError("仅支持知乎收藏夹或用户文章 URL")


class CollectionDownloader:
    def __init__(
        self, settings: AppSettings, session: requests.Session | None = None, api_client=None,
        image_session=None, sleep=time.sleep,
    ) -> None:
        self.settings = settings
        self.session = session
        self.api_client = api_client
        if self.api_client is None and self.session is None:
            profile_dir = settings.profile_dir or settings.output_dir.parent / "data" / "browser_profile"
            self.api_client = ZhihuApiClient(
                CookieStore(profile_dir.parent / "cookies.json"), proxy=settings.proxy,
                min_interval=settings.interval_seconds,
                browser_warmup=lambda uri: warmup_zhihu_browser(
                    profile_dir, CookieStore(profile_dir.parent / "cookies.json"), uri, settings.proxy
                ),
            )
            self.session = self.api_client.session
        if self.session is None:
            self.session = requests.Session()
        self.image_session = image_session or requests.Session()
        self._sleep = sleep
        self.image_interval = settings.interval_seconds
        if settings.proxy and hasattr(self.session, "proxies"):
            self.session.proxies.update({"http": settings.proxy, "https": settings.proxy})
        if settings.proxy and hasattr(self.image_session, "proxies"):
            self.image_session.proxies.update({"http": settings.proxy, "https": settings.proxy})

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.api_client is not None:
            return self.api_client.get(urlsplit(url).path, params)
        try:
            response = self.session.get(url, params=params, timeout=30)
        except requests.RequestException as exc:
            raise ZhihuNetworkError(str(exc)) from exc
        if response.status_code in (401, 403):
            raise ZhihuAuthError("知乎登录态已失效，请重新登录")
        if response.status_code == 429:
            raise ZhihuRateLimitError("请求过于频繁，请提高请求间隔")
        response.raise_for_status()
        return response.json()

    def download_items(self, items: list[dict[str, Any]], output_dir: Path, emit) -> int:
        markdown_dir = output_dir / "markdown"
        image_dir = output_dir / "images"
        markdown_dir.mkdir(parents=True, exist_ok=True)
        image_dir.mkdir(parents=True, exist_ok=True)
        processed = 0
        attempted_image = False
        for item in items:
            url = item.get("url", "")
            title = _safe_filename(_item_title(item))
            identity = url or str(item.get("id", "")) or _content_preview(item) or title
            suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
            path = markdown_dir / f"{title}-{suffix}.md"
            if should_skip_existing(path, url, item.get("updated_time", 0)):
                emit(f"跳过未变化内容：{title}")
                continue
            markdown = item_to_markdown(item)
            for image_url in re.findall(r"https?://[^\s)\"']+", markdown):
                if Path(urlsplit(image_url).path).suffix.lower() not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    continue
                try:
                    if attempted_image and self.image_interval > 0:
                        self._sleep(self.image_interval)
                    attempted_image = True
                    response = self.image_session.get(image_url, timeout=30)
                    response.raise_for_status()
                    suffix = Path(image_url.split("?", 1)[0]).suffix or ".bin"
                    image_name = hashlib.sha256(image_url.encode()).hexdigest()[:16] + suffix
                    (image_dir / image_name).write_bytes(response.content)
                    markdown = markdown.replace(image_url, f"../images/{image_name}")
                except requests.RequestException:
                    emit(f"图片下载失败：{image_url}")
            path.write_text(markdown, encoding="utf-8")
            processed += 1
            emit(f"已保存：{path.name}")
        return processed

    def run(self, task: ZhihuTask, emit, cancel) -> TaskResult:
        if task.proxy and hasattr(self.session, "proxies"):
            self.session.proxies.update({"http": task.proxy, "https": task.proxy})
        if task.proxy and hasattr(self.image_session, "proxies"):
            self.image_session.proxies.update({"http": task.proxy, "https": task.proxy})
        self.image_interval = task.interval_seconds
        if self.api_client is not None and hasattr(self.api_client, "min_interval"):
            self.api_client.min_interval = task.interval_seconds
        api_url = collection_api_for_target(task.target)
        items = []
        offset = 0
        while len(items) < task.max_items:
            payload = self._get(api_url, {"limit": min(task.max_items - len(items), 20), "offset": offset})
            page = payload.get("data", [])
            items.extend(page)
            if cancel.is_set():
                return TaskResult("cancelled", 0)
            if not page or payload.get("paging", {}).get("is_end", True):
                break
            offset += len(page)
        if self.api_client is not None:
            risk_controlled = []
            def fetch_detail(uri, params):
                try:
                    return self.api_client.get(uri, params)
                except ZhihuRiskControlError:
                    risk_controlled.append(uri)
                    return {}
            items = hydrate_content_items(items[: task.max_items], fetch_detail)
            for uri in risk_controlled:
                emit(f"详情被知乎风控拦截，已保留列表摘要：{uri}")
        count = self.download_items(items[: task.max_items], task.output_dir or self.settings.output_dir, emit)
        return TaskResult("completed", count, task.output_dir)
