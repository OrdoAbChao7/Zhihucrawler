from __future__ import annotations

import re
import json
from urllib.parse import urlsplit
from itertools import zip_longest
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

import requests
from urllib.parse import urlsplit

from ..auth.session import CookieStore, warmup_zhihu_browser
from ..config.settings import AppSettings
from .errors import ZhihuAuthError, ZhihuNetworkError, ZhihuRateLimitError, ZhihuRiskControlError
from .models import TaskResult, TaskType, ZhihuTask
from .http_client import ZhihuApiClient
from .content import hydrate_content_items


def normalise_content_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for item in items:
        item = item.get("object") if isinstance(item.get("object"), dict) else item
        if not item.get("id") and not item.get("url"):
            continue
        content = item.get("content") or item.get("excerpt") or ""
        author = item.get("author") or {}
        question = item.get("question") or {}
        records.append({
            "id": str(item.get("id", "")),
            "kind": item.get("type", "unknown"),
            "title": question.get("title") or item.get("title") or "知乎内容",
            "author": author.get("name", ""),
            "url": item.get("url", ""),
            "content": content,
            "updated_time": item.get("updated_time", 0),
        })
    return records


def creator_api_urls(target: str) -> list[str]:
    token = urlsplit(target).path.rstrip("/").split("/")[-1]
    if not token or token == "people":
        raise ValueError("无法解析创作者 token")
    return [
        f"https://www.zhihu.com/api/v4/members/{token}/answers",
        f"https://www.zhihu.com/api/v4/members/{token}/articles",
        f"https://www.zhihu.com/api/v4/members/{token}/zvideos",
    ]


def _id_from_url(url: str, marker: str) -> str:
    match = re.search(rf"/{marker}/(\d+)", url)
    if not match:
        raise ValueError(f"无法从 URL 解析 {marker} ID")
    return match.group(1)


class MediaCrawlerAdapter:
    """HTTP adapter retaining the four useful Zhihu crawler modes."""

    def __init__(self, settings: AppSettings, session: requests.Session | None = None, api_client=None) -> None:
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
        if settings.proxy and hasattr(self.session, "proxies"):
            self.session.proxies.update({"http": settings.proxy, "https": settings.proxy})

    def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
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

    def _fetch_pages(
        self, url: str, params: dict[str, Any], max_items: int, cancel: Event,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = int(params.get("offset", 0))
        while len(items) < max_items and not cancel.is_set():
            page_params = dict(params)
            page_params["offset"] = offset
            page_params["limit"] = min(max_items - len(items), 100)
            payload = self._get(url, page_params)
            page = payload.get("data", [])
            items.extend(page)
            if not page or payload.get("paging", {}).get("is_end", True):
                break
            offset += len(page)
        return items[:max_items]

    def fetch_items(self, task: ZhihuTask, cancel: Event, emit: Callable[[str], None]) -> list[dict[str, Any]]:
        if task.task_type is TaskType.SEARCH:
            url, params = "https://www.zhihu.com/api/v4/search_v3", {
                "t": "general", "q": task.target, "limit": min(max(task.max_items * 2 + 1, 10), 100),
            }
        elif task.task_type is TaskType.QUESTION:
            url = f"https://www.zhihu.com/api/v4/questions/{_id_from_url(task.target, 'question')}/answers"
            items = self._fetch_pages(
                url,
                {
                    "offset": 0,
                    "include": (
                        "data[*].content,excerpt,created_time,updated_time,voteup_count,comment_count,"
                        "is_normal,admin_closed_comment,can_comment,comment_permission,review_info,"
                        "reaction_instruction,is_labeled,label_info;data[*].author;"
                        "data[*].question.has_publishing_draft,relationship"
                    ),
                    "sort_by": "default",
                },
                task.max_items, cancel,
            )
            emit(f"获取到 {len(items)} 条知乎内容")
            return normalise_content_items(items)
        elif task.task_type is TaskType.CREATOR:
            urls = creator_api_urls(task.target)
            groups = []
            for url in urls:
                groups.append(self._fetch_pages(url, {"offset": 0, "order_by": "created"}, task.max_items, cancel))
            all_items = [item for row in zip_longest(*groups) for item in row if item is not None][:task.max_items]
            if self.api_client is not None:
                risk_controlled = []
                def fetch_detail(uri, params):
                    try:
                        return self.api_client.get(uri, params)
                    except ZhihuRiskControlError:
                        risk_controlled.append(uri)
                        return {}
                all_items = hydrate_content_items(all_items, fetch_detail)
                for uri in risk_controlled:
                    emit(f"详情被知乎风控拦截，已保留列表摘要：{uri}")
            emit(f"获取到 {len(all_items)} 条创作者内容")
            return normalise_content_items(all_items)
        else:
            raise ValueError("该任务类型请使用收藏夹下载引擎")
        payload = self._get(url, params)
        items = payload.get("data", [])
        emit(f"获取到 {len(items)} 条知乎内容")
        return normalise_content_items(items)[: task.max_items]

    def run(self, task: ZhihuTask, emit: Callable[[str], None], cancel: Event) -> TaskResult:
        if task.proxy and hasattr(self.session, "proxies"):
            self.session.proxies.update({"http": task.proxy, "https": task.proxy})
        if self.api_client is not None and hasattr(self.api_client, "min_interval"):
            self.api_client.min_interval = task.interval_seconds
        items = self.fetch_items(task, cancel, emit)
        if cancel.is_set():
            return TaskResult("cancelled", 0)
        if task.include_comments:
            for item in items:
                if cancel.is_set():
                    return TaskResult("cancelled", 0)
                if item.get("kind") == "answer" and item.get("id"):
                    comments = self._get(
                        f"https://www.zhihu.com/api/v4/answers/{item['id']}/comments",
                        {"limit": 20, "offset": 0},
                    ).get("data", [])
                    item["comments"] = comments
            emit("评论采集完成")
        output = Path(task.output_dir or self.settings.output_dir)
        (output / "raw").mkdir(parents=True, exist_ok=True)
        (output / "markdown").mkdir(parents=True, exist_ok=True)
        (output / "raw" / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        for index, item in enumerate(items, 1):
            title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", item.get("title", "知乎内容"))[:100] or f"item-{index}"
            (output / "markdown" / f"{index:04d}-{title}.md").write_text(
                f"---\ntitle: {item.get('title', '')}\nurl: {item.get('url', '')}\n---\n\n{item.get('content', '')}\n",
                encoding="utf-8",
            )
        return TaskResult("completed", len(items), task.output_dir)
