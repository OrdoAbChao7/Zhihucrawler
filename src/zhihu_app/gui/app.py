from __future__ import annotations

import asyncio
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..config.settings import AppSettings
from ..engine.collection_downloader import CollectionDownloader
from ..engine.mediacrawler_adapter import MediaCrawlerAdapter
from ..engine.models import TaskType
from ..engine.paths import build_task_output_paths
from ..engine.runner import TaskRunner
from .forms import build_task_from_form


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
        self.root = tk.Tk()
        self.root.title("知乎采集器")
        self.root.geometry("760x560")
        self.vars = {name: tk.StringVar(value=value) for name, value in {
            "task_type": "search", "target": "", "max_items": str(settings.max_items),
            "interval": str(settings.interval_seconds), "proxy": settings.proxy,
        }.items()}
        self.include_comments = tk.BooleanVar(value=False)
        self._build()
        self.runner = TaskRunner(self._run_task)
        self.runner.on_log = lambda message: self.root.after(0, self._log, message)
        self.runner.on_done = lambda result: self.root.after(0, lambda: self._finished(result.status))
        self.runner.on_error = lambda error: self.root.after(0, lambda: self._error(error))
        self._login_session = None
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=14)
        frame.pack(fill="both", expand=True)
        fields = [("任务类型", "task_type"), ("关键词或 URL", "target"), ("最大数量", "max_items"), ("请求间隔(秒)", "interval"), ("代理", "proxy")]
        for row, (label, name) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=5)
            if name == "task_type":
                ttk.Combobox(frame, textvariable=self.vars[name], values=[t.value for t in TaskType], state="readonly", width=20).grid(row=row, column=1, sticky="ew")
            else:
                ttk.Entry(frame, textvariable=self.vars[name], width=65).grid(row=row, column=1, sticky="ew")
        ttk.Checkbutton(frame, text="抓取评论（采集模式）", variable=self.include_comments).grid(row=5, column=1, sticky="w")
        buttons = ttk.Frame(frame); buttons.grid(row=6, column=1, sticky="w", pady=10)
        ttk.Button(buttons, text="开始任务", command=self._start).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="停止", command=self._cancel).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="登录知乎", command=self._login).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="打开输出目录", command=lambda: Path(self.settings.output_dir).mkdir(parents=True, exist_ok=True) or __import__("os").startfile(self.settings.output_dir)).pack(side="left")
        self.log = tk.Text(frame, height=20, state="disabled")
        self.log.grid(row=7, column=0, columnspan=2, sticky="nsew")
        frame.columnconfigure(1, weight=1); frame.rowconfigure(7, weight=1)

    def _start(self) -> None:
        try:
            values = {key: var.get() for key, var in self.vars.items()}
            values["include_comments"] = "1" if self.include_comments.get() else "0"
            task = build_task_from_form(values)
            task.output_dir = build_task_output_paths(self.settings.output_dir, task).task_dir
            self.runner.submit(task)
            self._log(f"任务已开始，输出目录：{task.output_dir}")
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
        self.log.configure(state="normal"); self.log.insert("end", message + "\n"); self.log.see("end"); self.log.configure(state="disabled")

    def _finished(self, status: str) -> None: self._log(f"任务结束：{status}")
    def _error(self, error: Exception) -> None: messagebox.showerror("任务错误", str(error)); self._log(f"错误：{error}")
    def _close(self) -> None: self.runner.cancel(); self.root.destroy()
    def run(self) -> None: self.root.mainloop()


def create_app(settings: AppSettings | None = None) -> ZhihuApp:
    return ZhihuApp(settings or AppSettings.defaults())
