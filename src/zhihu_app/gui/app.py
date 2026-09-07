from __future__ import annotations

import asyncio
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
import customtkinter as ctk

from ..config.settings import AppSettings
from ..engine.collection_downloader import CollectionDownloader
from ..engine.mediacrawler_adapter import MediaCrawlerAdapter
from ..engine.models import TaskType
from ..engine.paths import build_task_output_paths
from ..engine.runner import TaskRunner
from .forms import build_task_from_form


TASK_TYPE_LABELS = {
    "search": "搜索内容",
    "question": "问题回答",
    "creator": "用户回答 / 文章",
    "collection": "收藏夹 / 用户文章",
}


def task_type_label(value: str) -> str:
    return TASK_TYPE_LABELS.get(value, value)


def build_output_hint(output_dir: str | Path) -> str:
    return f"文件将保存到：{Path(output_dir)}\\...\\markdown"


def run_login_in_background(session_factory, on_error, on_success=None, verifier_factory=None) -> None:
    """Run login and never lose an exception in an unobserved thread."""
    async def login() -> object:
        session = session_factory()
        await session.login()
        return session

    try:
        session = asyncio.run(login())
        if verifier_factory:
            verifier_factory().verify_login()
    except Exception as exc:
        on_error(exc)
    else:
        if on_success:
            on_success(session)


class ZhihuApp:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("知乎采集器")
        self.root.geometry("900x700")
        self.root.minsize(780, 580)

        self.colors = {
            "navy": "#173B67", "blue": "#1f538d", "ink": "#e0e0e0",
            "muted": "#888888", "surface": "#2b2b2b", "background": "#242424",
            "border": "#3a3a3a", "success": "#16845B", "danger": "#C43232",
        }

        self.vars = {name: tk.StringVar(value=value) for name, value in {
            "task_type": task_type_label("search"), "target": "", "max_items": str(settings.max_items),
            "interval": str(settings.interval_seconds), "proxy": settings.proxy,
        }.items()}
        self.include_comments = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="准备就绪")

        self._build()
        self.runner = TaskRunner(self._run_task)
        self.runner.on_log = lambda message: self.root.after(0, self._log, message)
        self.runner.on_done = lambda result: self.root.after(0, lambda: self._finished(result.status))
        self.runner.on_error = lambda error: self.root.after(0, lambda: self._error(error))
        self._login_session = None
        self.root.protocol("WM_DELETE_WINDOW", self._close)


        # Header
        header = ctk.CTkFrame(self.root, fg_color=self.colors["surface"], corner_radius=0, height=80)
        header.pack(fill="x", pady=(0, 10))
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="知乎采集器", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"), text_color=self.colors["ink"]).pack(anchor="w", padx=20, pady=(15, 0))
        ctk.CTkLabel(header, text="搜索、问题、用户内容与收藏夹，一站式保存为 Markdown", font=ctk.CTkFont(family="Segoe UI", size=12), text_color=self.colors["muted"]).pack(anchor="w", padx=20, pady=(2, 0))

        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Task Config Card
        card = ctk.CTkFrame(main_frame, fg_color=self.colors["surface"], corner_radius=10)
        card.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(card, text="任务配置", font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), text_color=self.colors["ink"]).grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(15, 10))

        fields = [("任务类型", "task_type"), ("关键词或 URL", "target"), ("最大数量", "max_items"), ("请求间隔（秒）", "interval"), ("代理地址", "proxy")]

        for row, (label, name) in enumerate(fields, start=1):
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(family="Segoe UI", size=12), text_color=self.colors["ink"]).grid(row=row, column=0, sticky="w", pady=6, padx=(20, 16))
            if name == "task_type":
                widget = ctk.CTkOptionMenu(card, variable=self.vars[name], values=[task_type_label(t.value) for t in TaskType], width=200, fg_color=self.colors["background"], button_color=self.colors["background"], button_hover_color=self.colors["border"])
                widget.grid(row=row, column=1, sticky="w", pady=6)
            else:
                widget = ctk.CTkEntry(card, textvariable=self.vars[name], width=450, fg_color=self.colors["background"], border_color=self.colors["border"])
                widget.grid(row=row, column=1, sticky="w", pady=6)

        ctk.CTkCheckBox(card, text="抓取评论（仅采集模式）", variable=self.include_comments, font=ctk.CTkFont(family="Segoe UI", size=12), fg_color=self.colors["blue"], hover_color=self.colors["blue"]).grid(row=6, column=1, sticky="w", pady=(6, 2))
        ctk.CTkLabel(card, text=build_output_hint(self.settings.output_dir), font=ctk.CTkFont(family="Segoe UI", size=11), text_color=self.colors["muted"]).grid(row=7, column=1, sticky="w", pady=(2, 15))

        card.columnconfigure(1, weight=1)

        # Actions
        actions = ctk.CTkFrame(main_frame, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 15))

        ctk.CTkButton(actions, text="▶ 开始任务", command=self._start, font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), width=120, height=36, fg_color=self.colors["blue"], hover_color="#2458C6").pack(side="left", padx=(0, 10))
        ctk.CTkButton(actions, text="■ 停止", command=self._cancel, font=ctk.CTkFont(family="Segoe UI", size=13), width=100, height=36, fg_color="transparent", border_width=1, border_color=self.colors["border"], hover_color=self.colors["border"], text_color=self.colors["ink"]).pack(side="left", padx=(0, 10))
        ctk.CTkButton(actions, text="⇥ 登录知乎", command=self._login, font=ctk.CTkFont(family="Segoe UI", size=13), width=100, height=36, fg_color="transparent", border_width=1, border_color=self.colors["border"], hover_color=self.colors["border"], text_color=self.colors["ink"]).pack(side="left", padx=(0, 10))
        ctk.CTkButton(actions, text="打开输出目录", command=self._open_output, font=ctk.CTkFont(family="Segoe UI", size=13), width=120, height=36, fg_color="transparent", border_width=1, border_color=self.colors["border"], hover_color=self.colors["border"], text_color=self.colors["ink"]).pack(side="right")

        # Status Bar
        status_bar = ctk.CTkFrame(main_frame, fg_color="transparent")
        status_bar.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(status_bar, textvariable=self.status_var, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=self.colors["blue"]).pack(side="left")
        ctk.CTkLabel(status_bar, text="安全间隔与登录态由程序自动管理", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=self.colors["muted"]).pack(side="right")

        # Log Card
        log_card = ctk.CTkFrame(main_frame, fg_color=self.colors["surface"], corner_radius=10)
        log_card.pack(fill="both", expand=True)

        ctk.CTkLabel(log_card, text="运行日志", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color=self.colors["ink"]).pack(anchor="w", padx=20, pady=(10, 5))

        self.log = ctk.CTkTextbox(log_card, fg_color=self.colors["background"], text_color=self.colors["ink"], font=ctk.CTkFont(family="Consolas", size=12), wrap="word", corner_radius=8)
        self.log.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.log.configure(state="disabled")

    def _open_output(self) -> None:
        Path(self.settings.output_dir).mkdir(parents=True, exist_ok=True)
        os.startfile(self.settings.output_dir)

    def _start(self) -> None:
        try:
            values = {key: var.get() for key, var in self.vars.items()}
            values["task_type"] = next((key for key, label in TASK_TYPE_LABELS.items() if label == values["task_type"]), values["task_type"])
            values["include_comments"] = "1" if self.include_comments.get() else "0"
            task = build_task_from_form(values)
            task.output_dir = build_task_output_paths(self.settings.output_dir, task).task_dir
            self.runner.submit(task)
            self._log(f"任务已开始，输出目录：{task.output_dir}")
            self.status_var.set("正在采集…")
        except (ValueError, RuntimeError) as exc:
            self._error(exc)

    def _run_task(self, task, emit, cancel):
        if task.task_type is TaskType.COLLECTION:
            return CollectionDownloader(self.settings).run(task, emit, cancel)
        return MediaCrawlerAdapter(self.settings).run(task, emit, cancel)

    def _login(self) -> None:
        self._log("正在启动知乎登录浏览器…")
        from ..auth.session import CookieStore, SessionManager
        from ..engine.http_client import ZhihuApiClient
        cookie_store = CookieStore(self.settings.profile_dir.parent / "cookies.json")
        threading.Thread(
            target=run_login_in_background,
            kwargs={
                "session_factory":
                lambda: SessionManager(self.settings.profile_dir),
                "on_error": lambda error: self.root.after(0, lambda: self._error(error)),
                "on_success": lambda session: self.root.after(0, lambda: self._login_succeeded(session)),
                "verifier_factory": lambda: ZhihuApiClient(cookie_store, proxy=self.settings.proxy),
            },
            daemon=True,
        ).start()

    def _login_succeeded(self, session) -> None:
        self._login_session = session
        self._log("知乎登录态验证成功，可以开始采集")

    def _cancel(self) -> None:
        self.runner.cancel(); self._log("已请求停止任务")

    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _finished(self, status: str) -> None:
        self.status_var.set(f"任务结束：{status}")
        self._log(f"任务结束：{status}")
    def _error(self, error: Exception) -> None:
        self.status_var.set("任务出错")
        messagebox.showerror("任务错误", str(error)); self._log(f"错误：{error}")
    def _close(self) -> None: self.runner.cancel(); self.root.destroy()
    def run(self) -> None: self.root.mainloop()


def create_app(settings: AppSettings | None = None) -> ZhihuApp:
    return ZhihuApp(settings or AppSettings.defaults())
