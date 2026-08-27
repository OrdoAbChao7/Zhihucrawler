# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/zhihu/core.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


# -*- coding: utf-8 -*-
import asyncio
import os
# import random  # Removed as we now use fixed config.CRAWLER_MAX_SLEEP_SEC intervals
from asyncio import Task
from typing import Dict, List, Optional, Tuple, cast

from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    async_playwright,
)

import config
from constant import zhihu as constant
from base.base_crawler import AbstractCrawler
from model.m_zhihu import ZhihuContent, ZhihuCreator
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import zhihu as zhihu_store
from tools import utils
from tools.cdp_browser import CDPBrowserManager
from var import crawler_type_var, source_keyword_var

from .client import ZhiHuClient
from .exception import DataFetchError
from .help import ZhihuExtractor, judge_zhihu_url
from .login import ZhiHuLogin


class ZhihuCrawler(AbstractCrawler):
    context_page: Page
    zhihu_client: ZhiHuClient
    browser_context: BrowserContext
    cdp_manager: Optional[CDPBrowserManager]

    def __init__(self) -> None:
        self.index_url = "https://www.zhihu.com"
        # self.user_agent = utils.get_user_agent()
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self._extractor = ZhihuExtractor()
        self.cdp_manager = None
        self.ip_proxy_pool = None  # Proxy IP pool for automatic proxy refresh

    async def start(self) -> None:
        """
        Start the crawler
        Returns:

        """
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            self.ip_proxy_pool = await create_ip_pool(
                config.IP_PROXY_POOL_COUNT, enable_validate_ip=True
            )
            ip_proxy_info: IpInfoModel = await self.ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = utils.format_proxy_info(
                ip_proxy_info
            )

        async with async_playwright() as playwright:
            # Choose launch mode based on configuration
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[ZhihuCrawler] Launching browser in CDP mode")
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy_format,
                    self.user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:
                utils.logger.info("[ZhihuCrawler] Launching browser in standard mode")
                # Launch a browser context.
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium, None, self.user_agent, headless=config.HEADLESS
                )
                # stealth.min.js is a js script to prevent the website from detecting the crawler.
                await self.browser_context.add_init_script(path="libs/stealth.min.js")

            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url, wait_until="domcontentloaded")

            # Create a client to interact with the zhihu website.
            self.zhihu_client = await self.create_zhihu_client(httpx_proxy_format)
            if not await self.zhihu_client.pong():
                login_obj = ZhiHuLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone="",  # input your phone number
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES,
                )
                await login_obj.begin()
                await self.zhihu_client.update_cookies(
                    browser_context=self.browser_context
                )

            # Zhihu's search API requires opening the search page first to access cookies, homepage alone won't work
            utils.logger.info(
                "[ZhihuCrawler.start] Zhihu navigating to search page to get search page cookies, this process takes about 5 seconds"
            )
            await self.context_page.goto(
                f"{self.index_url}/search?q=python&search_source=Guess&utm_content=search_hot&type=content"
            )
            await asyncio.sleep(5)
            await self.zhihu_client.update_cookies(browser_context=self.browser_context)

            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                # Search for notes and retrieve their comment information.
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                # Get the information and comments of the specified post
                await self.get_specified_notes()
            elif config.CRAWLER_TYPE == "creator":
                # Get creator's information and their notes and comments
                await self.get_creators_and_notes()
            elif config.CRAWLER_TYPE == "question":
                # Get answers under a specific question
                await self.get_question_answers()
            else:
                pass

            utils.logger.info("[ZhihuCrawler.start] Zhihu Crawler finished ...")

    async def search(self) -> None:
        """Search for notes and retrieve their comment information."""
        utils.logger.info("[ZhihuCrawler.search] Begin search zhihu keywords")
        zhihu_limit_count = 20  # zhihu limit page fixed value
        if config.CRAWLER_MAX_NOTES_COUNT < zhihu_limit_count:
            config.CRAWLER_MAX_NOTES_COUNT = zhihu_limit_count
        start_page = config.START_PAGE
        for keyword in config.KEYWORDS.split(","):
            source_keyword_var.set(keyword)
            utils.logger.info(
                f"[ZhihuCrawler.search] Current search keyword: {keyword}"
            )
            page = 1
            while (
                page - start_page + 1
            ) * zhihu_limit_count <= config.CRAWLER_MAX_NOTES_COUNT:
                if page < start_page:
                    utils.logger.info(f"[ZhihuCrawler.search] Skip page {page}")
                    page += 1
                    continue

                try:
                    utils.logger.info(
                        f"[ZhihuCrawler.search] search zhihu keyword: {keyword}, page: {page}"
                    )
                    content_list: List[ZhihuContent] = (
                        await self.zhihu_client.get_note_by_keyword(
                            keyword=keyword,
                            page=page,
                        )
                    )
                    utils.logger.info(
                        f"[ZhihuCrawler.search] Search contents :{content_list}"
                    )
                    if not content_list:
                        utils.logger.info("No more content!")
                        break

                    # Sleep after page navigation
                    await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                    utils.logger.info(f"[ZhihuCrawler.search] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after page {page-1}")

                    page += 1
                    for content in content_list:
                        await zhihu_store.update_zhihu_content(content)

                    await self.batch_get_content_comments(content_list)
                except DataFetchError:
                    utils.logger.error("[ZhihuCrawler.search] Search content error")
                    return

    async def batch_get_content_comments(self, content_list: List[ZhihuContent]):
        """
        Batch get content comments
        Args:
            content_list:

        Returns:

        """
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(
                f"[ZhihuCrawler.batch_get_content_comments] Crawling comment mode is not enabled"
            )
            return

        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for content_item in content_list:
            task = asyncio.create_task(
                self.get_comments(content_item, semaphore), name=content_item.content_id
            )
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_comments(
        self, content_item: ZhihuContent, semaphore: asyncio.Semaphore
    ):
        """
        Get note comments with keyword filtering and quantity limitation
        Args:
            content_item:
            semaphore:

        Returns:

        """
        async with semaphore:
            utils.logger.info(
                f"[ZhihuCrawler.get_comments] Begin get note id comments {content_item.content_id}"
            )

            # Sleep before fetching comments
            await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
            utils.logger.info(f"[ZhihuCrawler.get_comments] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds before fetching comments for content {content_item.content_id}")

            await self.zhihu_client.get_note_all_comments(
                content=content_item,
                crawl_interval=config.CRAWLER_MAX_SLEEP_SEC,
                callback=zhihu_store.batch_update_zhihu_note_comments,
            )

    async def get_creators_and_notes(self) -> None:
        """
        Get creator's information and their notes and comments
        Returns:

        """
        utils.logger.info(
            "[ZhihuCrawler.get_creators_and_notes] Begin get zhihu creators"
        )
        for user_link in config.ZHIHU_CREATOR_URL_LIST:
            utils.logger.info(
                f"[ZhihuCrawler.get_creators_and_notes] Begin get creator {user_link}"
            )
            user_url_token = user_link.split("/")[-1]
            # get creator detail info from web html content
            # 尝试获取用户信息
            createor_info: Optional[ZhihuCreator] = await self.zhihu_client.get_creator_info(
                url_token=user_url_token
            )
            
            # 即使获取不到用户信息，也尝试获取回答
            if not createor_info:
                utils.logger.warning(
                    f"[ZhihuCrawler.get_creators_and_notes] Creator {user_url_token} info not found, but will try to get answers anyway"
                )
                # 创建一个基本的 creator 对象，只包含 url_token
                createor_info = ZhihuCreator()
                createor_info.url_token = user_url_token
            else:
                utils.logger.info(
                    f"[ZhihuCrawler.get_creators_and_notes] Creator info: {createor_info}"
                )
                await zhihu_store.save_creator(creator=createor_info)

            # Get all anwser information of the creator
            answer_list = await self.zhihu_client.get_all_anwser_by_creator(
                creator=createor_info,
                crawl_interval=config.CRAWLER_MAX_SLEEP_SEC,
                callback=zhihu_store.batch_update_zhihu_contents,
            )
            utils.logger.info(f"[ZhihuCrawler.get_creators_and_notes] Got {len(answer_list)} answers")

            # Get all articles of the creator's contents
            article_list = await self.zhihu_client.get_all_articles_by_creator(
                creator=createor_info,
                crawl_interval=config.CRAWLER_MAX_SLEEP_SEC,
                callback=zhihu_store.batch_update_zhihu_contents
            )
            utils.logger.info(f"[ZhihuCrawler.get_creators_and_notes] Got {len(article_list)} articles")

            # 合并所有内容
            all_content_list = answer_list + article_list

            # Get all comments of the creator's contents
            await self.batch_get_content_comments(all_content_list)

    async def get_note_detail(
        self, full_note_url: str, semaphore: asyncio.Semaphore
    ) -> Optional[ZhihuContent]:
        """
        Get note detail
        Args:
            full_note_url: str
            semaphore:

        Returns:

        """
        async with semaphore:
            utils.logger.info(
                f"[ZhihuCrawler.get_specified_notes] Begin get specified note {full_note_url}"
            )
            # Judge note type
            note_type: str = judge_zhihu_url(full_note_url)
            if note_type == constant.ANSWER_NAME:
                question_id = full_note_url.split("/")[-3]
                answer_id = full_note_url.split("/")[-1]
                utils.logger.info(
                    f"[ZhihuCrawler.get_specified_notes] Get answer info, question_id: {question_id}, answer_id: {answer_id}"
                )
                result = await self.zhihu_client.get_answer_info(question_id, answer_id)

                # Sleep after fetching answer details
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[ZhihuCrawler.get_note_detail] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after fetching answer details {answer_id}")

                return result

            elif note_type == constant.ARTICLE_NAME:
                article_id = full_note_url.split("/")[-1]
                utils.logger.info(
                    f"[ZhihuCrawler.get_specified_notes] Get article info, article_id: {article_id}"
                )
                result = await self.zhihu_client.get_article_info(article_id)

                # Sleep after fetching article details
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[ZhihuCrawler.get_note_detail] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after fetching article details {article_id}")

                return result

            elif note_type == constant.VIDEO_NAME:
                video_id = full_note_url.split("/")[-1]
                utils.logger.info(
                    f"[ZhihuCrawler.get_specified_notes] Get video info, video_id: {video_id}"
                )
                result = await self.zhihu_client.get_video_info(video_id)

                # Sleep after fetching video details
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[ZhihuCrawler.get_note_detail] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after fetching video details {video_id}")

                return result

    async def get_specified_notes(self):
        """
        Get the information and comments of the specified post
        Returns:

        """
        get_note_detail_task_list = []
        for full_note_url in config.ZHIHU_SPECIFIED_ID_LIST:
            # remove query params
            full_note_url = full_note_url.split("?")[0]
            crawler_task = self.get_note_detail(
                full_note_url=full_note_url,
                semaphore=asyncio.Semaphore(config.MAX_CONCURRENCY_NUM),
            )
            get_note_detail_task_list.append(crawler_task)

        need_get_comment_notes: List[ZhihuContent] = []
        note_details = await asyncio.gather(*get_note_detail_task_list)
        for index, note_detail in enumerate(note_details):
            if not note_detail:
                utils.logger.info(
                    f"[ZhihuCrawler.get_specified_notes] Note {config.ZHIHU_SPECIFIED_ID_LIST[index]} not found"
                )
                continue

            note_detail = cast(ZhihuContent, note_detail)  # only for type check
            need_get_comment_notes.append(note_detail)
            await zhihu_store.update_zhihu_content(note_detail)

        await self.batch_get_content_comments(need_get_comment_notes)

    async def create_zhihu_client(self, httpx_proxy: Optional[str]) -> ZhiHuClient:
        """Create zhihu client"""
        utils.logger.info(
            "[ZhihuCrawler.create_zhihu_client] Begin create zhihu API client ..."
        )
        cookie_str, cookie_dict = utils.convert_cookies(
            await self.browser_context.cookies()
        )
        zhihu_client_obj = ZhiHuClient(
            proxy=httpx_proxy,
            headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
                "cookie": cookie_str,
                "priority": "u=1, i",
                "referer": "https://www.zhihu.com/",
                "user-agent": self.user_agent,
                "x-api-version": "3.0.91",
                "x-app-za": "OS=Web",
                "x-requested-with": "fetch",
                "x-zse-93": "101_3_3.0",
                "sec-ch-ua": "\"Google Chrome\";v=\"146\", \"Not?A_Brand\";v=\"8\", \"Chromium\";v=\"146\"",
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "\"Windows\"",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "same-origin",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1"
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
            proxy_ip_pool=self.ip_proxy_pool,  # Pass proxy pool for automatic refresh
        )
        return zhihu_client_obj

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser and create browser context"""
        utils.logger.info(
            "[ZhihuCrawler.launch_browser] Begin create browser context ..."
        )
        if config.SAVE_LOGIN_STATE:
            # feat issue #14
            # we will save login state to avoid login every time
            user_data_dir = os.path.join(
                os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM
            )  # type: ignore
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
                channel="chrome",  # Use system Chrome stable version
            )
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy, channel="chrome")  # type: ignore
            browser_context = await browser.new_context(
                viewport={"width": 1920, "height": 1080}, user_agent=user_agent
            )
            return browser_context

    async def launch_browser_with_cdp(
        self,
        playwright: Playwright,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """
        Launch browser using CDP mode
        """
        try:
            self.cdp_manager = CDPBrowserManager()
            browser_context = await self.cdp_manager.launch_and_connect(
                playwright=playwright,
                playwright_proxy=playwright_proxy,
                user_agent=user_agent,
                headless=headless,
            )

            # Display browser information
            browser_info = await self.cdp_manager.get_browser_info()
            utils.logger.info(f"[ZhihuCrawler] CDP browser info: {browser_info}")

            return browser_context

        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler] CDP mode launch failed, falling back to standard mode: {e}")
            # Fall back to standard mode
            chromium = playwright.chromium
            return await self.launch_browser(
                chromium, playwright_proxy, user_agent, headless
            )

    async def get_question_answers(self) -> None:
        """
        Get answers under a specific question using the Zhihu API
        Returns:

        """
        utils.logger.info(
            "[ZhihuCrawler.get_question_answers] Begin get question answers via API"
        )
        for question_link in config.ZHIHU_QUESTION_URL_LIST:
            utils.logger.info(
                f"[ZhihuCrawler.get_question_answers] Begin get answers for question: {question_link}"
            )
            
            # Extract question_id from URL
            question_id = question_link.rstrip('/').split('/')[-1]
            
            if not question_id or not question_id.isdigit():
                utils.logger.error(
                    f"[ZhihuCrawler.get_question_answers] Invalid question URL: {question_link}"
                )
                continue
            
            utils.logger.info(
                f"[ZhihuCrawler.get_question_answers] Question ID: {question_id}"
            )
            
            # Get max answers count from config
            max_answers = getattr(config, 'ZHIHU_QUESTION_MAX_ANSWERS', 50)
            
            # Use the API-based approach to get answers
            try:
                answer_list = await self.zhihu_client.get_all_answers_by_question(
                    question_id=question_id,
                    max_answers=max_answers,
                    crawl_interval=config.CRAWLER_MAX_SLEEP_SEC,
                    callback=zhihu_store.batch_update_zhihu_contents,
                )
                
                utils.logger.info(
                    f"[ZhihuCrawler.get_question_answers] Got {len(answer_list)} answers for question {question_id}"
                )
                
                # If API approach returned empty, fall back to browser-based approach
                if not answer_list:
                    utils.logger.info(
                        "[ZhihuCrawler.get_question_answers] API returned empty, falling back to browser-based approach"
                    )
                    answer_list = await self._get_question_answers_via_browser(
                        question_id=question_id,
                        question_url=question_link,
                        max_answers=max_answers,
                    )
                    
                    if answer_list:
                        await zhihu_store.batch_update_zhihu_contents(answer_list)
                
                # Get all comments of the answers
                await self.batch_get_content_comments(answer_list)
                
            except Exception as e:
                utils.logger.error(
                    f"[ZhihuCrawler.get_question_answers] Error getting answers for question {question_id}: {e}"
                )
                # Fall back to browser-based approach
                try:
                    utils.logger.info(
                        "[ZhihuCrawler.get_question_answers] Falling back to browser-based approach"
                    )
                    answer_list = await self._get_question_answers_via_browser(
                        question_id=question_id,
                        question_url=question_link,
                        max_answers=max_answers,
                    )
                    
                    if answer_list:
                        await zhihu_store.batch_update_zhihu_contents(answer_list)
                        await self.batch_get_content_comments(answer_list)
                except Exception as e2:
                    utils.logger.error(
                        f"[ZhihuCrawler.get_question_answers] Browser-based approach also failed: {e2}"
                    )

    async def _get_question_answers_via_browser(
        self,
        question_id: str,
        question_url: str,
        max_answers: int = 50,
    ) -> List[ZhihuContent]:
        """
        Get answers under a question using browser-based approach
        This method navigates to the question page and extracts answers from the DOM
        
        Args:
            question_id: Question ID
            question_url: Question URL
            max_answers: Maximum number of answers to crawl
            
        Returns:
            List of ZhihuContent objects
        """
        answer_list: List[ZhihuContent] = []
        page = self.context_page  # Use the existing context page with login cookies
        
        try:
            utils.logger.info(
                f"[ZhihuCrawler._get_question_answers_via_browser] Navigating to {question_url}"
            )
            
            # Navigate to the question page using the existing page
            await page.goto(question_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)  # Wait for page to fully load
            
            # Check current URL
            current_url = page.url
            utils.logger.info(
                f"[ZhihuCrawler._get_question_answers_via_browser] Current URL after navigation: {current_url}"
            )
            
            # Get the page HTML content first
            page_content = await page.content()
            
            # Save a debug copy of the page content
            debug_file_path = f"data/zhihu/json/question_{question_id}_debug.html"
            os.makedirs(os.path.dirname(debug_file_path), exist_ok=True)
            with open(debug_file_path, "w", encoding="utf-8") as f:
                f.write(page_content)
            utils.logger.info(
                f"[ZhihuCrawler._get_question_answers_via_browser] Saved debug HTML to {debug_file_path}"
            )
            
            # Check if we got an error page
            if '"error"' in page_content and '"code":40362' in page_content:
                utils.logger.error(
                    "[ZhihuCrawler._get_question_answers_via_browser] Got anti-scraping error page, trying to scroll and wait"
                )
                # Try scrolling and waiting for the page to load properly
                await page.evaluate("window.scrollTo(0, 100)")
                await asyncio.sleep(3)
                page_content = await page.content()
            
            # Now try to extract answers
            utils.logger.info(
                "[ZhihuCrawler._get_question_answers_via_browser] Extracting answers from page"
            )
            
            # First, try to extract data from JavaScript initialData
            answers_data = []
            
            # Try to get data from the page
            try:
                js_data = await page.evaluate("""
                () => {
                    let data = null;
                    // Check for initialData script
                    const scriptEl = document.getElementById('js-initialData');
                    if (scriptEl) {
                        try {
                            data = JSON.parse(scriptEl.textContent);
                        } catch (e) {
                            console.error('Failed to parse script data:', e);
                        }
                    }
                    return data;
                }
                """)
                
                if js_data and isinstance(js_data, dict):
                    utils.logger.info(
                        "[ZhihuCrawler._get_question_answers_via_browser] Found initial data"
                    )
                    
                    initial_state = js_data.get("initialState", {})
                    entities = initial_state.get("entities", {})
                    
                    answers_dict = entities.get("answers", {})
                    users_dict = entities.get("users", {})
                    questions_dict = entities.get("questions", {})
                    
                    utils.logger.info(
                        f"[ZhihuCrawler._get_question_answers_via_browser] Found {len(answers_dict)} answers in initial data"
                    )
                    
                    # Get question info
                    question_info = questions_dict.get(question_id, {})
                    question_title = question_info.get("title", "")
                    
                    # Iterate through all answers and filter by question_id
                    for answer_id, answer_data in answers_dict.items():
                        if len(answers_data) >= max_answers:
                            break
                        
                        # Check if this answer belongs to our question
                        answer_question = answer_data.get("question", {})
                        answer_question_id = ""
                        if isinstance(answer_question, dict):
                            answer_question_id = str(answer_question.get("id", ""))
                            if not question_title:
                                question_title = answer_question.get("title", "")
                        
                        if answer_question_id != question_id:
                            continue
                        
                        # Get author info
                        author = answer_data.get("author", {})
                        author_name = ""
                        if isinstance(author, str):
                            author_info = users_dict.get(author, {})
                            author_name = author_info.get("name", "")
                        elif isinstance(author, dict):
                            author_name = author.get("name", "")
                        elif answer_data.get("author"):
                            author_name = str(answer_data.get("author", ""))
                        
                        answers_data.append({
                            "answer_id": str(answer_data.get("id", "")),
                            "question_id": question_id,
                            "question_title": question_title,
                            "content": answer_data.get("content", ""),
                            "excerpt": answer_data.get("excerpt", "")[:200] if answer_data.get("excerpt") else "",
                            "author_name": author_name,
                            "voteup_count": answer_data.get("voteup_count", 0),
                            "comment_count": answer_data.get("comment_count", 0),
                            "created_time": answer_data.get("created_time", 0),
                            "answer_url": f"https://www.zhihu.com/question/{question_id}/answer/{answer_data.get('id', '')}",
                        })
                    
                    utils.logger.info(
                        f"[ZhihuCrawler._get_question_answers_via_browser] Filtered {len(answers_data)} answers for question {question_id}"
                    )
            except Exception as e:
                utils.logger.error(
                    f"[ZhihuCrawler._get_question_answers_via_browser] Error extracting initial data: {e}"
                )
            
            # If no data from initialData, try scrolling and then HTML extraction
            if not answers_data:
                utils.logger.info(
                    "[ZhihuCrawler._get_question_answers_via_browser] No initial data found, trying scroll and HTML extraction"
                )
                
                # Scroll down to load more answers with progressive loading
                for scroll_round in range(10):
                    prev_height = await page.evaluate("document.body.scrollHeight")
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)
                    new_height = await page.evaluate("document.body.scrollHeight")
                    if new_height == prev_height:
                        # Try clicking "load more" button
                        try:
                            load_more_btn = await page.query_selector('button[class*="LoadMore"], button[class*="load-more"], a[class*="load-more"]')
                            if load_more_btn:
                                await load_more_btn.click()
                                await asyncio.sleep(2)
                            else:
                                break
                        except:
                            break
                
                # Get updated page content
                page_content = await page.content()
                
                # Save another debug copy
                debug_file_path2 = f"data/zhihu/json/question_{question_id}_debug2.html"
                with open(debug_file_path2, "w", encoding="utf-8") as f:
                    f.write(page_content)
                utils.logger.info(
                    f"[ZhihuCrawler._get_question_answers_via_browser] Saved debug HTML after scrolling to {debug_file_path2}"
                )
                
                # Try to extract data again after scrolling
                try:
                    js_data = await page.evaluate("""
                    () => {
                        let data = null;
                        const scriptEl = document.getElementById('js-initialData');
                        if (scriptEl) {
                            try {
                                data = JSON.parse(scriptEl.textContent);
                            } catch (e) {
                                console.error('Failed to parse script data:', e);
                            }
                        }
                        return data;
                    }
                    """)
                    
                    if js_data and isinstance(js_data, dict):
                        initial_state = js_data.get("initialState", {})
                        entities = initial_state.get("entities", {})
                        
                        answers_dict = entities.get("answers", {})
                        users_dict = entities.get("users", {})
                        questions_dict = entities.get("questions", {})
                        
                        question_info = questions_dict.get(question_id, {})
                        question_title = question_info.get("title", "")
                        
                        # Iterate through all answers and filter by question_id
                        for answer_id, answer_data in answers_dict.items():
                            if len(answers_data) >= max_answers:
                                break
                            
                            answer_question = answer_data.get("question", {})
                            answer_question_id = ""
                            if isinstance(answer_question, dict):
                                answer_question_id = str(answer_question.get("id", ""))
                                if not question_title:
                                    question_title = answer_question.get("title", "")
                            
                            if answer_question_id != question_id:
                                continue
                            
                            author = answer_data.get("author", {})
                            author_name = ""
                            if isinstance(author, str):
                                author_info = users_dict.get(author, {})
                                author_name = author_info.get("name", "")
                            elif isinstance(author, dict):
                                author_name = author.get("name", "")
                            elif answer_data.get("author"):
                                author_name = str(answer_data.get("author", ""))
                            
                            answers_data.append({
                                "answer_id": str(answer_data.get("id", "")),
                                "question_id": question_id,
                                "question_title": question_title,
                                "content": answer_data.get("content", ""),
                                "excerpt": answer_data.get("excerpt", "")[:200] if answer_data.get("excerpt") else "",
                                "author_name": author_name,
                                "voteup_count": answer_data.get("voteup_count", 0),
                                "comment_count": answer_data.get("comment_count", 0),
                                "created_time": answer_data.get("created_time", 0),
                                "answer_url": f"https://www.zhihu.com/question/{question_id}/answer/{answer_data.get('id', '')}",
                            })
                except Exception as e:
                    utils.logger.error(
                        f"[ZhihuCrawler._get_question_answers_via_browser] Error after scrolling: {e}"
                    )
            
            utils.logger.info(
                f"[ZhihuCrawler._get_question_answers_via_browser] Extracted {len(answers_data)} answers from page"
            )
            
            # Convert extracted data to ZhihuContent objects
            for answer_data in answers_data:
                try:
                    content = ZhihuContent()
                    content.content_id = answer_data.get("answer_id", "")
                    content.content_type = "answer"
                    content.title = answer_data.get("question_title", "")
                    content.desc = answer_data.get("excerpt", "")
                    content.content_text = answer_data.get("content", "")
                    content.content_url = answer_data.get("answer_url", "")
                    content.question_id = answer_data.get("question_id", "")
                    content.voteup_count = answer_data.get("voteup_count", 0)
                    content.comment_count = 0
                    content.user_nickname = answer_data.get("author_name", "")
                    content.user_id = answer_data.get("author_name", "")
                    ts = answer_data.get("created_time", 0)
                    if isinstance(ts, str) and ts.isdigit():
                        content.created_time = int(ts)
                    else:
                        content.created_time = ts if isinstance(ts, int) else 0
                    
                    answer_list.append(content)
                except Exception as e:
                    utils.logger.error(f"[ZhihuCrawler._get_question_answers_via_browser] Error converting answer: {e}")
            
            utils.logger.info(
                f"[ZhihuCrawler._get_question_answers_via_browser] Successfully converted {len(answer_list)} answers"
            )
            
        except Exception as e:
            utils.logger.error(
                f"[ZhihuCrawler._get_question_answers_via_browser] Error: {e}"
            )
        
        return answer_list

    async def close(self):
        """Close browser context"""
        # Special handling if using CDP mode
        if self.cdp_manager:
            await self.cdp_manager.cleanup()
            self.cdp_manager = None
        else:
            await self.browser_context.close()
        utils.logger.info("[ZhihuCrawler.close] Browser context closed ...")
