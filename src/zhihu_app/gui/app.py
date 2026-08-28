from __future__ import annotations

import asyncio
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

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
        self.root = tk.Tk()
        self.root.title("知乎采集器")
        self.root.geometry("900x680")
        self.root.minsize(780, 580)
        self.colors = {
            "navy": "#173B67", "blue": "#2F6FED", "ink": "#1D2939",
            "muted": "#667085", "surface": "#FFFFFF", "background": "#F4F7FB",
            "border": "#D0D5DD", "success": "#16845B", "danger": "#C43232",
        }
        self.vars = {name: tk.StringVar(value=value) for name, value in {
            "task_type": task_type_label("search"), "target": "", "max_items": str(settings.max_items),
            "interval": str(settings.interval_seconds), "proxy": settings.proxy,
        }.items()}
        self.include_comments = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="准备就绪")
        self.status_color = tk.StringVar(value=self.colors["muted"])
        self._build()
        self.runner = TaskRunner(self._run_task)
        self.runner.on_log = lambda message: self.root.after(0, self._log, message)
        self.runner.on_done = lambda result: self.root.after(0, lambda: self._finished(result.status))
        self.runner.on_error = lambda error: self.root.after(0, lambda: self._error(error))
        self._login_session = None
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=self.colors["background"])
        style.configure("Card.TLabelframe", background=self.colors["surface"], bordercolor=self.colors["border"])
        style.configure("Card.TLabelframe.Label", background=self.colors["surface"], foreground=self.colors["navy"], font=("Segoe UI", 10, "bold"))
        style.configure("Body.TLabel", background=self.colors["surface"], foreground=self.colors["ink"], font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=self.colors["surface"], foreground=self.colors["muted"], font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=self.colors["navy"], foreground="white", font=("Segoe UI", 21, "bold"))
        style.configure("Subtitle.TLabel", background=self.colors["navy"], foreground="#D6E4FF", font=("Segoe UI", 10))
        style.configure("Primary.TButton", background=self.colors["blue"], foreground="white", padding=(16, 9), font=("Segoe UI", 10, "bold"))
        style.map("Primary.TButton", background=[("active", "#2458C6")])
        style.configure("Secondary.TButton", padding=(13, 9), font=("Segoe UI", 10))
        style.configure("Status.TLabel", background=self.colors["background"], foreground=self.colors["muted"], font=("Segoe UI", 10, "bold"))

        frame = ttk.Frame(self.root, style="App.TFrame", padding=(22, 18))
        frame.pack(fill="both", expand=True)
        header = tk.Frame(frame, bg=self.colors["navy"], padx=22, pady=18)
        header.pack(fill="x", pady=(0, 16))
        ttk.Label(header, text="知乎采集器", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="搜索、问题、用户内容与收藏夹，一站式保存为 Markdown", style="Subtitle.TLabel").pack(anchor="w", pady=(4, 0))

        card = ttk.LabelFrame(frame, text=" 任务配置 ", style="Card.TLabelframe", padding=(18, 14))
        card.pack(fill="x", pady=(0, 14))
        fields = [("任务类型", "task_type"), ("关键词或 URL", "target"), ("最大数量", "max_items"), ("请求间隔（秒）", "interval"), ("代理地址", "proxy")]
        for row, (label, name) in enumerate(fields):
            ttk.Label(card, text=label, style="Body.TLabel").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 16))
            if name == "task_type":
                widget = ttk.Combobox(card, textvariable=self.vars[name], values=[task_type_label(t.value) for t in TaskType], state="readonly", width=28)
            else:
                widget = ttk.Entry(card, textvariable=self.vars[name], width=70)
            widget.grid(row=row, column=1, sticky="ew", pady=6)
        ttk.Checkbutton(card, text="抓取评论（仅采集模式）", variable=self.include_comments).grid(row=5, column=1, sticky="w", pady=(6, 2))
        ttk.Label(card, text=build_output_hint(self.settings.output_dir), style="Muted.TLabel").grid(row=6, column=1, sticky="w", pady=(7, 0))
        card.columnconfigure(1, weight=1)

        actions = ttk.Frame(frame, style="App.TFrame")
        actions.pack(fill="x", pady=(0, 9))
        ttk.Button(actions, text="▶  开始任务", style="Primary.TButton", command=self._start).pack(side="left", padx=(0, 9))
        ttk.Button(actions, text="■  停止", style="Secondary.TButton", command=self._cancel).pack(side="left", padx=(0, 9))
        ttk.Button(actions, text="⇥  登录知乎", style="Secondary.TButton", command=self._login).pack(side="left", padx=(0, 9))
        ttk.Button(actions, text="打开输出目录", style="Secondary.TButton", command=self._open_output).pack(side="right")

        status_bar = ttk.Frame(frame, style="App.TFrame")
        status_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(status_bar, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        ttk.Label(status_bar, text="安全间隔与登录态由程序自动管理", style="Muted.TLabel").pack(side="right")

        log_card = ttk.LabelFrame(frame, text=" 运行日志 ", style="Card.TLabelframe", padding=10)
        log_card.pack(fill="both", expand=True)
        log_frame = ttk.Frame(log_card)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=14, state="disabled", wrap="word", bg="#101828", fg="#D0D5DD", insertbackground="white", relief="flat", padx=14, pady=12, font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

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
        self.log.configure(state="normal"); self.log.insert("end", message + "\n"); self.log.see("end"); self.log.configure(state="disabled")

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
